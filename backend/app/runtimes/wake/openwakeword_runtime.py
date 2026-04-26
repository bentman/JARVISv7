from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from backend.app.models.catalog import get_model_entry
from backend.app.runtimes.wake.base import WakeBase


WAKE_MODEL_KEY = "hey_jarvis_v0.1"
WAKE_CHUNK_SAMPLES = 1280


class OpenWakeWordRuntime(WakeBase):
    def __init__(
        self,
        device: str = "cpu",
        model_path: Path | None = None,
        threshold: float | None = None,
        model_name: str = "openwakeword-hey-jarvis",
    ) -> None:
        entry = get_model_entry("wake", model_name)
        super().__init__(device=device, model_path=model_path or entry.local_path)
        self.model_name = model_name
        self.threshold = float(threshold if threshold is not None else entry.config.get("threshold", 0.5))
        self._model: Any | None = None
        self.last_score = 0.0

    @property
    def wakeword_path(self) -> Path:
        return self.model_path / "hey_jarvis_v0.1.onnx"

    @property
    def melspec_path(self) -> Path:
        return self.model_path / "melspectrogram.onnx"

    @property
    def embedding_path(self) -> Path:
        return self.model_path / "embedding_model.onnx"

    def is_available(self) -> bool:
        return self.wakeword_path.is_file() and self.melspec_path.is_file() and self.embedding_path.is_file()

    def _load_model(self) -> Any:
        if self._model is None:
            if not self.is_available():
                raise RuntimeError(f"wake model files are unavailable at {self.model_path}")
            from openwakeword import Model

            self._model = Model(
                wakeword_models=[str(self.wakeword_path)],
                inference_framework="onnx",
                melspec_model_path=str(self.melspec_path),
                embedding_model_path=str(self.embedding_path),
            )
        return self._model

    def detect(self, audio_chunk: np.ndarray) -> bool:
        audio = np.asarray(audio_chunk, dtype=np.int16).reshape(-1)
        model = self._load_model()
        max_score = 0.0
        for start in range(0, len(audio), WAKE_CHUNK_SAMPLES):
            chunk = audio[start : start + WAKE_CHUNK_SAMPLES]
            if chunk.size == 0:
                continue
            predictions = model.predict(chunk)
            score = float(predictions.get(WAKE_MODEL_KEY, predictions.get("hey_jarvis", 0.0)))
            max_score = max(max_score, score)
        self.last_score = max_score
        return max_score >= self.threshold