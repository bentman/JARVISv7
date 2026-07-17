from __future__ import annotations

import os
from pathlib import Path

from backend.app.artifacts.session_artifact import SessionArtifact
from backend.app.artifacts.session_timeline import SessionTimeline
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.core.paths import DATA_DIR


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
