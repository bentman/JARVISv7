from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.artifacts import storage
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.core.paths import DATA_DIR
from backend.app.memory.write_policy import WritePolicy


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass(slots=True)
class EpisodicEntry:
    turn_id: str
    session_id: str
    session_started_at: str
    transcript: str | None
    response_text: str | None
    tools_invoked: list[str]
    written_at: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EpisodicEntry":
        return cls(
            turn_id=str(payload.get("turn_id", "")),
            session_id=str(payload.get("session_id", "")),
            session_started_at=str(payload.get("session_started_at", "")),
            transcript=payload.get("transcript"),
            response_text=payload.get("response_text"),
            tools_invoked=list(payload.get("tools_invoked", [])),
            written_at=str(payload.get("written_at", "")),
        )


class EpisodicMemory:
    def __init__(self, base_dir: Path = DATA_DIR / "memory" / "episodic", sessions_base_dir: Path = DATA_DIR / "sessions") -> None:
        self.base_dir = base_dir
        self.sessions_base_dir = sessions_base_dir

    def write_entry(self, artifact: TurnArtifact, policy: WritePolicy) -> EpisodicEntry | None:
        try:
            if not policy.write_to_episodic_memory:
                return None
            if policy.episodic_skip_failed_turns and artifact.failure_reason is not None:
                return None
            response_text = (artifact.response_text or "").strip()
            if len(response_text) < policy.episodic_min_response_length:
                return None

            session_started_at = _iso_now()
            session_artifact = storage.read_session_artifact(artifact.session_id, self.sessions_base_dir)
            if session_artifact is not None and session_artifact.started_at:
                session_started_at = session_artifact.started_at

            entry = EpisodicEntry(
                turn_id=artifact.turn_id,
                session_id=artifact.session_id,
                session_started_at=session_started_at,
                transcript=artifact.transcript,
                response_text=artifact.response_text,
                tools_invoked=list(artifact.tools_invoked),
                written_at=_iso_now(),
            )
            session_dir = self.base_dir / artifact.session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            entry_path = session_dir / f"{artifact.turn_id}.json"
            storage.write_text_atomic(entry_path, entry.to_json() + "\n")
            self._prune_sessions(policy)
            return entry
        except Exception:
            return None

    def retrieve_recent(self, n: int = 5, base_dir: Path | None = None) -> list[EpisodicEntry]:
        return self._retrieve(base_dir=base_dir, n=n)

    def retrieve_by_keyword(self, keyword: str, n: int = 5, base_dir: Path | None = None) -> list[EpisodicEntry]:
        needle = keyword.strip().lower()
        if not needle:
            return []
        try:
            entries = self._retrieve(base_dir=base_dir, n=10_000)
            matched: list[EpisodicEntry] = []
            for entry in entries:
                transcript = (entry.transcript or "").lower()
                response = (entry.response_text or "").lower()
                if needle in transcript or needle in response:
                    matched.append(entry)
                if len(matched) >= n:
                    break
            return matched
        except Exception:
            return []

    def _retrieve(self, *, base_dir: Path | None, n: int) -> list[EpisodicEntry]:
        try:
            root = base_dir or self.base_dir
            if not root.exists():
                return []
            entries: list[EpisodicEntry] = []
            for session_dir in root.iterdir():
                if not session_dir.is_dir():
                    continue
                for file_path in session_dir.glob("*.json"):
                    try:
                        payload = json.loads(file_path.read_text(encoding="utf-8"))
                        entry = EpisodicEntry.from_dict(payload)
                    except Exception:
                        continue
                    entries.append(entry)
            entries.sort(key=lambda item: _parse_iso(item.written_at) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            return entries[:n]
        except Exception:
            return []

    def _prune_sessions(self, policy: WritePolicy) -> None:
        retention = policy.episodic_retention_sessions
        if retention <= 0:
            return
        if not self.base_dir.exists():
            return
        session_dirs = [p for p in self.base_dir.iterdir() if p.is_dir()]
        if len(session_dirs) <= retention:
            return

        candidates: list[tuple[datetime, Path]] = []
        for session_dir in session_dirs:
            ts = self._session_timestamp(session_dir)
            if ts is None:
                continue
            candidates.append((ts, session_dir))

        candidates.sort(key=lambda item: item[0])
        prune_count = max(0, len(session_dirs) - retention)
        for _, session_dir in candidates[:prune_count]:
            for file_path in session_dir.glob("*"):
                if file_path.is_file():
                    file_path.unlink()
            session_dir.rmdir()

    def _session_timestamp(self, session_dir: Path) -> datetime | None:
        timestamps: list[datetime] = []
        for file_path in session_dir.glob("*.json"):
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
                dt = _parse_iso(str(payload.get("written_at", "")))
                if dt is not None:
                    timestamps.append(dt)
            except Exception:
                continue
        if timestamps:
            return min(timestamps)
        session_artifact = storage.read_session_artifact(session_dir.name, self.sessions_base_dir)
        if session_artifact is None:
            return None
        return _parse_iso(session_artifact.started_at)
