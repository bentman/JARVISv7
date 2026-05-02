from __future__ import annotations

import json

from backend.app.core.capabilities import HardwareProfile
from backend.app.tools.registry import ToolBase


class HardwareTool(ToolBase):
    def __init__(self, profile: HardwareProfile) -> None:
        self._profile = profile

    def name(self) -> str:
        return "hardware.info"

    def description(self) -> str:
        return "Return selected host hardware facts from cached profile."

    def run(self, tool_input: dict[str, object]) -> str:
        payload = {
            "arch": self._profile.arch,
            "gpu_vendor": self._profile.gpu_vendor,
            "npu_vendor": self._profile.npu_vendor,
            "memory_total_gb": self._profile.memory_total_gb,
            "memory_available_gb": self._profile.memory_available_gb,
        }
        return json.dumps(payload, sort_keys=True)
