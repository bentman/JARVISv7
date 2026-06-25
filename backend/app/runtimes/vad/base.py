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
