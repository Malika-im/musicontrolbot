"""
High-Fidelity Audio Pitch Shifting Module.
Shifts audio pitch by musical semitones while preserving exact tempo (BPM),
duration, rhythm, and stereo imaging.
"""

from pathlib import Path
from typing import Union

from app.core.exceptions import PitchShiftError
from app.core.logging import logger


def transpose_audio(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    semitones: float,
) -> Path:
    """
    Transpose audio file by specified number of musical semitones.
    Positive semitones = higher pitch, Negative semitones = lower pitch.
    Preserves exact duration, tempo (BPM), and stereo channels.

    :param input_path: Source audio file path
    :param output_path: Target audio file path
    :param semitones: Float / int number of semitones (-12 to +12)
    :return: Path to resulting audio file
    """
    input_p = Path(input_path)
    output_p = Path(output_path)

    if not input_p.exists():
        raise PitchShiftError(f"Исходный файл не найден: {input_p}")

    if abs(semitones) < 0.01:
        # Zero shift: direct copy
        import shutil
        shutil.copyfile(input_p, output_p)
        logger.info(f"0 semitones shift requested. Copied {input_p} directly to {output_p}")
        return output_p

    try:
        import numpy as np
        import soundfile as sf
        import librosa

        # Load audio with native sample rate and all channels (preserving stereo)
        audio_data, sr = librosa.load(str(input_p), sr=None, mono=False)
        orig_length = audio_data.shape[-1]

        # Shift audio pitch while keeping duration and tempo invariant
        if audio_data.ndim == 1:
            # Mono channel
            shifted = librosa.effects.pitch_shift(
                audio_data,
                sr=sr,
                n_steps=semitones,
                bins_per_octave=12,
            )
            if len(shifted) > orig_length:
                shifted = shifted[:orig_length]
            elif len(shifted) < orig_length:
                shifted = np.pad(shifted, (0, orig_length - len(shifted)))

            peak = float(np.max(np.abs(shifted)))
            if peak > 0.98:
                shifted = shifted * (0.95 / peak)

            out_data = shifted
        else:
            # Multi-channel (stereo)
            channels = []
            for ch in range(audio_data.shape[0]):
                ch_shifted = librosa.effects.pitch_shift(
                    audio_data[ch],
                    sr=sr,
                    n_steps=semitones,
                    bins_per_octave=12,
                )
                if len(ch_shifted) > orig_length:
                    ch_shifted = ch_shifted[:orig_length]
                elif len(ch_shifted) < orig_length:
                    ch_shifted = np.pad(ch_shifted, (0, orig_length - len(ch_shifted)))
                channels.append(ch_shifted)

            shifted = np.stack(channels, axis=0)
            peak = float(np.max(np.abs(shifted)))
            if peak > 0.98:
                shifted = shifted * (0.95 / peak)

            out_data = shifted.T

        output_p.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_p), out_data, sr)

        logger.info(
            f"Successfully transposed {input_p.name} by {semitones:+.1f} semitones to {output_p.name} "
            f"(SR={sr}, channels={audio_data.shape[0] if audio_data.ndim > 1 else 1})"
        )
        return output_p

    except Exception as exc:
        logger.exception(f"Error during audio transposition: {exc}")
        raise PitchShiftError(
            f"Не удалось изменить тональность аудио: {exc}",
            "⚠️ Ошибка при изменении тональности композиции. Попробуйте еще раз."
        )
