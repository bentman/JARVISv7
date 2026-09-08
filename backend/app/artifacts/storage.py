from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from backend.app.artifacts.session_artifact import SessionArtifact
from backend.app.artifacts.session_timeline import SessionTimeline
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.core.paths import DATA_DIR

ACTION_LOG_NAME = "action-log.jsonl"
ACTION_LOG_ARCHIVE_NAME = "action-log.1.jsonl"
ACTION_LOG_MAX_BYTES = 8 * 1024 * 1024
_action_log_lock = threading.Lock()


def write_text_atomic(path: Path, content: str) -> None:
    """Write content to path so readers never observe a partially written file."""
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def write_turn_artifact(artifact: TurnArtifact, base_dir: Path = DATA_DIR / "turns") -> Path:
    session_dir = base_dir / artifact.session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = session_dir / f"{artifact.turn_id}.json"
    write_text_atomic(artifact_path, artifact.to_json() + "\n")
    return artifact_path


def read_turn_artifact(session_id: str, turn_id: str, base_dir: Path = DATA_DIR / "turns") -> TurnArtifact | None:
    artifact_path = base_dir / session_id / f"{turn_id}.json"
    if not artifact_path.exists():
        return None
    return TurnArtifact.from_json(artifact_path.read_text(encoding="utf-8"))


def write_session_artifact(artifact: SessionArtifact, base_dir: Path = DATA_DIR / "sessions") -> Path:
    session_dir = base_dir / artifact.session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = session_dir / "session.json"
    write_text_atomic(artifact_path, artifact.to_json() + "\n")
    return artifact_path


def read_session_artifact(session_id: str, base_dir: Path = DATA_DIR / "sessions") -> SessionArtifact | None:
    artifact_path = base_dir / session_id / "session.json"
    if not artifact_path.exists():
        return None
    return SessionArtifact.from_json(artifact_path.read_text(encoding="utf-8"))


def write_session_timeline(timeline: SessionTimeline, base_dir: Path = DATA_DIR / "sessions") -> Path:
    session_dir = base_dir / timeline.session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = session_dir / "timeline.json"
    write_text_atomic(artifact_path, timeline.to_json() + "\n")
    return artifact_path


def read_session_timeline(session_id: str, base_dir: Path = DATA_DIR / "sessions") -> SessionTimeline | None:
    artifact_path = base_dir / session_id / "timeline.json"
    if not artifact_path.exists():
        return None
    return SessionTimeline.from_json(artifact_path.read_text(encoding="utf-8"))


def append_action_event(entry: dict[str, Any], base_dir: Path = DATA_DIR / "actions") -> Path:
    """Append one action-evidence record durably.

    Action evidence must survive a crash and must not depend on an active session, so
    this appends and fsyncs rather than rewriting a whole file like the artifact writers.
    """
    base_dir.mkdir(parents=True, exist_ok=True)
    log_path = base_dir / ACTION_LOG_NAME
    line = json.dumps(entry, default=str, sort_keys=True) + "\n"
    with _action_log_lock:
        # Every governed action appends several records, so the log is bounded by rotating
        # once. One archive is kept, so evidence survives the roll instead of being truncated.
        if log_path.is_file() and log_path.stat().st_size + len(line.encode("utf-8")) > ACTION_LOG_MAX_BYTES:
            os.replace(log_path, base_dir / ACTION_LOG_ARCHIVE_NAME)
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    return log_path


def read_action_events(base_dir: Path = DATA_DIR / "actions") -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in (base_dir / ACTION_LOG_ARCHIVE_NAME, base_dir / ACTION_LOG_NAME):
        events.extend(_read_action_log(path))
    return events


def _read_action_log(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events
