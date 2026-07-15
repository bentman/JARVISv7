from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from backend.app.runtimes.vad.base import VADDecision


@dataclass(frozen=True, slots=True)
class EnergyVADRuntime:
    speech_rms_threshold: float = 0.02
    probability_rms_scale: float = 0.08

    def detect(self, samples: np.ndarray, sample_rate: int) -> VADDecision:
        del sample_rate
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            return VADDecision(speech=False, probability=0.0, rms=0.0)

        rms = float(np.sqrt(np.mean(np.square(audio))))
        probability = min(1.0, rms / self.probability_rms_scale) if self.probability_rms_scale > 0 else 0.0
        return VADDecision(
            speech=rms >= self.speech_rms_threshold,
            probability=probability,
            rms=rms,
        )
