"""
Audio Effects and Time-Interval Masking.
Performs smooth crossfades, muting, or isolating specific time intervals
(e.g. for keeping or removing words identified by Whisper).
"""

from pathlib import Path
from typing import List, Tuple

from app.core.exceptions import MusicBotException
from app.core.logging import logger


class AudioEffects:
    @staticmethod
    def apply_time_masks(
        input_path: Path,
        output_path: Path,
        mute_intervals: List[Tuple[float, float]],
        fade_ms: float = 15.0,
    ) -> Path:
        """
        Mute specific time intervals in the audio file with smooth crossfade envelopes.
        Used for removing swear words, censoring phrases, or deleting verse vocals.

        :param input_path: Input audio file
        :param output_path: Output audio file
        :param mute_intervals: List of (start_sec, end_sec) tuples to silence
        :param fade_ms: Duration of linear fade in/out in milliseconds to prevent audio clicks
        """
        if not mute_intervals:
            import shutil
            shutil.copyfile(input_path, output_path)
            return output_path

        import numpy as np
        import soundfile as sf
        import librosa

        data, sr = librosa.load(str(input_path), sr=None, mono=False)
        total_samples = data.shape[-1]
        fade_samples = int((fade_ms / 1000.0) * sr)

        # Create gain envelope (1.0 everywhere, fading to 0.0 inside mute intervals)
        envelope = np.ones(total_samples, dtype=np.float32)

        for start_sec, end_sec in mute_intervals:
            start_idx = max(0, int(start_sec * sr))
            end_idx = min(total_samples, int(end_sec * sr))

            if start_idx >= end_idx:
                continue

            # Zero out interval
            envelope[start_idx:end_idx] = 0.0

            # Fade out before start_idx
            if fade_samples > 0 and start_idx > fade_samples:
                fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
                envelope[start_idx - fade_samples : start_idx] = fade_out

            # Fade in after end_idx
            if fade_samples > 0 and end_idx + fade_samples < total_samples:
                fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
                envelope[end_idx : end_idx + fade_samples] = fade_in

        # Apply envelope
        if data.ndim == 1:
            processed = data * envelope
            out_data = processed
        else:
            processed = data * envelope[np.newaxis, :]
            out_data = processed.T

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), out_data, sr)
        logger.info(f"Applied {len(mute_intervals)} mute masks with {fade_ms}ms crossfade to {output_path.name}")
        return output_path

    @staticmethod
    def apply_keep_intervals(
        input_path: Path,
        output_path: Path,
        keep_intervals: List[Tuple[float, float]],
        fade_ms: float = 15.0,
    ) -> Path:
        """
        Keep only the specified intervals (e.g. 'leave only the words I love you' or 'leave chorus only'),
        muting everything else.
        """
        import soundfile as sf
        import librosa

        data, sr = librosa.load(str(input_path), sr=None, mono=False)
        total_duration = data.shape[-1] / float(sr)

        # Invert keep_intervals into mute_intervals
        sorted_intervals = sorted(keep_intervals, key=lambda x: x[0])
        mute_intervals = []
        current_time = 0.0

        for start, end in sorted_intervals:
            if start > current_time:
                mute_intervals.append((current_time, start))
            current_time = max(current_time, end)

        if current_time < total_duration:
            mute_intervals.append((current_time, total_duration))

        return AudioEffects.apply_time_masks(input_path, output_path, mute_intervals, fade_ms)
