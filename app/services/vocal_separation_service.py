"""
Vocal Separation Service.
Creates clean backing tracks (instrumentals/минусовки) and isolates vocal tracks.
"""

from pathlib import Path
from typing import Dict, Optional
from app.audio.ffmpeg_utils import FFmpegUtils
from app.core.exceptions import AudioSeparationError
from app.core.logging import logger
from app.services.audio_separation_service import AudioSeparationService


class VocalSeparationService:
    def __init__(self, separation_service: AudioSeparationService | None = None):
        self.separation_service = separation_service or AudioSeparationService()

    def create_instrumental(
        self,
        audio_path: Path,
        stems_dir: Path,
        output_path: Path,
        cached_stems: Optional[Dict[str, Path]] = None,
    ) -> Path:
        """
        Creates a high-quality backing track (минусовка) by separating stems
        and combining drums, bass, and other (leaving vocals out).
        """
        stems = cached_stems or self.separation_service.separate_stems(audio_path, stems_dir)
        instrumental_stems = []
        for name in ["drums", "bass", "other", "guitar", "piano"]:
            if name in stems and stems[name].exists():
                instrumental_stems.append(stems[name])

        if not instrumental_stems:
            raise AudioSeparationError("Не удалось получить инструментальные дорожки.")

        logger.info(f"Mixing instrumental stems: {[p.name for p in instrumental_stems]} -> {output_path.name}")
        return FFmpegUtils.mix_tracks(instrumental_stems, output_path)

    def extract_vocals(
        self,
        audio_path: Path,
        stems_dir: Path,
        output_path: Path,
        cached_stems: Optional[Dict[str, Path]] = None,
    ) -> Path:
        """
        Extracts vocal track from input audio.
        """
        stems = cached_stems or self.separation_service.separate_stems(audio_path, stems_dir)
        if "vocals" not in stems or not stems["vocals"].exists():
            raise AudioSeparationError("Не удалось извлечь дорожку вокала.")

        import shutil
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(stems["vocals"], output_path)
        logger.info(f"Isolated vocal stem saved to {output_path.name}")
        return output_path
