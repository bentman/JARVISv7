from __future__ import annotations

from pathlib import Path


def write_trace(turn_id: str, content: str, trace_dir: Path) -> Path:
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / f"{turn_id}.txt"
    trace_path.write_text(content, encoding="utf-8")
    return trace_path