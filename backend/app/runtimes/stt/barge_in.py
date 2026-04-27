from __future__ import annotations

from collections.abc import Callable

import numpy as np


class BargeInDetector:
    def __init__(
        self,
        *,
        energy_threshold: float = 0.02,
        guard_time_s: float = 0.5,
        time_source: Callable[[], float] | None = None,
    ) -> None:
        self.energy_threshold = energy_threshold
        self.guard_time_s = guard_time_s
        self._time_source = time_source
        self._started_at: float | None = None

    def reset(self) -> None:
        self._started_at = self._now()

    def detect(self, audio_chunk: np.ndarray) -> bool:
        samples = np.asarray(audio_chunk, dtype=np.float32)
        if samples.size == 0:
            return False
        if self._started_at is not None and self._now() - self._started_at < self.guard_time_s:
            return False
        rms = float(np.sqrt(np.mean(np.square(samples))))
        return rms >= self.energy_threshold

    def _now(self) -> float:
        if self._time_source is not None:
            return self._time_source()
        import time

        return time.monotonic()