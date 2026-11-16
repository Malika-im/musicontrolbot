"""
SQLAlchemy Database Models.
Users, AudioFiles, and ProcessingTasks.
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TaskType(str, enum.Enum):
    KARAOKE = "KARAOKE"                           # Instrumental without main vocals
    LEAD_VOCALS = "LEAD_VOCALS"                   # Main voice only
    BACKING_VOCALS = "BACKING_VOCALS"             # Backing vocals only
    REMOVE_BACKING_VOCALS = "REMOVE_BACKING_VOCALS" # Keep main voice, remove backings
    SEPARATE_STEMS = "SEPARATE_STEMS"             # 4 or 6 full stems
    SMART_EDIT = "SMART_EDIT"                     # Natural language planned edits
    PITCH_SHIFT = "PITCH_SHIFT"                   # Transpose key / semitones


class ProcessingStatus(str, enum.Enum):
    PENDING = "PENDING"
    ANALYZING = "ANALYZING"
    SEPARATING = "SEPARATING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    audio_files: Mapped[List["AudioFile"]] = relationship(
        "AudioFile", back_populates="user", cascade="all, delete-orphan"
    )
    tasks: Mapped[List["ProcessingTask"]] = relationship(
        "ProcessingTask", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User telegram_id={self.telegram_id} username={self.username}>"


class AudioFile(Base):
    __tablename__ = "audio_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_format: Mapped[str] = mapped_column(String(32), nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    
    # Music analysis metadata
    detected_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    detected_bpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="audio_files")
    tasks: Mapped[List["ProcessingTask"]] = relationship(
        "ProcessingTask", back_populates="audio_file", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AudioFile id={self.id} filename={self.original_filename} duration={self.duration}s>"


class ProcessingTask(Base):
    __tablename__ = "processing_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    audio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    processing_status: Mapped[str] = mapped_column(
        String(32), default=ProcessingStatus.PENDING.value, nullable=False, index=True
    )
    # Generic JSON storage compatible with SQLite & Postgres
    processing_parameters: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=dict, nullable=False
    )
    result_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Key transposition fields (Section 13)
    semitones_shifted: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    original_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    result_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="tasks")
    audio_file: Mapped["AudioFile"] = relationship("AudioFile", back_populates="tasks")

    __table_args__ = (
        Index("idx_user_status", "user_id", "processing_status"),
    )

    def __repr__(self) -> str:
        return f"<ProcessingTask id={self.id} type={self.task_type} status={self.processing_status}>"
