from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any

SESSION_ARTIFACT_FIELDS: tuple[str, ...] = (
    "session_id",
    "started_at",
    "ended_at",
    "turn_ids",
    "final_state",
    "timeline_path",
    "continuity_summary",
    "memory_curation_candidate",
)


@dataclass(slots=True)
class SessionArtifact:
    session_id: str
    started_at: str
    ended_at: str | None = None
    turn_ids: list[str] = field(default_factory=list)
    final_state: str = "IDLE"
    timeline_path: str | None = None
    continuity_summary: dict[str, Any] = field(default_factory=dict)
    memory_curation_candidate: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {name: payload[name] for name in SESSION_ARTIFACT_FIELDS}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SessionArtifact:
        field_names = {field_def.name for field_def in fields(cls)}
        return cls(**{name: payload[name] for name in field_names if name in payload})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> SessionArtifact:
        return cls.from_dict(json.loads(payload))
