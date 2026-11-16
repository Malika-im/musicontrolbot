"""
Text and Smart Edit Handlers.
Processes natural language audio instructions, custom pitch numbers, and URLs.
"""

from typing import Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.bot_service import TelegramBotService
from app.core.exceptions import PlannerAmbiguityError, TaskLimitExceededError
from app.core.logging import logger
from app.database.models import TaskType
from app.database.repositories import AudioFileRepository, UserRepository
from app.services.audio_edit_planner import AudioEditPlanner
from app.services.task_manager import TaskManager


class TextHandlers:
    def __init__(
        self,
        bot_service: TelegramBotService,
        session: AsyncSession,
        planner: Optional[AudioEditPlanner] = None,
        task_manager: Optional[TaskManager] = None,
    ):
        self.bot = bot_service
        self.session = session
        self.planner = planner or AudioEditPlanner()
        self.task_mgr = task_manager or TaskManager(session)
        self.user_repo = UserRepository(session)
        self.audio_repo = AudioFileRepository(session)

    async def handle_text(
        self,
        chat_id: int,
        telegram_id: int,
        username: Optional[str],
        text: str,
    ) -> None:
        """Handle incoming text message."""
        clean_text = text.strip()
        user = await self.user_repo.get_or_create(telegram_id=telegram_id, username=username)

        # 1. Check if user typed a numeric pitch value (e.g. "-2", "+3", "1.5")
        if self._is_pitch_number(clean_text):
            semitones = float(clean_text.replace("+", ""))
            latest_audio = await self.audio_repo.get_latest_for_user(user.id)
            if not latest_audio:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text="Сначала отправьте песню, для которой нужно изменить тональность!"
                )
                return

            await self._enqueue_pitch_task(chat_id, user.id, latest_audio.id, semitones, latest_audio.detected_key)
            return

        # 2. Check if user sent a natural language smart edit prompt
        latest_audio = await self.audio_repo.get_latest_for_user(user.id)
        if not latest_audio:
            await self.bot.send_message(
                chat_id=chat_id,
                text="Сначала отправьте музыкальный файл, чтобы я мог применить к нему изменения 🎵"
            )
            return

        # Parse with AudioEditPlanner
        try:
            plan = self.planner.plan_edit(clean_text)

            confirm_msg = await self.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🧠 <b>План обработки сформирован:</b>\n"
                    f"• {plan.summary_description}\n\n"
                    f"⏳ Задача поставлена в очередь..."
                ),
            )

            # Map planned action to task type
            task_type = plan.action_type
            params = plan.model_dump()

            await self.task_mgr.create_and_enqueue_task(
                user_id=user.id,
                audio_id=latest_audio.id,
                task_type=task_type,
                parameters=params,
                semitones=plan.pitch_semitones,
                original_key=latest_audio.detected_key,
            )

        except PlannerAmbiguityError as e:
            await self.bot.send_message(chat_id=chat_id, text=e.clarification_prompt)
        except TaskLimitExceededError as e:
            await self.bot.send_message(chat_id=chat_id, text=e.user_friendly_message)
        except Exception as e:
            logger.exception(f"Error handling smart prompt: {e}")
            await self.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Не удалось распознать инструкцию. Попробуйте сформулировать запрос иначе."
            )

    async def _enqueue_pitch_task(
        self,
        chat_id: int,
        user_id: uuid.UUID,
        audio_id: uuid.UUID,
        semitones: float,
        orig_key: Optional[str],
    ) -> None:
        direction = "повышение" if semitones > 0 else "понижение"
        await self.bot.send_message(
            chat_id=chat_id,
            text=f"⏳ Запущено изменение тональности ({direction} на {abs(semitones):.1f} полутона)...",
        )
        try:
            await self.task_mgr.create_and_enqueue_task(
                user_id=user_id,
                audio_id=audio_id,
                task_type=TaskType.PITCH_SHIFT.value,
                parameters={"semitones": semitones},
                semitones=semitones,
                original_key=orig_key,
            )
        except TaskLimitExceededError as e:
            await self.bot.send_message(chat_id=chat_id, text=e.user_friendly_message)

    @staticmethod
    def _is_pitch_number(text: str) -> bool:
        """Check if string is a numeric pitch offset like +2, -3, 1, 2.5."""
        clean = text.strip().replace("+", "")
        try:
            val = float(clean)
            return -12.0 <= val <= 12.0 and val != 0.0
        except ValueError:
            return False
