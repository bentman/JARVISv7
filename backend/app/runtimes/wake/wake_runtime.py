from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.hardware.readiness import derive_wake_device_readiness
from backend.app.runtimes.wake.base import WakeBase
from backend.app.runtimes.wake.openwakeword_runtime import OpenWakeWordRuntime


class NullWakeRuntime(WakeBase):
    def __init__(self, reason: str, device: str = "cpu", model_path: Path | None = None) -> None:
        super().__init__(device=device, model_path=model_path or Path("."))
        self.reason = reason

    def is_available(self) -> bool:
        return False

    def detect(self, audio_chunk: np.ndarray) -> bool:
        return False


def select_wake_runtime(preflight: PreflightResult, profile: HardwareProfile) -> WakeBase:
    device, ready, reason = derive_wake_device_readiness(preflight, profile)
    if not ready:
        return NullWakeRuntime(reason=reason, device=device)
    return OpenWakeWordRuntime(device=device)