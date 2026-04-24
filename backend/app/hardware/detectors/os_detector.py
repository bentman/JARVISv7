from __future__ import annotations

import importlib
import platform
import subprocess
from pathlib import Path


_LAPTOP_CHASSIS_TYPES = {8, 9, 10, 11, 12, 14, 18, 21, 30, 31, 32}


def _load_psutil():
    try:
        return importlib.import_module("psutil")
    except Exception:
        return None


def _run_command(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return ""
    return (completed.stdout or completed.stderr or "").strip()


def _detect_device_class(os_name: str) -> str:
    battery = None
    psutil = _load_psutil()
    try:
        if psutil is not None:
            battery = psutil.sensors_battery()
    except Exception:
        battery = None

    if battery is not None:
        return "laptop"

    if os_name == "windows":
        output = _run_command(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_SystemEnclosure | Select-Object -ExpandProperty ChassisTypes) -join ','",
            ]
        )
        if output:
            try:
                chassis_types = {
                    int(part.strip())
                    for part in output.replace("[", "").replace("]", "").split(",")
                    if part.strip().isdigit()
                }
            except Exception:
                chassis_types = set()
            if chassis_types & _LAPTOP_CHASSIS_TYPES:
                return "laptop"
            if chassis_types:
                return "desktop"

    if os_name in {"linux", "darwin"}:
        dmi_path = Path("/sys/class/dmi/id/chassis_type")
        try:
            chassis_text = dmi_path.read_text(encoding="utf-8").strip()
        except Exception:
            chassis_text = ""
        if chassis_text.isdigit() and int(chassis_text) in _LAPTOP_CHASSIS_TYPES:
            return "laptop"

    return "unknown"


def detect_os_info() -> dict[str, str]:
    os_name = (platform.system() or "unknown").strip().lower()
    if os_name not in {"windows", "linux", "darwin"}:
        os_name = "unknown"

    return {
        "os_name": os_name,
        "os_version": (platform.version() or platform.release() or "unknown").strip() or "unknown",
        "device_class": _detect_device_class(os_name),
    }
