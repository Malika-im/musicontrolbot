"""
Audio Mixing Service.
Coordinates mixing stems, applying word masking intervals, and generating final deliverables.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
from app.audio.audio_effects import AudioEffects
from app.audio.ffmpeg_utils import FFmpegUtils
from app.core.exceptions import MusicBotException
from app.core.logging import logger


class AudioMixingService:
    @staticmethod
    def mix_selected_stems(
        stems_dict: Dict[str, Path],
        stems_to_keep: List[str],
        output_path: Path,
    ) -> Path:
        """
        Mixes only the stems specified in stems_to_keep.
        """
        selected_paths: List[Path] = []
        for stem_name in stems_to_keep:
            if stem_name in stems_dict and stems_dict[stem_name].exists():
                selected_paths.append(stems_dict[stem_name])

        if not selected_paths:
            raise MusicBotException(f"Не найдены запрашиваемые дорожки для сведения: {stems_to_keep}")

        return FFmpegUtils.mix_tracks(selected_paths, output_path)

    @staticmethod
    def apply_word_filters(
        audio_path: Path,
        output_path: Path,
        keep_intervals: Optional[List[Tuple[float, float]]] = None,
        remove_intervals: Optional[List[Tuple[float, float]]] = None,
    ) -> Path:
        """
        Silences or isolates specific intervals.
        """
        if keep_intervals:
            return AudioEffects.apply_keep_intervals(audio_path, output_path, keep_intervals)
        elif remove_intervals:
            return AudioEffects.apply_time_masks(audio_path, output_path, remove_intervals)
        else:
            import shutil
            shutil.copyfile(audio_path, output_path)
            return output_path
