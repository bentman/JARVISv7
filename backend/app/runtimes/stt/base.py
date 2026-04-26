from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np


STT_DEVICES = {"cpu", "cuda", "directml", "qnn"}


class STTBase(ABC):
    def __init__(self, device: str, model_path: Path) -> None:
        if device not in STT_DEVICES:
            allowed = ", ".join(sorted(STT_DEVICES))
            raise ValueError(f"unsupported STT device '{device}'; expected one of: {allowed}")
        self.device = device
        self.model_path = model_path

    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError