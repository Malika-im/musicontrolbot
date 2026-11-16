"""
Telegram Command Handlers (/start, /help, /history, /cancel).
"""

from sqlalchemy.ext.asyncio import AsyncSession
from app.bot.bot_service import TelegramBotService
from app.database.models import ProcessingStatus
from app.database.repositories import TaskRepository, UserRepository


START_MESSAGE = (
    "Привет! 🎵 Я AI-бот для работы с музыкой.\n\n"
    "Отправь мне аудиозапись или файл с песней, и я смогу:\n\n"
    "🎤 <b>Убрать голос и создать минусовку.</b>\n"
    "🎧 <b>Извлечь вокал.</b>\n"
    "🎼 <b>Оставить бэк-вокал.</b>\n"
    "✂️ <b>Удалить или сохранить определённые слова.</b>\n"
    "🎹 <b>Разделить музыку на отдельные инструменты.</b>\n"
    "🎹 <b>Изменить тональность песни без изменения скорости.</b>\n\n"
    "Просто отправь песню, чтобы начать!"
)

HELP_MESSAGE = (
    "<b>Справка по использованию AI Music Bot 🎵</b>\n\n"
    "1. <b>Форматы:</b> MP3, WAV, FLAC, M4A, OGG, AAC, голосовые сообщения и видео.\n"
    "2. <b>Максимум:</b> до 50 МБ и до 15 минут длительности.\n"
    "3. <b>Изменение тональности (Pitch Shift):</b>\n"
    "   Используйте кнопки ⬇️/⬆️ или напишите: <i>«Понизь на 2 полутона»</i>, <i>«Подними на полтона»</i>.\n"
    "   Длительность и BPM трека не изменяются!\n"
    "4. <b>Умное редактирование (AI):</b>\n"
    "   Вы можете написать естественным языком, например:\n"
    "   • <i>«Оставь только бэк-вокал»</i>\n"
    "   • <i>«Убери основной голос, но оставь бэки»</i>\n"
    "   • <i>«Оставь слова 'я тебя люблю'»</i>\n"
    "   • <i>«Сделай минусовку на тон ниже»</i>\n\n"
    "Команды:\n"
    "/start — Перезапуск бота\n"
    "/help — Справка\n"
    "/history — История ваших обработок\n"
    "/cancel — Отмена текущей задачи"
)


class CommandHandlers:
    def __init__(self, bot_service: TelegramBotService, session: AsyncSession):
        self.bot = bot_service
        self.session = session
        self.user_repo = UserRepository(session)
        self.task_repo = TaskRepository(session)

    async def handle_start(self, chat_id: int, telegram_id: int, username: str | None) -> None:
        """Handle /start command: register user and send greeting."""
        await self.user_repo.get_or_create(telegram_id=telegram_id, username=username)
        await self.session.commit()
        await self.bot.send_message(chat_id=chat_id, text=START_MESSAGE)

    async def handle_help(self, chat_id: int) -> None:
        """Handle /help command."""
        await self.bot.send_message(chat_id=chat_id, text=HELP_MESSAGE)

    async def handle_history(self, chat_id: int, telegram_id: int) -> None:
        """Handle /history command: show recent user tasks."""
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if not user:
            await self.bot.send_message(chat_id=chat_id, text="У вас пока нет обработанных аудиозаписей.")
            return

        tasks = await self.task_repo.get_user_history(user.id, limit=5)
        if not tasks:
            await self.bot.send_message(chat_id=chat_id, text="У вас пока нет истории обработок. Отправьте аудио!")
            return

        lines = ["<b>📜 Ваша история обработок:</b>\n"]
        for idx, task in enumerate(tasks, 1):
            date_str = task.created_at.strftime("%d.%m.%Y %H:%M")
            song_name = task.audio_file.original_filename if task.audio_file else "Аудио"
            status_emoji = "✅" if task.processing_status == ProcessingStatus.COMPLETED.value else "⏳"
            pitch_info = f" ({task.semitones_shifted:+.1f} полут.)" if task.semitones_shifted else ""
            lines.append(f"{idx}. {status_emoji} <b>{song_name}</b>\n   Тип: {task.task_type}{pitch_info} | {date_str}")

        await self.bot.send_message(chat_id=chat_id, text="\n".join(lines))

    async def handle_cancel(self, chat_id: int, telegram_id: int) -> None:
        """Handle /cancel command: cancel active processing task."""
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if not user:
            await self.bot.send_message(chat_id=chat_id, text="Нет активных задач для отмены.")
            return

        task = await self.task_repo.get_latest_active_or_recent_task(user.id)
        if not task or task.processing_status not in (
            ProcessingStatus.PENDING.value,
            ProcessingStatus.ANALYZING.value,
            ProcessingStatus.SEPARATING.value,
            ProcessingStatus.PROCESSING.value,
        ):
            await self.bot.send_message(chat_id=chat_id, text="У вас нет активных задач для отмены.")
            return

        await self.task_repo.update_status(task.id, ProcessingStatus.CANCELLED, error_message="Отменено пользователем")
        await self.session.commit()
        await self.bot.send_message(chat_id=chat_id, text="⛔ Обработка текущей задачи отменена.")
