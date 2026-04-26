from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from backend.app.runtimes.wake.base import WakeBase


class PorcupineRuntime(WakeBase):
    def __init__(self, device: str = "cpu", model_path: Path | None = None) -> None:
        super().__init__(device=device, model_path=model_path or Path("models/wake/porcupine"))
        self.reason = "PICOVOICE_ACCESS_KEY not set"

    def is_available(self) -> bool:
        if os.getenv("PICOVOICE_ACCESS_KEY"):
            self.reason = "Porcupine structural slot present; live validation not required in B.4"
            return True
        self.reason = "PICOVOICE_ACCESS_KEY not set"
        return False

    def detect(self, audio_chunk: np.ndarray) -> bool:
        raise RuntimeError("Porcupine wake runtime is structural only in B.4")