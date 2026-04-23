from __future__ import annotations

import psutil


def _bytes_to_gb(value: int | float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / (1024**3), 2)


def detect_memory_info() -> dict[str, float | None]:
    memory = psutil.virtual_memory()
    return {
        "memory_total_gb": _bytes_to_gb(getattr(memory, "total", None)),
        "memory_available_gb": _bytes_to_gb(getattr(memory, "available", None)),
    }
