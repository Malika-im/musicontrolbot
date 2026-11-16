"""
Backing Vocal Separation Engine.
Splits an isolated vocal track into Lead Vocals (solo voice) and Backing Vocals (harmonies/ad-libs).
Uses Mid/Side spatial decomposition and spectral difference filtering.
"""

from pathlib import Path
from typing import Tuple

from app.core.exceptions import AudioSeparationError
from app.core.logging import logger


class BackingVocalEngine:
    """
    Separates lead vocals and backing vocals from an already isolated vocal stem.
    """

    @staticmethod
    def separate_lead_and_backing(
        vocal_stem_path: Path,
        lead_output_path: Path,
        backing_output_path: Path,
    ) -> Tuple[Path, Path]:
        """
        Takes an isolated vocal track (WAV/MP3) and produces two tracks:
        1. Lead vocals (centered primary soloist)
        2. Backing vocals (stereo harmonies, choir, ad-libs)
        """
        try:
            import numpy as np
            import soundfile as sf
            import librosa

            # Load vocal stem
            data, sr = librosa.load(str(vocal_stem_path), sr=None, mono=False)

            if data.ndim == 1:
                logger.warning("Mono vocal stem provided: lead and backing separation cannot use stereo cues.")
                lead_output_path.parent.mkdir(parents=True, exist_ok=True)
                backing_output_path.parent.mkdir(parents=True, exist_ok=True)
                sf.write(str(lead_output_path), data, sr)
                sf.write(str(backing_output_path), np.zeros_like(data), sr)
                return lead_output_path, backing_output_path

            left = data[0]
            right = data[1]

            # Mid / Side decomposition
            mid = 0.5 * (left + right)
            side = 0.5 * (left - right)

            # Compute Short-Time Fourier Transform (STFT)
            n_fft = 2048
            hop_length = 512
            d_mid = librosa.stft(mid, n_fft=n_fft, hop_length=hop_length)
            d_side = librosa.stft(side, n_fft=n_fft, hop_length=hop_length)

            mag_mid, phase_mid = np.abs(d_mid), np.angle(d_mid)
            mag_side, phase_side = np.abs(d_side), np.angle(d_side)

            # Backing vocal mask: regions where side energy is prominent relative to mid
            # Lead vocal mask: regions where mid energy dominates
            epsilon = 1e-6
            side_ratio = mag_side / (mag_mid + epsilon)

            # Soft sigmoid mask for backing vocals
            backing_mask = 1.0 / (1.0 + np.exp(-3.0 * (side_ratio - 0.35)))
            backing_mask = np.clip(backing_mask, 0.0, 1.0)

            lead_mask = 1.0 - backing_mask

            # Synthesize isolated spectral magnitudes
            lead_stft = (mag_mid * lead_mask) * np.exp(1j * phase_mid)
            lead_mono = librosa.istft(lead_stft, hop_length=hop_length, length=len(mid))

            # Reconstruct stereo lead (centered)
            lead_stereo = np.stack([lead_mono, lead_mono], axis=0)

            # Backing vocals include both the prominent side channel and masked mid harmonics
            backing_left = librosa.istft(
                ((mag_mid * backing_mask) * np.exp(1j * phase_mid)) + d_side,
                hop_length=hop_length,
                length=len(left),
            )
            backing_right = librosa.istft(
                ((mag_mid * backing_mask) * np.exp(1j * phase_mid)) - d_side,
                hop_length=hop_length,
                length=len(right),
            )
            backing_stereo = np.stack([backing_left, backing_right], axis=0)

            # Anti-clipping normalization
            for audio_arr in [lead_stereo, backing_stereo]:
                peak = float(np.max(np.abs(audio_arr)))
                if peak > 0.98:
                    audio_arr *= 0.95 / peak

            lead_output_path.parent.mkdir(parents=True, exist_ok=True)
            backing_output_path.parent.mkdir(parents=True, exist_ok=True)

            sf.write(str(lead_output_path), lead_stereo.T, sr)
            sf.write(str(backing_output_path), backing_stereo.T, sr)

            logger.info(f"Successfully separated lead vocals ({lead_output_path.name}) and backing vocals ({backing_output_path.name})")
            return lead_output_path, backing_output_path

        except Exception as exc:
            logger.exception(f"Error separating lead and backing vocals: {exc}")
            raise AudioSeparationError(f"Ошибка разделения бэк-вокала: {exc}")
