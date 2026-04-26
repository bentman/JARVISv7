from __future__ import annotations

import numpy as np


class BargeInDetector:
    def detect(self, audio_chunk: np.ndarray) -> bool:
        return False