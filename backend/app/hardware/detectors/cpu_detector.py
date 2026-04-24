from __future__ import annotations

import importlib
import os
import platform


def _load_psutil():
    try:
        return importlib.import_module("psutil")
    except Exception:
        return None


def normalize_arch(machine: str | None) -> str:
    value = (machine or "").strip().lower()
    if value in {"amd64", "x86_64", "x64"}:
        return "amd64"
    if value in {"arm64", "aarch64"}:
        return "arm64"
    return "unknown"


def detect_cpu_info() -> dict[str, int | float | str | None]:
    psutil = _load_psutil()
    cpu_freq = psutil.cpu_freq() if psutil is not None else None
    return {
        "cpu_name": (platform.processor() or platform.machine() or "unknown").strip() or "unknown",
        "cpu_physical_cores": psutil.cpu_count(logical=False) if psutil is not None else os.cpu_count(),
        "cpu_logical_cores": psutil.cpu_count(logical=True) if psutil is not None else os.cpu_count(),
        "cpu_max_freq_mhz": round(cpu_freq.max, 2) if cpu_freq and cpu_freq.max else None,
        "arch": normalize_arch(platform.machine()),
    }
