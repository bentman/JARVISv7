from __future__ import annotations

import json
from datetime import datetime

from backend.app.core.capabilities import HardwareProfile
from backend.app.tools.system.hardware_tool import HardwareTool
from backend.app.tools.system.time_tool import TimeTool


def test_time_tool_returns_iso8601_string() -> None:
    value = TimeTool().run({})
    assert isinstance(value, str)
    assert datetime.fromisoformat(value)


def test_hardware_tool_returns_json_with_arch() -> None:
    profile = HardwareProfile(arch="amd64", gpu_vendor="nvidia", npu_vendor="qualcomm")
    payload = json.loads(HardwareTool(profile).run({}))
    assert payload["arch"] == "amd64"
    assert "gpu_vendor" in payload
    assert "npu_vendor" in payload
