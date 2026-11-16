"""
Tests for Audio Validation Service and SSRF Security Guard.
"""

from pathlib import Path
import pytest

from app.core.exceptions import AudioValidationError, SSRFSecurityError
from app.core.security import validate_safe_url
from app.services.audio_validation_service import AudioValidationService


def test_filename_sanitization():
    validator = AudioValidationService()

    # Directory traversal prevention
    assert validator.sanitize_filename("../../../secret/song.mp3") == "song.mp3"
    assert validator.sanitize_filename("..\\..\\Windows\\System32\\cmd.exe") == "cmd.exe"

    # Dangerous characters removal
    dirty = "my_track; rm -rf /; $(whoami).mp3"
    clean = validator.sanitize_filename(dirty)
    assert ";" not in clean
    assert "$" not in clean
    assert "/" not in clean


def test_file_size_validation(tmp_path: Path):
    validator = AudioValidationService()

    # 1. Empty file
    empty_file = tmp_path / "empty.wav"
    empty_file.write_bytes(b"")
    with pytest.raises(AudioValidationError, match="пуст"):
        validator.validate_file_size(empty_file)

    # 2. Valid file
    normal_file = tmp_path / "normal.wav"
    normal_file.write_bytes(b"RIFF" + b"\x00" * 100)
    assert validator.validate_file_size(normal_file) == 104

    # 3. Oversized file (> 50 MB)
    large_file = tmp_path / "large.wav"
    validator.settings.MAX_FILE_SIZE_MB = 1  # 1 MB threshold for test
    large_file.write_bytes(b"0" * (2 * 1024 * 1024))
    with pytest.raises(AudioValidationError, match="превышает лимит"):
        validator.validate_file_size(large_file)


def test_format_detection_from_magic_bytes(tmp_path: Path):
    validator = AudioValidationService()

    wav_file = tmp_path / "test.wav"
    wav_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    assert validator.detect_format_from_bytes(wav_file) == "wav"

    flac_file = tmp_path / "test.flac"
    flac_file.write_bytes(b"fLaC\x00\x00\x00\x22")
    assert validator.detect_format_from_bytes(flac_file) == "flac"

    mp3_file = tmp_path / "test.mp3"
    mp3_file.write_bytes(b"ID3\x03\x00\x00\x00")
    assert validator.detect_format_from_bytes(mp3_file) == "mp3"

    m4a_file = tmp_path / "test.m4a"
    m4a_file.write_bytes(b"\x00\x00\x00\x20ftypM4A ")
    assert validator.detect_format_from_bytes(m4a_file) == "m4a"

    invalid_file = tmp_path / "bad.bin"
    invalid_file.write_bytes(b"MZ\x90\x00\x03\x00\x00\x00")
    with pytest.raises(AudioValidationError, match="формат"):
        validator.detect_format_from_bytes(invalid_file)


def test_ssrf_security_guard():
    # 1. Non-http scheme rejected
    with pytest.raises(SSRFSecurityError, match="протокол"):
        validate_safe_url("file:///etc/passwd")

    with pytest.raises(SSRFSecurityError, match="протокол"):
        validate_safe_url("ftp://example.com/audio.mp3")

    # 2. Localhost and loopback rejected
    with pytest.raises(SSRFSecurityError, match="хосту"):
        validate_safe_url("http://localhost/song.mp3")

    with pytest.raises(SSRFSecurityError, match="хосту"):
        validate_safe_url("http://127.0.0.1:8000/api/song.mp3")

    # 3. Cloud metadata rejected
    with pytest.raises(SSRFSecurityError):
        validate_safe_url("http://169.254.169.254/latest/meta-data")
