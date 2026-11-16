"""
Database Repositories for Users, AudioFiles, and ProcessingTasks.
Encapsulates all SQL queries with SQLAlchemy 2.0 async syntax.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import AudioFile, ProcessingStatus, ProcessingTask, User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, telegram_id: int, username: Optional[str] = None) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(
                id=uuid.uuid4(),
                telegram_id=telegram_id,
                username=username,
            )
            self.session.add(user)
            await self.session.flush()
        elif username and user.username != username:
            user.username = username
            await self.session.flush()
        return user


class AudioFileRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: uuid.UUID,
        original_filename: str,
        file_format: str,
        duration: float,
        file_size: int,
        storage_path: str,
        detected_key: Optional[str] = None,
        detected_bpm: Optional[float] = None,
    ) -> AudioFile:
        audio = AudioFile(
            id=uuid.uuid4(),
            user_id=user_id,
            original_filename=original_filename,
            file_format=file_format.lower(),
            duration=duration,
            file_size=file_size,
            storage_path=storage_path,
            detected_key=detected_key,
            detected_bpm=detected_bpm,
        )
        self.session.add(audio)
        await self.session.flush()
        return audio

    async def get_by_id(self, audio_id: uuid.UUID) -> Optional[AudioFile]:
        stmt = select(AudioFile).where(AudioFile.id == audio_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_for_user(self, user_id: uuid.UUID) -> Optional[AudioFile]:
        stmt = (
            select(AudioFile)
            .where(AudioFile.user_id == user_id)
            .order_by(desc(AudioFile.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID, limit: int = 10) -> List[AudioFile]:
        stmt = (
            select(AudioFile)
            .where(AudioFile.user_id == user_id)
            .order_by(desc(AudioFile.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: uuid.UUID,
        audio_id: uuid.UUID,
        task_type: str,
        processing_parameters: Optional[Dict[str, Any]] = None,
        semitones_shifted: Optional[float] = None,
        original_key: Optional[str] = None,
    ) -> ProcessingTask:
        task = ProcessingTask(
            id=uuid.uuid4(),
            user_id=user_id,
            audio_id=audio_id,
            task_type=task_type,
            processing_status=ProcessingStatus.PENDING.value,
            processing_parameters=processing_parameters or {},
            semitones_shifted=semitones_shifted,
            original_key=original_key,
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def get_by_id(self, task_id: uuid.UUID) -> Optional[ProcessingTask]:
        stmt = (
            select(ProcessingTask)
            .options(selectinload(ProcessingTask.audio_file))
            .where(ProcessingTask.id == task_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_active_tasks_for_user(self, user_id: uuid.UUID) -> int:
        active_statuses = [
            ProcessingStatus.PENDING.value,
            ProcessingStatus.ANALYZING.value,
            ProcessingStatus.SEPARATING.value,
            ProcessingStatus.PROCESSING.value,
        ]
        stmt = (
            select(func.count(ProcessingTask.id))
            .where(
                ProcessingTask.user_id == user_id,
                ProcessingTask.processing_status.in_(active_statuses),
            )
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def update_status(
        self,
        task_id: uuid.UUID,
        status: ProcessingStatus,
        result_path: Optional[str] = None,
        error_message: Optional[str] = None,
        semitones_shifted: Optional[float] = None,
        original_key: Optional[str] = None,
        result_key: Optional[str] = None,
    ) -> Optional[ProcessingTask]:
        task = await self.get_by_id(task_id)
        if not task:
            return None

        task.processing_status = status.value
        if result_path is not None:
            task.result_path = result_path
        if error_message is not None:
            task.error_message = error_message
        if semitones_shifted is not None:
            task.semitones_shifted = semitones_shifted
        if original_key is not None:
            task.original_key = original_key
        if result_key is not None:
            task.result_key = result_key

        if status in (ProcessingStatus.COMPLETED, ProcessingStatus.FAILED, ProcessingStatus.CANCELLED):
            task.completed_at = datetime.now(timezone.utc)

        await self.session.flush()
        return task

    async def get_user_history(self, user_id: uuid.UUID, limit: int = 10) -> List[ProcessingTask]:
        stmt = (
            select(ProcessingTask)
            .options(selectinload(ProcessingTask.audio_file))
            .where(ProcessingTask.user_id == user_id)
            .order_by(desc(ProcessingTask.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_active_or_recent_task(self, user_id: uuid.UUID) -> Optional[ProcessingTask]:
        stmt = (
            select(ProcessingTask)
            .options(selectinload(ProcessingTask.audio_file))
            .where(ProcessingTask.user_id == user_id)
            .order_by(desc(ProcessingTask.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
