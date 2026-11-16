"""
Tests for Audio Separation and Stem Mixing.
"""

from pathlib import Path
import wave
from app.audio.ffmpeg_utils import FFmpegUtils
from app.services.background_vocal_service import BackgroundVocalService
from app.services.vocal_separation_service import VocalSeparationService


def test_stem_mixing_instrumental(synthetic_wav_file: Path, tmp_path: Path):
    """Test combining multiple stems into an instrumental track."""
    stem_drums = synthetic_wav_file
    stem_bass = synthetic_wav_file
    output_mix = tmp_path / "mixed_instrumental.wav"

    result = FFmpegUtils.mix_tracks([stem_drums, stem_bass], output_mix)
    assert result.exists()
    assert result.stat().st_size > 0

    with wave.open(str(result), "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getframerate() == 22050


def test_backing_vocal_mid_side_separation(synthetic_wav_file: Path, tmp_path: Path):
    """Test Mid/Side spectral decomposition into lead voice and backing vocals."""
    vocal_service = BackgroundVocalService()
    lead_out = tmp_path / "lead.wav"
    backing_out = tmp_path / "backing.wav"

    vocal_service.backing_vocal_engine.separate_lead_and_backing(
        vocal_stem_path=synthetic_wav_file,
        lead_output_path=lead_out,
        backing_output_path=backing_out,
    )

    assert lead_out.exists()
    assert backing_out.exists()
    assert lead_out.stat().st_size > 0
    assert backing_out.stat().st_size > 0
