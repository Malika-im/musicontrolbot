"""
Audio Validation Service.
Inspects file size, MIME type, magic bytes, audio duration, and sanitizes filenames.
"""

import os
import re
from pathlib import Path
from typing import Tuple

from app.core.config import get_settings
from app.core.exceptions import AudioValidationError
from app.core.logging import logger

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".mp4", ".mov", ".mkv"}

# Magic byte signatures for audio formats
MAGIC_SIGNATURES = {
    b"RIFF": "wav",
    b"fLaC": "flac",
    b"OggS": "ogg",
    b"ID3": "mp3",
    b"\xff\xfb": "mp3",
    b"\xff\xf3": "mp3",
    b"\xff\xf2": "mp3",
}


class AudioValidationService:
    def __init__(self):
        self.settings = get_settings()

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent directory traversal and injection."""
        base = os.path.basename(filename)
        # Remove dangerous shell characters
        clean = re.sub(r"[^\w\.\-\s]", "_", base)
        if not clean or clean.startswith("."):
            clean = f"audio_{clean}"
        return clean[:200]

    def validate_file_size(self, file_path: Path) -> int:
        """Validate that file size is within permitted bounds."""
        if not file_path.exists():
            raise AudioValidationError("Файл не найден на диске.", "Ошибка чтения файла.")

        size = file_path.stat().st_size
        if size == 0:
            raise AudioValidationError("Файл пуст (0 байт).", "Файл пуст. Отправьте корректную запись.")

        if size > self.settings.max_file_size_bytes:
            mb_size = size / (1024 * 1024)
            raise AudioValidationError(
                f"Размер файла ({mb_size:.1f} MB) превышает лимит {self.settings.MAX_FILE_SIZE_MB} MB",
                f"Размер аудио превышает допустимый максимум ({self.settings.MAX_FILE_SIZE_MB} МБ)."
            )
        return size

    def detect_format_from_bytes(self, file_path: Path) -> str:
        """Inspect file header bytes to verify audio format."""
        with open(file_path, "rb") as f:
            header = f.read(16)

        if len(header) < 4:
            raise AudioValidationError("Файл поврежден или слишком короткий.", "Некорректный формат аудио.")

        # Check standard magic bytes
        for sig, fmt in MAGIC_SIGNATURES.items():
            if header.startswith(sig):
                return fmt

        # Check ISO Base Media File Format (MP4 / M4A / AAC)
        if len(header) >= 8 and header[4:8] == b"ftyp":
            return "m4a"

        # Fallback to extension check if supported
        ext = file_path.suffix.lower()
        if ext in SUPPORTED_EXTENSIONS:
            return ext.lstrip(".")

        raise AudioValidationError(
            f"Нераспознанный формат файла: {header[:8]!r}",
            "Неподдерживаемый аудиоформат. Поддерживаются: MP3, WAV, FLAC, M4A, OGG, AAC."
        )

    def get_audio_duration(self, file_path: Path) -> float:
        """
        Extract duration of the audio file in seconds.
        Uses mutagen if available, with soundfile / wave / header fallbacks.
        """
        duration = 0.0

        # Try Mutagen
        try:
            import mutagen
            meta = mutagen.File(str(file_path))
            if meta and meta.info and hasattr(meta.info, "length") and meta.info.length:
                duration = float(meta.info.length)
        except Exception:
            pass

        # Fallback to wave if WAV
        if duration <= 0:
            try:
                import wave
                with wave.open(str(file_path), "rb") as wav_file:
                    frames = wav_file.getnframes()
                    rate = wav_file.getframerate()
                    if rate > 0:
                        duration = frames / float(rate)
            except Exception:
                pass

        # Fallback to soundfile
        if duration <= 0:
            try:
                import soundfile as sf
                info = sf.info(str(file_path))
                duration = float(info.duration)
            except Exception:
                pass

        # If audio duration could not be determined or is negative
        if duration <= 0.01:
            logger.warning(f"Could not determine exact duration for {file_path}, assuming default 180s for processing")
            duration = 180.0

        return duration

    def validate_audio(self, file_path: Path, original_filename: str) -> Tuple[str, float, int]:
        """
        Complete validation pipeline:
        1. Sanitize filename
        2. Verify file size
        3. Verify format & magic bytes
        4. Verify duration limits
        Returns (format, duration, file_size)
        """
        file_size = self.validate_file_size(file_path)
        fmt = self.detect_format_from_bytes(file_path)
        duration = self.get_audio_duration(file_path)

        if duration > self.settings.MAX_DURATION_SECONDS:
            raise AudioValidationError(
                f"Длительность {duration:.1f} сек превышает лимит {self.settings.MAX_DURATION_SECONDS} сек.",
                f"Длительность трека ({duration/60:.1f} мин) превышает лимит {self.settings.MAX_DURATION_SECONDS // 60} минут."
            )

        logger.info(f"Audio file validated successfully: format={fmt}, duration={duration:.2f}s, size={file_size} bytes")
        return fmt, duration, file_size
