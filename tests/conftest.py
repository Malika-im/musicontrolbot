"""
Pytest Fixtures and Test Setup.
Generates synthetic WAV audio files and provides test database sessions and FastAPI test client.
"""

import math
import struct
import wave
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_application


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Return test configuration settings."""
    settings = get_settings()
    settings.ENVIRONMENT = "test"
    settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"
    settings.DATABASE_SYNC_URL = "sqlite:///:memory:"
    settings.TELEGRAM_WEBHOOK_SECRET = "test_webhook_secret_12345"
    return settings


@pytest.fixture(scope="session")
def synthetic_wav_file(tmp_path_factory) -> Path:
    """
    Generate a 3-second 440 Hz stereo test audio file (WAV format)
    using only Python standard library (wave & struct).
    """
    tmp_dir = tmp_path_factory.mktemp("audio_test")
    wav_path = tmp_dir / "test_stereo_song.wav"

    sample_rate = 22050
    duration_sec = 3.0
    num_samples = int(sample_rate * duration_sec)
    freq_left = 440.0   # A4
    freq_right = 554.37  # C#5

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)  # Stereo
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)

        frames = bytearray()
        for i in range(num_samples):
            t = float(i) / sample_rate
            # Generate left and right channels
            val_left = int(16000 * math.sin(2.0 * math.pi * freq_left * t))
            val_right = int(16000 * math.sin(2.0 * math.pi * freq_right * t))
            frames.extend(struct.pack("<hh", val_left, val_right))

        wf.writeframes(frames)

    return wav_path


@pytest.fixture
def client(test_settings) -> Generator[TestClient, None, None]:
    """Test client for FastAPI endpoints."""
    app = create_application()
    with TestClient(app) as test_client:
        yield test_client
