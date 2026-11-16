"""
Speech Recognition Service.
Coordinates Whisper transcription and phrase timestamp discovery.
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple
from app.ai.whisper_engine import WhisperEngine
from app.core.exceptions import SpeechRecognitionError
from app.core.logging import logger


class SpeechRecognitionService:
    def __init__(self, whisper_engine: WhisperEngine | None = None):
        self.whisper_engine = whisper_engine or WhisperEngine()

    def get_word_timestamps(self, audio_path: Path) -> List[Dict[str, Any]]:
        """Transcribe audio and obtain timestamped word list."""
        if not audio_path.exists():
            raise SpeechRecognitionError(f"Файл {audio_path} не существует.")
        return self.whisper_engine.transcribe_with_words(audio_path)

    def locate_phrases(
        self,
        audio_path: Path,
        phrases: List[str],
        cached_words: List[Dict[str, Any]] | None = None,
    ) -> List[Tuple[float, float]]:
        """
        Locate all occurrences of target phrases in the audio file.
        Returns list of (start_sec, end_sec) tuples.
        """
        words = cached_words or self.get_word_timestamps(audio_path)
        all_intervals: List[Tuple[float, float]] = []

        for phrase in phrases:
            intervals = self.whisper_engine.find_phrase_intervals(words, phrase)
            all_intervals.extend(intervals)

        logger.info(f"Located {len(all_intervals)} total intervals for phrases {phrases}")
        return all_intervals
