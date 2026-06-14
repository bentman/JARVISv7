from __future__ import annotations

import numpy as np


def has_committable_audio(audio: np.ndarray | None, sample_rate: int | None) -> bool:
    if audio is None or sample_rate is None:
        return False
    return sample_rate > 0 and np.asarray(audio).size > 0
