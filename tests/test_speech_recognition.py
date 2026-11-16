"""
Tests for Speech Recognition and Word-Level Audio Masking (Stage 7).
"""

from pathlib import Path
import wave
from app.ai.whisper_engine import WhisperEngine
from app.audio.audio_effects import AudioEffects


def test_whisper_phrase_locator():
    """Test locating multi-word phrases within timestamped word stream."""
    sample_words = [
        {"word": "Привет,", "start": 0.5, "end": 0.9},
        {"word": "я", "start": 1.0, "end": 1.2},
        {"word": "тебя", "start": 1.3, "end": 1.6},
        {"word": "люблю", "start": 1.7, "end": 2.1},
        {"word": "очень", "start": 2.2, "end": 2.5},
    ]

    intervals = WhisperEngine.find_phrase_intervals(sample_words, "я тебя люблю")
    assert len(intervals) == 1
    start, end = intervals[0]
    assert start == 1.0
    assert end == 2.1


def test_audio_effects_mute_intervals(synthetic_wav_file: Path, tmp_path: Path):
    """Test muting specific intervals with crossfade envelope."""
    output_path = tmp_path / "muted.wav"
    mute_intervals = [(0.5, 1.5)]

    result = AudioEffects.apply_time_masks(
        input_path=synthetic_wav_file,
        output_path=output_path,
        mute_intervals=mute_intervals,
        fade_ms=10.0,
    )

    assert result.exists()
    assert result.stat().st_size > 0

    with wave.open(str(result), "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getnframes() > 0


def test_audio_effects_keep_intervals(synthetic_wav_file: Path, tmp_path: Path):
    """Test keeping only specified phrase intervals."""
    output_path = tmp_path / "kept.wav"
    keep_intervals = [(1.0, 2.0)]

    result = AudioEffects.apply_keep_intervals(
        input_path=synthetic_wav_file,
        output_path=output_path,
        keep_intervals=keep_intervals,
        fade_ms=10.0,
    )

    assert result.exists()
    assert result.stat().st_size > 0
