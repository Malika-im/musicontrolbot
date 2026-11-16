"""
Storage Service.
Manages disk layout, uploads, stems, results, disk space monitoring, and retention cleanup.
"""

import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.exceptions import StorageError
from app.core.logging import logger


class StorageService:
    def __init__(self, base_dir: Optional[Path] = None):
        self.settings = get_settings()
        self.base_dir = base_dir or self.settings.STORAGE_BASE_DIR
        self.uploads_dir = self.base_dir / "uploads"
        self.stems_dir = self.base_dir / "stems"
        self.results_dir = self.base_dir / "results"
        self.temp_dir = self.base_dir / "temp"

        self.ensure_directories()

    def ensure_directories(self) -> None:
        """Create necessary storage subdirectories if they do not exist."""
        for directory in [self.uploads_dir, self.stems_dir, self.results_dir, self.temp_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def check_disk_space(self) -> float:
        """
        Check free disk space in GB.
        Raises StorageError if free space is below the configured threshold.
        """
        stat = shutil.disk_usage(self.base_dir)
        free_gb = stat.free / (1024 ** 3)
        if free_gb < self.settings.DISK_MIN_FREE_SPACE_GB:
            logger.error(f"Low disk space: {free_gb:.2f} GB free, minimum required is {self.settings.DISK_MIN_FREE_SPACE_GB} GB")
            raise StorageError(
                f"Недостаточно места на диске ({free_gb:.2f} GB).",
                "⚠️ Сервер временно перегружен из-за нехватки дискового пространства."
            )
        return free_gb

    def get_upload_path(self, user_id: uuid.UUID, extension: str) -> Path:
        """Generate a secure, unique filepath for an incoming upload."""
        self.check_disk_space()
        ext = extension.lstrip(".").lower()
        filename = f"{user_id}_{uuid.uuid4().hex}.{ext}"
        return self.uploads_dir / filename

    def get_task_stems_dir(self, task_id: uuid.UUID) -> Path:
        """Get or create a dedicated stems directory for a processing task."""
        self.check_disk_space()
        task_dir = self.stems_dir / str(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    def get_result_path(self, task_id: uuid.UUID, suffix: str, extension: str = "mp3") -> Path:
        """Generate destination path for a processed output audio file."""
        self.check_disk_space()
        ext = extension.lstrip(".").lower()
        filename = f"result_{task_id}_{suffix}.{ext}"
        return self.results_dir / filename

    def cleanup_task_temp_files(self, task_id: uuid.UUID) -> None:
        """Remove intermediate separated stems and temporary files for a completed or failed task."""
        task_stems = self.stems_dir / str(task_id)
        if task_stems.exists():
            shutil.rmtree(task_stems, ignore_errors=True)
            logger.debug(f"Cleaned up stems directory for task {task_id}")

    def cleanup_old_files(self, max_age_hours: Optional[int] = None) -> int:
        """
        Purge files older than retention policy from uploads, stems, and temp directories.
        Returns count of removed items.
        """
        hours = max_age_hours or self.settings.CLEANUP_RETENTION_HOURS
        now = time.time()
        max_age_seconds = hours * 3600
        removed_count = 0

        target_dirs = [self.temp_dir, self.stems_dir, self.uploads_dir]
        for directory in target_dirs:
            if not directory.exists():
                continue
            for entry in directory.iterdir():
                try:
                    file_stat = entry.stat()
                    age = now - file_stat.st_mtime
                    if age > max_age_seconds:
                        if entry.is_dir():
                            shutil.rmtree(entry, ignore_errors=True)
                        else:
                            entry.unlink(missing_ok=True)
                        removed_count += 1
                except Exception as e:
                    logger.warning(f"Failed to remove expired entry {entry}: {e}")

        logger.info(f"Storage cleanup completed. Removed {removed_count} expired files/directories.")
        return removed_count
