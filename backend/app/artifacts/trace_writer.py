from __future__ import annotations

from pathlib import Path

from backend.app.artifacts.storage import _atomic_write_text


def write_trace(turn_id: str, content: str, trace_dir: Path) -> Path:
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / f"{turn_id}.txt"
    _atomic_write_text(trace_path, content)
    return trace_path
