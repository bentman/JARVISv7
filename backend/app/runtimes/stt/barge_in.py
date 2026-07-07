from __future__ import annotations

from collections.abc import Callable

import numpy as np

from backend.app.runtimes.vad import VADRuntime


class BargeInDetector:
    def __init__(
        self,
        *,
        energy_threshold: float = 0.02,
        guard_time_s: float = 0.5,
        min_speech_s: float = 0.2,
        min_speech_chunks: int = 1,
        sample_rate: int = 16000,
        vad: VADRuntime | None = None,
        time_source: Callable[[], float] | None = None,
    ) -> None:
        self.energy_threshold = energy_threshold
        self.guard_time_s = guard_time_s
        self.min_speech_s = min_speech_s
        self.min_speech_chunks = max(1, min_speech_chunks)
        self.sample_rate = sample_rate
        self.vad = vad
        self._time_source = time_source
        self._started_at: float | None = None
        self._speech_samples = 0
        self._speech_chunks = 0

    def reset(self) -> None:
        self._started_at = self._now()
        self._speech_samples = 0
        self._speech_chunks = 0

    def detect(self, audio_chunk: np.ndarray) -> bool:
        samples = np.asarray(audio_chunk, dtype=np.float32)
        if samples.size == 0:
            return False
        if self._started_at is not None and self._now() - self._started_at < self.guard_time_s:
            return False
        if self.vad is not None:
            speech = self.vad.detect(samples, self.sample_rate).speech
        else:
            rms = float(np.sqrt(np.mean(np.square(samples))))
            speech = rms >= self.energy_threshold
        if not speech:
            self._speech_samples = 0
            self._speech_chunks = 0
            return False
        self._speech_samples += int(samples.size)
        self._speech_chunks += 1
        return self._speech_samples >= int(self.min_speech_s * self.sample_rate) and self._speech_chunks >= self.min_speech_chunks

    def _now(self) -> float:
        if self._time_source is not None:
            return self._time_source()
        import time

        return time.monotonic()
