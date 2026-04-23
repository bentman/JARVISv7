from __future__ import annotations

import platform

import psutil


def normalize_arch(machine: str | None) -> str:
    value = (machine or "").strip().lower()
    if value in {"amd64", "x86_64", "x64"}:
        return "amd64"
    if value in {"arm64", "aarch64"}:
        return "arm64"
    return "unknown"


def detect_cpu_info() -> dict[str, int | float | str | None]:
    cpu_freq = psutil.cpu_freq()
    return {
        "cpu_name": (platform.processor() or platform.machine() or "unknown").strip() or "unknown",
        "cpu_physical_cores": psutil.cpu_count(logical=False),
        "cpu_logical_cores": psutil.cpu_count(logical=True),
        "cpu_max_freq_mhz": round(cpu_freq.max, 2) if cpu_freq and cpu_freq.max else None,
        "arch": normalize_arch(platform.machine()),
    }
