from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from backend.app.models.catalog import get_model_path
from backend.app.runtimes.tts.base import TTSBase


KOKORO_SAMPLE_RATE = 24000
PROVIDER_OVERRIDE_MISSING_REASON = "provider-override-missing"


def _provider_for_device(device: str) -> str | None:
    if device == "cuda":
        return "CUDAExecutionProvider"
    if device == "directml":
        return "DmlExecutionProvider"
    if device == "qnn":
        return "QNNExecutionProvider"
    return None


class KokoroOnnxRuntime(TTSBase):
    def __init__(
        self,
        device: str = "cpu",
        model_path: Path | None = None,
        model_name: str | None = None,
        voice: str = "af_heart",
    ) -> None:
        super().__init__(device=device, model_path=model_path or get_model_path("tts", model_name))
        self.model_name = model_name
        self.voice = voice
        self._model: Any | None = None
        self._sample_rate = KOKORO_SAMPLE_RATE

    @property
    def onnx_path(self) -> Path:
        return self.model_path / "kokoro-v1.0.onnx"

    @property
    def voices_path(self) -> Path:
        return self.model_path / "voices-v1.0.bin"

    def is_available(self) -> bool:
        return self.onnx_path.is_file() and self.voices_path.is_file()

    def _load_model(self) -> Any:
        if self._model is None:
            if not self.is_available():
                raise RuntimeError(f"TTS model files are unavailable at {self.model_path}")
            from kokoro_onnx import Kokoro
            import inspect

            provider_name = _provider_for_device(self.device)
            if provider_name is not None:
                signature = inspect.signature(Kokoro.__init__)
                if "providers" not in signature.parameters:
                    raise RuntimeError(
                        f"{PROVIDER_OVERRIDE_MISSING_REASON}: kokoro_onnx.Kokoro does not expose providers override"
                    )

            self._model = Kokoro(str(self.onnx_path), str(self.voices_path))
        return self._model

    def synthesize(self, text: str) -> np.ndarray:
        audio, sample_rate = self._load_model().create(text, voice=self.voice)
        self._sample_rate = int(sample_rate)
        return np.asarray(audio, dtype=np.float32)

    def sample_rate(self) -> int:
        return self._sample_rate