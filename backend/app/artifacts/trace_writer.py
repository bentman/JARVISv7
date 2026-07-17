from __future__ import annotations

from pathlib import Path

from backend.app.artifacts.storage import write_text_atomic


def write_trace(turn_id: str, content: str, trace_dir: Path) -> Path:
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / f"{turn_id}.txt"
    write_text_atomic(trace_path, content)
    return trace_path