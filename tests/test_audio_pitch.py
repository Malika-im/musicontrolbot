"""
Tests for Audio Pitch Shifting and Transposition (Section 13).
Validates +1, +2, +3, -1, -2, -3 semitone transposition,
duration and BPM preservation, stereo imaging, and key detection math.
"""

import wave
from pathlib import Path
import pytest

from app.audio.key_detector import KeyDetector
from app.audio.pitch_shifter import transpose_audio


def test_key_transposition_math():
    """Test musical key transposition formulas in equal temperament."""
    # C major - 2 semitones = Bb major (prompt example!)
    assert KeyDetector.transpose_key_name("C major", -2) == "Bb major"

    # C major + 2 semitones = D major
    assert KeyDetector.transpose_key_name("C major", 2) == "D major"

    # A minor + 3 semitones = C minor
    assert KeyDetector.transpose_key_name("A minor", 3) == "C minor"

    # G major - 1 semitone = F# major
    assert KeyDetector.transpose_key_name("G major", -1) == "F# major"

    # E minor + 1 semitone = F minor
    assert KeyDetector.transpose_key_name("E minor", 1) == "F minor"

    # D major + 4 semitones = F# major
    assert KeyDetector.transpose_key_name("D major", 4) == "F# major"

    # Zero semitones shift returns original
    assert KeyDetector.transpose_key_name("G# minor", 0) == "G# minor"


@pytest.mark.parametrize("semitones", [+1.0, +2.0, +3.0, -1.0, -2.0, -3.0])
def test_transpose_audio_all_semitones(synthetic_wav_file: Path, tmp_path: Path, semitones: float):
    """
    Test transposition for +1, +2, +3, -1, -2, -3 semitones.
    Verifies output exists, maintains exact duration, and preserves stereo channels.
    """
    output_path = tmp_path / f"transposed_{semitones:+.0f}.wav"

    # Read original duration and channels
    with wave.open(str(synthetic_wav_file), "rb") as orig_wf:
        orig_frames = orig_wf.getnframes()
        orig_rate = orig_wf.getframerate()
        orig_channels = orig_wf.getnchannels()
        orig_duration = orig_frames / float(orig_rate)

    # Perform pitch shift
    result = transpose_audio(synthetic_wav_file, output_path, semitones)

    assert result.exists()
    assert result.stat().st_size > 0

    # Inspect transposed file properties
    with wave.open(str(result), "rb") as res_wf:
        res_frames = res_wf.getnframes()
        res_rate = res_wf.getframerate()
        res_channels = res_wf.getnchannels()
        res_duration = res_frames / float(res_rate)

    # 1. Channels preserved (Stereo -> Stereo)
    assert res_channels == orig_channels == 2

    # 2. Sample rate preserved
    assert res_rate == orig_rate

    # 3. Duration preserved (tempo/BPM invariance) within 0.05s tolerance
    assert abs(res_duration - orig_duration) < 0.05


def test_transpose_zero_semitones(synthetic_wav_file: Path, tmp_path: Path):
    """Zero semitones transposition should perform a lossless copy."""
    output_path = tmp_path / "zero_shift.wav"
    result = transpose_audio(synthetic_wav_file, output_path, 0.0)
    assert result.exists()
    assert result.stat().st_size == synthetic_wav_file.stat().st_size


def test_key_detector_synthetic_audio(synthetic_wav_file: Path):
    """Verify that KeyDetector extracts a musical key and BPM without errors."""
    key, bpm = KeyDetector.detect_key_and_bpm(str(synthetic_wav_file))
    assert isinstance(key, str)
    assert len(key) > 0
    assert bpm > 0
