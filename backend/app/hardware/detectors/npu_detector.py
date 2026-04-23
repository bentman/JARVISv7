from __future__ import annotations

import platform
import subprocess


def _run_command(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return ""
    return (completed.stdout or completed.stderr or "").strip()


def _match_vendor(*texts: str) -> str | None:
    joined = " ".join(texts).lower()
    if any(token in joined for token in ("qualcomm", "hexagon", "snapdragon", "qcom")):
        return "qualcomm"
    if any(token in joined for token in ("intel", "neural processing unit", "npu")):
        return "intel"
    if any(token in joined for token in ("amd ", " amd", "xdna", "ryzen ai", "advanced micro devices")):
        return "amd"
    if "apple" in joined:
        return "apple"
    return None


def detect_npu_info() -> dict[str, object]:
    machine = (platform.machine() or "").strip().lower()
    processor = (platform.processor() or "").strip().lower()
    system = (platform.system() or "").strip().lower()

    if system == "darwin" and machine == "arm64":
        return {
            "npu_available": True,
            "npu_vendor": "apple",
            "npu_tops": None,
        }

    try:
        windows_pnp_output = _run_command(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_PnPEntity | Select-Object Name | Format-Table -HideTableHeaders",
            ]
        )
    except (FileNotFoundError, OSError):
        windows_pnp_output = ""

    vendor = _match_vendor(processor, windows_pnp_output)
    if vendor is not None:
        return {
            "npu_available": True,
            "npu_vendor": vendor,
            "npu_tops": None,
        }

    if system == "windows" and machine == "arm64" and "qualcomm" in windows_pnp_output.lower():
        return {
            "npu_available": True,
            "npu_vendor": "qualcomm",
            "npu_tops": None,
        }

    return {
        "npu_available": False,
        "npu_vendor": None,
        "npu_tops": None,
    }
