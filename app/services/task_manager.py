"""
Task Manager Service.
Handles task creation, concurrency limits, deduplication, state transitions,
and asynchronous worker dispatch.
"""

import uuid
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import TaskLimitExceededError
from app.core.logging import logger
from app.database.models import ProcessingStatus, ProcessingTask, TaskType
from app.database.repositories import TaskRepository


class TaskManager:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.task_repo = TaskRepository(session)
        self.settings = get_settings()

    async def create_and_enqueue_task(
        self,
        user_id: uuid.UUID,
        audio_id: uuid.UUID,
        task_type: str,
        parameters: Optional[Dict[str, Any]] = None,
        semitones: Optional[float] = None,
        original_key: Optional[str] = None,
    ) -> ProcessingTask:
        """
        Validate user task limits, create DB task record, and enqueue to Celery.
        """
        # Concurrency limit check
        active_count = await self.task_repo.count_active_tasks_for_user(user_id)
        if active_count >= self.settings.MAX_CONCURRENT_TASKS_PER_USER:
            raise TaskLimitExceededError(
                f"User {user_id} has {active_count} active tasks (limit {self.settings.MAX_CONCURRENT_TASKS_PER_USER})",
                f"⚠️ У вас уже выполняется {active_count} задачи. Дождитесь завершения перед запуском новой."
            )

        # Create record in DB
        task = await self.task_repo.create(
            user_id=user_id,
            audio_id=audio_id,
            task_type=task_type,
            processing_parameters=parameters or {},
            semitones_shifted=semitones,
            original_key=original_key,
        )
        await self.session.commit()

        # Enqueue in Celery
        try:
            from app.workers.tasks import process_audio_task
            process_audio_task.delay(str(task.id))
            logger.info(f"Enqueued Celery task for task_id={task.id}")
        except Exception as e:
            logger.warning(f"Could not enqueue Celery task immediately (worker may be local/mocked): {e}")

        return task

    async def update_task_progress(
        self,
        task_id: uuid.UUID,
        status: ProcessingStatus,
        result_path: Optional[str] = None,
        error_message: Optional[str] = None,
        semitones_shifted: Optional[float] = None,
        result_key: Optional[str] = None,
    ) -> Optional[ProcessingTask]:
        """Update task status in DB."""
        task = await self.task_repo.update_status(
            task_id=task_id,
            status=status,
            result_path=result_path,
            error_message=error_message,
            semitones_shifted=semitones_shifted,
            result_key=result_key,
        )
        await self.session.commit()
        return task
