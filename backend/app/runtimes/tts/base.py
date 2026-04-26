from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np


TTS_DEVICES = {"cpu", "cuda", "directml"}


class TTSBase(ABC):
    def __init__(self, device: str, model_path: Path) -> None:
        if device not in TTS_DEVICES:
            allowed = ", ".join(sorted(TTS_DEVICES))
            raise ValueError(f"unsupported TTS device '{device}'; expected one of: {allowed}")
        self.device = device
        self.model_path = model_path

    @abstractmethod
    def synthesize(self, text: str) -> np.ndarray:
        raise NotImplementedError

    @abstractmethod
    def sample_rate(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError