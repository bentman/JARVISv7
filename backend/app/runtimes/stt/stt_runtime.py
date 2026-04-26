from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.hardware.readiness import derive_stt_device_readiness
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.stt.onnx_whisper_runtime import OnnxWhisperRuntime


class DegradedSTTRuntime(STTBase):
    def __init__(self, reason: str, device: str = "cpu", model_path: Path | None = None) -> None:
        super().__init__(device=device, model_path=model_path or Path("."))
        self.reason = reason

    def is_available(self) -> bool:
        return False

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        raise RuntimeError(self.reason)


def select_stt_runtime(preflight: PreflightResult, profile: HardwareProfile) -> STTBase:
    device, ready, reason = derive_stt_device_readiness(preflight, profile)
    if not ready:
        return DegradedSTTRuntime(reason=reason, device=device)
    return OnnxWhisperRuntime(device=device)