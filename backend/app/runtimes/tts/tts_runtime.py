from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.hardware.readiness import derive_tts_device_readiness
from backend.app.runtimes.tts.base import TTSBase
from backend.app.runtimes.tts.kokoro_onnx_runtime import KOKORO_SAMPLE_RATE, KokoroOnnxRuntime


class NullTTSRuntime(TTSBase):
    def __init__(
        self,
        reason: str,
        device: str = "cpu",
        model_path: Path | None = None,
        sample_rate: int = KOKORO_SAMPLE_RATE,
    ) -> None:
        super().__init__(device=device, model_path=model_path or Path("."))
        self.reason = reason
        self._sample_rate = sample_rate

    def is_available(self) -> bool:
        return False

    def synthesize(self, text: str) -> np.ndarray:
        return np.array([], dtype=np.float32)

    def sample_rate(self) -> int:
        return self._sample_rate


def select_tts_runtime(preflight: PreflightResult, profile: HardwareProfile) -> TTSBase:
    device, ready, reason = derive_tts_device_readiness(preflight, profile)
    if not ready:
        return NullTTSRuntime(reason=reason, device=device)
    return KokoroOnnxRuntime(device=device)