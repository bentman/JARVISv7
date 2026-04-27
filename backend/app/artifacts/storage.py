from __future__ import annotations

from pathlib import Path

from backend.app.artifacts.session_artifact import SessionArtifact
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.core.paths import DATA_DIR


def write_turn_artifact(artifact: TurnArtifact, base_dir: Path = DATA_DIR / "turns") -> Path:
    session_dir = base_dir / artifact.session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = session_dir / f"{artifact.turn_id}.json"
    artifact_path.write_text(artifact.to_json() + "\n", encoding="utf-8")
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
    artifact_path.write_text(artifact.to_json() + "\n", encoding="utf-8")
    return artifact_path


def read_session_artifact(session_id: str, base_dir: Path = DATA_DIR / "sessions") -> SessionArtifact | None:
    artifact_path = base_dir / session_id / "session.json"
    if not artifact_path.exists():
        return None
    return SessionArtifact.from_json(artifact_path.read_text(encoding="utf-8"))