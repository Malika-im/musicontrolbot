"""initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_telegram_id'), 'users', ['telegram_id'], unique=True)

    # AudioFiles table
    op.create_table(
        'audio_files',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('original_filename', sa.String(length=512), nullable=False),
        sa.Column('file_format', sa.String(length=32), nullable=False),
        sa.Column('duration', sa.Float(), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('storage_path', sa.String(length=1024), nullable=False),
        sa.Column('detected_key', sa.String(length=64), nullable=True),
        sa.Column('detected_bpm', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audio_files_user_id'), 'audio_files', ['user_id'], unique=False)

    # ProcessingTasks table
    op.create_table(
        'processing_tasks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('audio_id', sa.UUID(), nullable=False),
        sa.Column('task_type', sa.String(length=64), nullable=False),
        sa.Column('processing_status', sa.String(length=32), nullable=False),
        sa.Column('processing_parameters', sa.JSON(), nullable=False),
        sa.Column('result_path', sa.String(length=1024), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('semitones_shifted', sa.Float(), nullable=True),
        sa.Column('original_key', sa.String(length=64), nullable=True),
        sa.Column('result_key', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['audio_id'], ['audio_files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_processing_tasks_audio_id'), 'processing_tasks', ['audio_id'], unique=False)
    op.create_index(op.f('ix_processing_tasks_processing_status'), 'processing_tasks', ['processing_status'], unique=False)
    op.create_index(op.f('ix_processing_tasks_task_type'), 'processing_tasks', ['task_type'], unique=False)
    op.create_index(op.f('ix_processing_tasks_user_id'), 'processing_tasks', ['user_id'], unique=False)
    op.create_index('idx_user_status', 'processing_tasks', ['user_id', 'processing_status'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_user_status', table_name='processing_tasks')
    op.drop_index(op.f('ix_processing_tasks_user_id'), table_name='processing_tasks')
    op.drop_index(op.f('ix_processing_tasks_task_type'), table_name='processing_tasks')
    op.drop_index(op.f('ix_processing_tasks_processing_status'), table_name='processing_tasks')
    op.drop_index(op.f('ix_processing_tasks_audio_id'), table_name='processing_tasks')
    op.drop_table('processing_tasks')
    op.drop_index(op.f('ix_audio_files_user_id'), table_name='audio_files')
    op.drop_table('audio_files')
    op.drop_index(op.f('ix_users_telegram_id'), table_name='users')
    op.drop_table('users')
