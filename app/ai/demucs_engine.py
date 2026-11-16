"""
Demucs Audio Source Separation Engine.
Integrates Facebook / Meta Research Demucs (HTDemucs) via PyTorch.
Separates mixed audio into 4 stems: vocals, drums, bass, and other.
"""

from pathlib import Path
from typing import Dict

from app.core.config import get_settings
from app.core.exceptions import AudioSeparationError
from app.core.logging import logger


class DemucsEngine:
    def __init__(self, model_name: str | None = None, device: str | None = None):
        settings = get_settings()
        self.model_name = model_name or settings.DEMUCS_MODEL
        
        # Check torch availability
        try:
            import torch
            has_cuda = torch.cuda.is_available()
        except ImportError:
            has_cuda = False

        if device:
            self.device = device
        elif settings.DEVICE == "cuda" and has_cuda:
            self.device = "cuda"
        else:
            self.device = "cpu"

        self._model = None
        logger.info(f"Initialized DemucsEngine (model={self.model_name}, device={self.device})")

    def _load_model(self):
        """Lazy load Demucs pretrained model onto designated device."""
        if self._model is None:
            logger.info(f"Loading Demucs pretrained model '{self.model_name}' on {self.device}...")
            try:
                import torch
                from demucs.pretrained import get_model
                self._model = get_model(self.model_name)
                self._model.to(self.device)
                self._model.eval()
                logger.info(f"Demucs model '{self.model_name}' loaded successfully.")
            except Exception as e:
                logger.exception(f"Failed to load Demucs model: {e}")
                raise AudioSeparationError(f"Ошибка загрузки модели Demucs: {e}")
        return self._model

    def separate(self, audio_path: Path, output_dir: Path) -> Dict[str, Path]:
        """
        Separate input audio into individual stems.
        Returns mapping of stem names to output file paths:
        e.g. {'vocals': Path, 'drums': Path, 'bass': Path, 'other': Path}
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        model = self._load_model()

        try:
            import torch
            import torchaudio
            from demucs.apply import apply_model

            # Load audio using torchaudio
            wav, sr = torchaudio.load(str(audio_path))

            if sr != model.samplerate:
                resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=model.samplerate)
                wav = resampler(wav)
                sr = model.samplerate

            if wav.shape[0] == 1:
                wav = wav.repeat(2, 1)
            elif wav.shape[0] > 2:
                wav = wav[:2, :]

            ref = wav.mean(0)
            wav = (wav - ref.mean()) / (ref.std() + 1e-8)
            wav = wav.to(self.device)

            with torch.no_grad():
                sources = apply_model(model, wav[None], device=self.device, shifts=1, split=True)

            sources = sources * (ref.std() + 1e-8) + ref.mean()

            stems: Dict[str, Path] = {}
            for name, source in zip(model.sources, sources[0]):
                source_cpu = source.cpu()
                stem_file = output_dir / f"{name}.wav"
                torchaudio.save(str(stem_file), source_cpu, sr)
                stems[name] = stem_file
                logger.debug(f"Saved stem '{name}' to {stem_file}")

            logger.info(f"Separation completed successfully for {audio_path.name}: {list(stems.keys())}")
            return stems

        except Exception as exc:
            logger.exception(f"Demucs separation execution error: {exc}")
            raise AudioSeparationError(f"Ошибка разделения аудиодорожек: {exc}")
