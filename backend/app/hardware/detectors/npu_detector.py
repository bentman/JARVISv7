from __future__ import annotations

import platform
import subprocess

_NPU_EVIDENCE_TOKENS = ("npu", "neural", "hexagon", "ai boost")

_VENDOR_TOKENS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("qualcomm", ("qualcomm", "hexagon", "snapdragon", "qcom")),
    ("intel", ("intel",)),
    ("amd", ("amd ", " amd", "xdna", "ryzen ai", "advanced micro devices")),
    ("apple", ("apple",)),
)


def _run_command(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=10)
    except subprocess.TimeoutExpired:
        return ""
    if completed.returncode != 0:
        return ""
    return (completed.stdout or completed.stderr or "").strip()


def _match_vendor(pnp_output: str) -> str | None:
    for line in pnp_output.splitlines():
        lowered = line.lower()
        if not any(token in lowered for token in _NPU_EVIDENCE_TOKENS):
            continue
        for vendor, tokens in _VENDOR_TOKENS:
            if any(token in lowered for token in tokens):
                return vendor
    return None


def detect_npu_info() -> dict[str, object]:
    machine = (platform.machine() or "").strip().lower()
    system = (platform.system() or "").strip().lower()

    if system == "darwin" and machine == "arm64":
        return {
            "npu_available": True,
            "npu_vendor": "apple",
            "npu_tops": None,
        }

    windows_pnp_output = ""
    if system == "windows":
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

    vendor = _match_vendor(windows_pnp_output)
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
