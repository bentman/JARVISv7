from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np


class WakeBase(ABC):
    def __init__(self, device: str, model_path: Path) -> None:
        if device != "cpu":
            raise ValueError("wake runtime supports only device='cpu' in Slice B")
        self.device = device
        self.model_path = model_path

    @abstractmethod
    def detect(self, audio_chunk: np.ndarray) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError