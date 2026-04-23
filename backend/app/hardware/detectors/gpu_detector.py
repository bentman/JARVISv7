from __future__ import annotations

import json
import platform
import subprocess


def _run_command(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return ""
    return (completed.stdout or completed.stderr or "").strip()


def _normalize_vendor(text: str) -> str | None:
    lower = text.lower()
    if "nvidia" in lower:
        return "nvidia"
    if "intel" in lower or "xpu" in lower:
        return "intel"
    if "amd" in lower or "radeon" in lower or "rocm" in lower:
        return "amd"
    if "qualcomm" in lower:
        return "qualcomm"
    return None


def _build_result(vendor: str, name: str | None, vram_gb: float | None, source: str) -> dict[str, object]:
    return {
        "gpu_available": True,
        "gpu_name": name,
        "gpu_vendor": vendor,
        "gpu_vram_gb": vram_gb,
        "gpu_vram_source": source,
    }


def _parse_mebibytes(value: str) -> float | None:
    try:
        return round(float(value.strip()) / 1024.0, 2)
    except Exception:
        return None


def _probe_cli(command: list[str], vendor_hint: str, source: str) -> dict[str, object] | None:
    try:
        output = _run_command(command)
    except (FileNotFoundError, OSError):
        return None

    if not output:
        return None

    vendor = _normalize_vendor(output) or vendor_hint
    first_line = output.splitlines()[0].strip()
    parts = [part.strip() for part in first_line.split(",") if part.strip()]
    name = parts[0] if parts else vendor.title()
    vram_gb = _parse_mebibytes(parts[1]) if len(parts) > 1 else None
    return _build_result(vendor, name, vram_gb, source)


def _probe_windows_wmi() -> dict[str, object] | None:
    if platform.system().lower() != "windows":
        return None

    try:
        output = _run_command(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | "
                "Select-Object Name,AdapterRAM | ConvertTo-Json -Compress",
            ]
        )
    except (FileNotFoundError, OSError):
        return None

    if not output:
        return None

    try:
        payload = json.loads(output)
    except Exception:
        return None

    if isinstance(payload, dict):
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        return None

    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "").strip() or None
        if not name:
            continue
        vendor = _normalize_vendor(name) or "unknown"
        adapter_ram = item.get("AdapterRAM")
        vram_gb = None
        if isinstance(adapter_ram, (int, float)):
            vram_gb = round(float(adapter_ram) / (1024**3), 2)
        return _build_result(vendor, name, vram_gb, "windows-wmi")

    return None


def detect_gpu_info() -> dict[str, object]:
    for command, vendor_hint, source in [
        (["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], "nvidia", "nvidia-smi"),
        (["xpu-smi", "-q"], "intel", "xpu-smi"),
        (["rocm-smi", "--showproductname"], "amd", "rocm-smi"),
    ]:
        probe = _probe_cli(command, vendor_hint, source)
        if probe is not None:
            return probe

    probe = _probe_windows_wmi()
    if probe is not None:
        return probe

    return {
        "gpu_available": False,
        "gpu_name": None,
        "gpu_vendor": None,
        "gpu_vram_gb": None,
        "gpu_vram_source": None,
    }
