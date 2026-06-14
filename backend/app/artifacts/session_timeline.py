from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any

SESSION_TIMELINE_EVENT_FIELDS: tuple[str, ...] = (
    "sequence",
    "event_type",
    "timestamp",
    "turn_id",
    "source",
    "state",
    "metadata",
)
SESSION_TIMELINE_FIELDS: tuple[str, ...] = ("session_id", "events")


@dataclass(slots=True)
class SessionTimelineEvent:
    sequence: int
    event_type: str
    timestamp: str
    turn_id: str | None = None
    source: str | None = None
    state: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {name: payload[name] for name in SESSION_TIMELINE_EVENT_FIELDS}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SessionTimelineEvent:
        field_names = {field_def.name for field_def in fields(cls)}
        return cls(**{name: payload[name] for name in field_names if name in payload})


@dataclass(slots=True)
class SessionTimeline:
    session_id: str
    events: list[SessionTimelineEvent] = field(default_factory=list)

    def append(
        self,
        event_type: str,
        *,
        timestamp: str,
        turn_id: str | None = None,
        source: str | None = None,
        state: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionTimelineEvent:
        event = SessionTimelineEvent(
            sequence=len(self.events) + 1,
            event_type=event_type,
            timestamp=timestamp,
            turn_id=turn_id,
            source=source,
            state=state,
            metadata=dict(metadata or {}),
        )
        self.events.append(event)
        return event

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "events": [event.to_dict() for event in self.events],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SessionTimeline:
        field_names = {field_def.name for field_def in fields(cls)}
        values = {name: payload[name] for name in field_names if name in payload}
        values["events"] = [SessionTimelineEvent.from_dict(event) for event in payload.get("events", [])]
        return cls(**values)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> SessionTimeline:
        return cls.from_dict(json.loads(payload))
