"""
Tests for Storage Service and Cleanup Policies.
"""

import time
import uuid
from pathlib import Path
from app.storage.storage_service import StorageService


def test_storage_directories_and_paths(tmp_path: Path):
    storage = StorageService(base_dir=tmp_path)
    assert storage.uploads_dir.exists()
    assert storage.stems_dir.exists()
    assert storage.results_dir.exists()
    assert storage.temp_dir.exists()

    user_id = uuid.uuid4()
    task_id = uuid.uuid4()

    upload_file = storage.get_upload_path(user_id, "mp3")
    assert upload_file.parent == storage.uploads_dir
    assert upload_file.suffix == ".mp3"

    stems_dir = storage.get_task_stems_dir(task_id)
    assert stems_dir.exists()
    assert stems_dir.name == str(task_id)

    result_file = storage.get_result_path(task_id, "karaoke", "mp3")
    assert result_file.parent == storage.results_dir


def test_storage_task_stems_cleanup(tmp_path: Path):
    storage = StorageService(base_dir=tmp_path)
    task_id = uuid.uuid4()
    stems_dir = storage.get_task_stems_dir(task_id)

    # Create dummy stem file
    dummy_file = stems_dir / "vocals.wav"
    dummy_file.write_bytes(b"dummy stem data")
    assert dummy_file.exists()

    # Clean up
    storage.cleanup_task_temp_files(task_id)
    assert not stems_dir.exists()


def test_storage_retention_purge(tmp_path: Path):
    storage = StorageService(base_dir=tmp_path)

    # Create old file in temp dir
    old_file = storage.temp_dir / "expired.tmp"
    old_file.write_bytes(b"old")

    # Manually backdate modification time to 48 hours ago
    past_time = time.time() - (48 * 3600)
    import os
    os.utime(old_file, (past_time, past_time))

    # Run cleanup with 24h retention
    removed = storage.cleanup_old_files(max_age_hours=24)
    assert removed >= 1
    assert not old_file.exists()
