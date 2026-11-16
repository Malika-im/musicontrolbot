"""
FFmpeg and Audio File Manipulation Utilities.
Provides format conversions, stem mixing, video audio extraction, and audio probing.
Includes pure-Python fallback for environments where ffmpeg binary is not in PATH.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from app.core.exceptions import MusicBotException
from app.core.logging import logger


class FFmpegUtils:
    @staticmethod
    def is_ffmpeg_available() -> bool:
        """Check if ffmpeg executable exists in system PATH."""
        return shutil.which("ffmpeg") is not None

    @staticmethod
    def convert_audio(
        input_path: Path,
        output_path: Path,
        bitrate: str = "192k",
        sample_rate: int = 44100,
    ) -> Path:
        """
        Convert audio file to target format (e.g. MP3/WAV/OGG).
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if FFmpegUtils.is_ffmpeg_available():
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(input_path),
                "-vn",
                "-ar", str(sample_rate),
                "-b:a", bitrate,
                str(output_path),
            ]
            try:
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                return output_path
            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg conversion failed: {e.stderr.decode('utf-8', errors='ignore')}")

        # Pythonic fallback using soundfile & librosa
        try:
            import soundfile as sf
            import librosa
            data, sr = librosa.load(str(input_path), sr=sample_rate, mono=False)
            out_data = data.T if data.ndim > 1 else data
            sf.write(str(output_path), out_data, sr)
            return output_path
        except Exception as exc:
            raise MusicBotException(f"Ошибка конвертации аудио: {exc}")

    @staticmethod
    def extract_audio_from_video(video_path: Path, output_audio_path: Path) -> Path:
        """
        Extract audio stream from video container (MP4, MOV, MKV, etc.).
        """
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)

        if FFmpegUtils.is_ffmpeg_available():
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-vn",
                "-acodec", "libmp3lame",
                "-q:a", "2",
                str(output_audio_path),
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return output_audio_path

        # Python fallback via soundfile/librosa if audio stream can be read
        try:
            import soundfile as sf
            import librosa
            data, sr = librosa.load(str(video_path), sr=44100, mono=False)
            sf.write(str(output_audio_path), data.T if data.ndim > 1 else data, sr)
            return output_audio_path
        except Exception as exc:
            raise MusicBotException(f"Не удалось извлечь звук из видео: {exc}")

    @staticmethod
    def mix_tracks(
        input_paths: List[Path],
        output_path: Path,
        weights: Optional[List[float]] = None,
    ) -> Path:
        """
        Mix multiple audio stems together into a single unified audio file.
        Used for creating instrumental backing tracks (drums + bass + other),
        or combining isolated vocals with accompaniment.
        """
        if not input_paths:
            raise MusicBotException("Список дорожек для сведения пуст.")

        if len(input_paths) == 1 and not weights:
            shutil.copyfile(input_paths[0], output_path)
            return output_path

        import numpy as np
        import soundfile as sf
        import librosa

        # Load all stems
        stem_arrays = []
        target_sr = None
        max_length = 0

        for path in input_paths:
            data, sr = librosa.load(str(path), sr=None, mono=False)
            if target_sr is None:
                target_sr = sr
            if data.shape[-1] > max_length:
                max_length = data.shape[-1]
            stem_arrays.append(data)

        # Equalize weights if not specified
        stem_weights = weights if weights and len(weights) == len(input_paths) else [1.0] * len(input_paths)

        # Pad and mix
        mixed = None
        for data, weight in zip(stem_arrays, stem_weights):
            if data.shape[-1] < max_length:
                if data.ndim == 1:
                    data = np.pad(data, (0, max_length - data.shape[-1]))
                else:
                    data = np.pad(data, ((0, 0), (0, max_length - data.shape[-1])))

            weighted_data = data * weight
            if mixed is None:
                mixed = weighted_data.astype(np.float32)
            else:
                mixed += weighted_data.astype(np.float32)

        peak = float(np.max(np.abs(mixed)))
        if peak > 0.98:
            mixed = mixed * (0.95 / peak)

        out_data = mixed.T if mixed.ndim > 1 else mixed
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), out_data, target_sr)

        logger.info(f"Mixed {len(input_paths)} stems into {output_path.name}")
        return output_path
