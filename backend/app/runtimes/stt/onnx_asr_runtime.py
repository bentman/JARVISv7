from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.runtimes.stt.base import STTBase


class OnnxAsrRuntime(STTBase):
    def __init__(self, device: str = "cpu", model_path: Path | None = None) -> None:
        super().__init__(device=device, model_path=model_path or Path("models/stt/parakeet-tdt"))
        self.reason = "onnx-asr secondary STT runtime is boundary-only in B.1"

    def is_available(self) -> bool:
        return False

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        raise RuntimeError(self.reason)