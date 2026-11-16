"""
Telegram Update Dispatcher.
Routes messages, commands, and callback queries to domain handlers.
"""

import uuid
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.bot_service import TelegramBotService
from app.bot.handlers.audio_handlers import AudioHandlers
from app.bot.handlers.command_handlers import CommandHandlers
from app.bot.handlers.text_handlers import TextHandlers
from app.bot.keyboards.inline import get_audio_action_keyboard, get_pitch_keyboard
from app.core.exceptions import TaskLimitExceededError
from app.core.logging import logger
from app.database.models import TaskType
from app.database.repositories import AudioFileRepository, UserRepository
from app.services.task_manager import TaskManager


class TelegramDispatcher:
    def __init__(self, session: AsyncSession, bot_service: TelegramBotService):
        self.session = session
        self.bot = bot_service
        self.commands = CommandHandlers(bot_service, session)
        self.audio_handlers = AudioHandlers(bot_service, session)
        self.text_handlers = TextHandlers(bot_service, session)
        self.task_mgr = TaskManager(session)
        self.user_repo = UserRepository(session)
        self.audio_repo = AudioFileRepository(session)

    async def dispatch_update(self, update: Dict[str, Any]) -> None:
        """Route incoming Telegram Update JSON."""
        if "message" in update:
            await self._dispatch_message(update["message"])
        elif "callback_query" in update:
            await self._dispatch_callback_query(update["callback_query"])

    async def _dispatch_message(self, message: Dict[str, Any]) -> None:
        chat_id = message["chat"]["id"]
        telegram_id = message["from"]["id"]
        username = message["from"].get("username")

        # Command handling
        text = message.get("text", "")
        if text.startswith("/"):
            cmd = text.split()[0].lower()
            if cmd == "/start":
                await self.commands.handle_start(chat_id, telegram_id, username)
            elif cmd == "/help":
                await self.commands.handle_help(chat_id)
            elif cmd == "/history":
                await self.commands.handle_history(chat_id, telegram_id)
            elif cmd == "/cancel":
                await self.commands.handle_cancel(chat_id, telegram_id)
            return

        # Check for media
        if any(k in message for k in ("audio", "voice", "document", "video", "video_note")):
            await self.audio_handlers.handle_media_message(chat_id, telegram_id, username, message)
            return

        # Check for URL
        if text.startswith("http://") or text.startswith("https://"):
            await self.audio_handlers.handle_external_url(chat_id, telegram_id, username, text.strip())
            return

        # Natural language text / smart editing
        if text:
            await self.text_handlers.handle_text(chat_id, telegram_id, username, text)

    async def _dispatch_callback_query(self, query: Dict[str, Any]) -> None:
        query_id = query["id"]
        data = query.get("data", "")
        message = query.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        msg_id = message.get("message_id")
        telegram_id = query["from"]["id"]

        await self.bot.answer_callback_query(query_id)
        if not chat_id or not data:
            return

        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if not user:
            return

        parts = data.split(":")
        action_prefix = parts[0]

        # 1. Main audio actions (act:...)
        if action_prefix == "act":
            action = parts[1]
            if action == "new_song":
                await self.bot.send_message(chat_id, "Отправьте песню, чтобы начать обработку! 🎵")
                return

            audio_id = uuid.UUID(parts[2])
            audio = await self.audio_repo.get_by_id(audio_id)
            if not audio:
                await self.bot.send_message(chat_id, "⚠️ Аудиофайл устарел или не найден.")
                return

            if action == "pitch_menu":
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=(
                        f"🎼 <b>Транспонирование (Изменение тональности)</b>\n"
                        f"Текущая тональность: <b>{audio.detected_key or 'C major'}</b>\n"
                        f"Темп (BPM): <b>{audio.detected_bpm or 120.0}</b>\n\n"
                        f"Выберите количество полутонов или напишите значение в чат:"
                    ),
                    reply_markup=get_pitch_keyboard(audio.id),
                )
                return

            if action == "smart_prompt":
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "✂️ <b>Умное редактирование AI</b>\n\n"
                        "Напишите в ответ обычным текстом, что именно сделать с песней. Например:\n"
                        "• <i>«Оставь только бэк-вокал»</i>\n"
                        "• <i>«Убери голос в куплетах, но оставь в припеве»</i>\n"
                        "• <i>«Оставь слова 'я тебя люблю'»</i>\n"
                        "• <i>«Сделай минусовку на тон ниже»</i>"
                    ),
                )
                return

            # Task types mapping
            task_type_map = {
                "karaoke": TaskType.KARAOKE.value,
                "lead_vocals": TaskType.LEAD_VOCALS.value,
                "backing_vocals": TaskType.BACKING_VOCALS.value,
                "remove_backing": TaskType.REMOVE_BACKING_VOCALS.value,
                "stems": TaskType.SEPARATE_STEMS.value,
            }
            if action in task_type_map:
                try:
                    await self.bot.send_message(chat_id, "⏳ Задача добавлена в очередь обработки...")
                    await self.task_mgr.create_and_enqueue_task(
                        user_id=user.id,
                        audio_id=audio.id,
                        task_type=task_type_map[action],
                        original_key=audio.detected_key,
                    )
                except TaskLimitExceededError as e:
                    await self.bot.send_message(chat_id, e.user_friendly_message)

        # 2. Pitch shifting actions (pitch:...)
        elif action_prefix == "pitch":
            sub_action = parts[1]
            audio_id = uuid.UUID(parts[2])
            audio = await self.audio_repo.get_by_id(audio_id)
            if not audio:
                return

            if sub_action == "back":
                mins = int(audio.duration // 60)
                secs = int(audio.duration % 60)
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=(
                        f"🎵 <b>Файл:</b> {audio.original_filename}\n"
                        f"⏱ <b>Длительность:</b> {mins}:{secs:02d}\n"
                        f"🎼 <b>Тональность:</b> {audio.detected_key}\n\n"
                        f"Выберите вариант обработки:"
                    ),
                    reply_markup=get_audio_action_keyboard(audio.id),
                )
                return

            if sub_action == "custom":
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "✍️ <b>Введите желаемое изменение тональности</b>\n\n"
                        "Отправьте число полутонов (от -12 до +12), например: <code>+2</code>, <code>-1.5</code>, <code>4</code>\n"
                        "Или напишите текстом: <i>«Понизь на 2 полутона»</i>"
                    ),
                )
                return

            # Specific semitone button pressed
            semitones = float(sub_action)
            direction = "повышение" if semitones > 0 else "понижение"
            await self.bot.send_message(
                chat_id,
                f"⏳ Запущено изменение тональности ({direction} на {abs(semitones):.0f} полут.)...",
            )
            try:
                await self.task_mgr.create_and_enqueue_task(
                    user_id=user.id,
                    audio_id=audio.id,
                    task_type=TaskType.PITCH_SHIFT.value,
                    parameters={"semitones": semitones},
                    semitones=semitones,
                    original_key=audio.detected_key,
                )
            except TaskLimitExceededError as e:
                await self.bot.send_message(chat_id, e.user_friendly_message)
