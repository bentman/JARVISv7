from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from backend.app.models.catalog import get_model_path
from backend.app.runtimes.stt.base import STTBase


QNN_STT_DEFERRED_REASON = "QNN STT inference deferred to H.2"


def providers_for_device(device: str) -> list[str]:
    if device == "cpu":
        return ["CPUExecutionProvider"]
    if device == "cuda":
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if device == "directml":
        return ["DmlExecutionProvider", "CPUExecutionProvider"]
    if device == "qnn":
        return []
    raise ValueError(f"unsupported STT device '{device}'")


class OnnxWhisperRuntime(STTBase):
    def __init__(
        self,
        device: str = "cpu",
        model_path: Path | None = None,
        model_name: str = "whisper-small-onnx",
    ) -> None:
        super().__init__(device=device, model_path=model_path or get_model_path("stt", model_name))
        self.model_name = model_name
        self.providers = providers_for_device(device)
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self.device == "qnn":
            raise NotImplementedError(QNN_STT_DEFERRED_REASON)
        if self._model is None:
            import onnx_asr

            self._model = onnx_asr.load_model(
                "onnx-community/whisper-small",
                path=self.model_path,
                providers=self.providers,
            )
        return self._model

    def is_available(self) -> bool:
        if self.device == "qnn":
            return False
        required = (
            "encoder_model.onnx",
            "decoder_model_merged.onnx",
            "config.json",
            "generation_config.json",
            "preprocessor_config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "vocab.json",
            "merges.txt",
            "normalizer.json",
            "added_tokens.json",
        )
        return all((self.model_path / filename).is_file() for filename in required)

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if self.device == "qnn":
            raise NotImplementedError(QNN_STT_DEFERRED_REASON)
        if not self.is_available():
            raise RuntimeError(f"STT model files are unavailable at {self.model_path}")
        waveform = np.asarray(audio, dtype=np.float32)
        result = self._load_model().recognize(waveform, sample_rate=sample_rate)
        if isinstance(result, str):
            return result
        return str(result)