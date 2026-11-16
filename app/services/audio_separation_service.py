"""
Audio Separation Service.
Coordinates Demucs PyTorch stem separation and manages stems directory.
"""

from pathlib import Path
from typing import Dict
from app.ai.demucs_engine import DemucsEngine
from app.core.exceptions import AudioSeparationError
from app.core.logging import logger
from app.storage.storage_service import StorageService


class AudioSeparationService:
    def __init__(
        self,
        demucs_engine: DemucsEngine | None = None,
        storage_service: StorageService | None = None,
    ):
        self.demucs_engine = demucs_engine or DemucsEngine()
        self.storage_service = storage_service or StorageService()

    def separate_stems(self, audio_path: Path, task_stems_dir: Path) -> Dict[str, Path]:
        """
        Run Demucs stem separation on input audio.
        Returns dict of paths: {'vocals': Path, 'drums': Path, 'bass': Path, 'other': Path}
        """
        if not audio_path.exists():
            raise AudioSeparationError(f"Файл {audio_path} не существует.")

        logger.info(f"Starting Demucs separation for {audio_path.name} into {task_stems_dir}")
        stems = self.demucs_engine.separate(audio_path, task_stems_dir)
        return stems
