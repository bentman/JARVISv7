from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True, slots=True)
class VADDecision:
    speech: bool
    probability: float
    rms: float


class VADRuntime(Protocol):
    def detect(self, samples: np.ndarray, sample_rate: int) -> VADDecision:
        """Return a deterministic speech decision for one audio chunk."""


def normalize_audio_samples(samples: np.ndarray) -> np.ndarray:
    audio = np.asarray(samples).reshape(-1)
    if np.issubdtype(audio.dtype, np.signedinteger):
        info = np.iinfo(audio.dtype)
        scale = float(max(abs(info.min), info.max))
        return audio.astype(np.float32) / scale
    return audio.astype(np.float32, copy=False)
