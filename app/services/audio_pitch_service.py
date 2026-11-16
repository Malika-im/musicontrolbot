"""
Audio Pitch Shifting and Harmony Service.
Manages key/scale/BPM detection, musical transposition (+/- semitones),
and quality checks (duration invariance, clipping avoidance).
"""

from pathlib import Path
from typing import Optional, Tuple
from app.audio.key_detector import KeyDetector
from app.audio.pitch_shifter import transpose_audio
from app.core.exceptions import PitchShiftError
from app.core.logging import logger


class AudioPitchService:
    def __init__(self):
        self.key_detector = KeyDetector()

    def analyze_musical_profile(self, audio_path: Path) -> Tuple[str, float]:
        """
        Detects musical key and BPM from audio.
        Returns (detected_key, detected_bpm), e.g. ("C major", 124.0).
        """
        if not audio_path.exists():
            raise PitchShiftError(f"Файл {audio_path} не существует.")
        key, bpm = self.key_detector.detect_key_and_bpm(str(audio_path))
        logger.info(f"Analyzed {audio_path.name}: key='{key}', bpm={bpm}")
        return key, bpm

    def calculate_new_key(self, original_key: str, semitones: float) -> str:
        """Calculate resulting musical key after shifting by `semitones`."""
        return self.key_detector.transpose_key_name(original_key, int(round(semitones)))

    def transpose(
        self,
        input_path: Path,
        output_path: Path,
        semitones: float,
        original_key: Optional[str] = None,
    ) -> Tuple[Path, str, str]:
        """
        Transposes audio by `semitones` while maintaining tempo, BPM, and duration.
        Returns (output_path, original_key, resulting_key).
        """
        # Determine original key if not already known
        orig_key = original_key
        if not orig_key or "Unknown" in orig_key:
            orig_key, _ = self.analyze_musical_profile(input_path)

        res_key = self.calculate_new_key(orig_key, semitones)

        logger.info(f"Transposing {input_path.name}: {semitones:+.1f} semitones ({orig_key} -> {res_key})")
        result_file = transpose_audio(
            input_path=input_path,
            output_path=output_path,
            semitones=semitones,
        )

        return result_file, orig_key, res_key
