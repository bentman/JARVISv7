from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

import numpy as np

TTS_DEVICES = {"cpu", "cuda", "directml", "qnn"}


class TTSBase(ABC):
    def __init__(self, device: str, model_path: Path) -> None:
        if device not in TTS_DEVICES:
            allowed = ", ".join(sorted(TTS_DEVICES))
            raise ValueError(f"unsupported TTS device '{device}'; expected one of: {allowed}")
        self.device = device
        self.model_path = model_path

    @property
    def supports_streaming(self) -> bool:
        return False

    @abstractmethod
    def synthesize(self, text: str) -> np.ndarray:
        raise NotImplementedError

    def synthesize_stream(self, text: str) -> Iterator[tuple[np.ndarray, int]]:
        """Yield chunks of (audio_chunk, sample_rate).

        Default implementation yields the full synthesized audio in a single chunk.
        """
        audio = self.synthesize(text)
        yield audio, self.sample_rate()

    @abstractmethod
    def sample_rate(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    def warmup(self) -> None:
        """Pre-load model weights and warm up execution providers."""
        pass
