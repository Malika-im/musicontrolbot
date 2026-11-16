"""
Background Vocal Service.
Manages isolation of backing vocals and lead vocals, and mixing backing vocals with accompaniment.
"""

from pathlib import Path
from typing import Dict, Optional, Tuple
from app.ai.backing_vocal_engine import BackingVocalEngine
from app.audio.ffmpeg_utils import FFmpegUtils
from app.core.exceptions import AudioSeparationError
from app.core.logging import logger
from app.services.audio_separation_service import AudioSeparationService


class BackgroundVocalService:
    def __init__(
        self,
        separation_service: AudioSeparationService | None = None,
        backing_vocal_engine: BackingVocalEngine | None = None,
    ):
        self.separation_service = separation_service or AudioSeparationService()
        self.backing_vocal_engine = backing_vocal_engine or BackingVocalEngine()

    def isolate_vocals_split(
        self,
        audio_path: Path,
        stems_dir: Path,
        cached_stems: Optional[Dict[str, Path]] = None,
    ) -> Tuple[Path, Path]:
        """
        Extract vocal stem and split into lead vocals and backing vocals.
        Returns (lead_vocals_path, backing_vocals_path).
        """
        stems = cached_stems or self.separation_service.separate_stems(audio_path, stems_dir)
        vocal_stem = stems.get("vocals")
        if not vocal_stem or not vocal_stem.exists():
            raise AudioSeparationError("Дорожка вокала не найдена.")

        lead_path = stems_dir / "lead_vocals.wav"
        backing_path = stems_dir / "backing_vocals.wav"

        return self.backing_vocal_engine.separate_lead_and_backing(
            vocal_stem_path=vocal_stem,
            lead_output_path=lead_path,
            backing_output_path=backing_path,
        )

    def extract_backing_vocals_only(
        self,
        audio_path: Path,
        stems_dir: Path,
        output_path: Path,
        cached_stems: Optional[Dict[str, Path]] = None,
    ) -> Path:
        """Extract only backing vocals."""
        _, backing_path = self.isolate_vocals_split(audio_path, stems_dir, cached_stems)
        import shutil
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backing_path, output_path)
        return output_path

    def remove_backing_vocals(
        self,
        audio_path: Path,
        stems_dir: Path,
        output_path: Path,
        cached_stems: Optional[Dict[str, Path]] = None,
    ) -> Path:
        """Keep only the lead voice, removing backing vocals and choir."""
        lead_path, _ = self.isolate_vocals_split(audio_path, stems_dir, cached_stems)
        import shutil
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(lead_path, output_path)
        return output_path

    def create_instrumental_with_backings(
        self,
        audio_path: Path,
        stems_dir: Path,
        output_path: Path,
        cached_stems: Optional[Dict[str, Path]] = None,
    ) -> Path:
        """
        Remove lead vocal, but keep backing vocals along with instrumental tracks.
        """
        stems = cached_stems or self.separation_service.separate_stems(audio_path, stems_dir)
        _, backing_path = self.isolate_vocals_split(audio_path, stems_dir, stems)

        tracks_to_mix = []
        for name in ["drums", "bass", "other", "guitar", "piano"]:
            if name in stems and stems[name].exists():
                tracks_to_mix.append(stems[name])
        tracks_to_mix.append(backing_path)

        logger.info(f"Mixing instrumental with backing vocals: {len(tracks_to_mix)} tracks")
        return FFmpegUtils.mix_tracks(tracks_to_mix, output_path)
