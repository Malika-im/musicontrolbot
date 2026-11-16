"""
Whisper Speech Recognition Engine.
Transcribes audio and extracts word-level timestamps using OpenAI Whisper.
Enables word-level precision filtering for smart audio editing.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import re

from app.core.config import get_settings
from app.core.exceptions import SpeechRecognitionError
from app.core.logging import logger


class WhisperEngine:
    def __init__(self, model_name: Optional[str] = None):
        settings = get_settings()
        self.model_name = model_name or settings.WHISPER_MODEL
        self.device = settings.DEVICE if settings.DEVICE in ("cuda", "cpu") else "cpu"
        self._model = None
        logger.info(f"Initialized WhisperEngine (model={self.model_name}, device={self.device})")

    def _load_model(self):
        """Lazy load Whisper model."""
        if self._model is None:
            logger.info(f"Loading Whisper model '{self.model_name}' on {self.device}...")
            try:
                import whisper
                self._model = whisper.load_model(self.model_name, device=self.device)
                logger.info(f"Whisper model '{self.model_name}' loaded successfully.")
            except Exception as e:
                logger.exception(f"Failed to load Whisper model: {e}")
                raise SpeechRecognitionError(f"Ошибка загрузки модели Whisper: {e}")
        return self._model

    def transcribe_with_words(self, audio_path: Path) -> List[Dict[str, Any]]:
        """
        Transcribe audio file and return list of words with start and end timestamps.
        Each word item: {'word': str, 'start': float, 'end': float}
        """
        model = self._load_model()
        try:
            # Run Whisper with word-level timestamps enabled
            result = model.transcribe(
                str(audio_path),
                word_timestamps=True,
                verbose=False,
            )

            word_list: List[Dict[str, Any]] = []
            for segment in result.get("segments", []):
                for word_info in segment.get("words", []):
                    word_clean = word_info.get("word", "").strip()
                    if word_clean:
                        word_list.append({
                            "word": word_clean,
                            "start": float(word_info.get("start", 0.0)),
                            "end": float(word_info.get("end", 0.0)),
                        })

            logger.info(f"Whisper transcribed {len(word_list)} words from {audio_path.name}")
            return word_list

        except Exception as exc:
            logger.exception(f"Whisper transcription error: {exc}")
            raise SpeechRecognitionError(f"Ошибка распознавания речи: {exc}")

    @staticmethod
    def find_phrase_intervals(
        words: List[Dict[str, Any]],
        target_phrase: str,
    ) -> List[Tuple[float, float]]:
        """
        Find start and end timestamps where the target phrase occurs in transcribed words.
        Handles multi-word phrases and case-insensitive matching.
        """
        clean_target = re.sub(r"[^\w\s]", "", target_phrase.lower()).strip().split()
        if not clean_target or not words:
            return []

        target_len = len(clean_target)
        intervals: List[Tuple[float, float]] = []

        # Sliding window over words
        for i in range(len(words) - target_len + 1):
            window_words = [
                re.sub(r"[^\w\s]", "", w["word"].lower()).strip()
                for w in words[i : i + target_len]
            ]
            if window_words == clean_target:
                start_time = words[i]["start"]
                end_time = words[i + target_len - 1]["end"]
                intervals.append((start_time, end_time))

        logger.info(f"Found {len(intervals)} occurrences for phrase '{target_phrase}'")
        return intervals
