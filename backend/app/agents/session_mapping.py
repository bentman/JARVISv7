"""Map ACP session events into JARVIS-native turn structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.agents.schema import AgentProfile

_VALID_EVENT_TYPES = frozenset({
    "initialized",
    "session_created",
    "permission_request",
    "progress",
    "output",
    "error",
    "completed",
    "cancelled",
})

_VALID_STATUSES = frozenset({"running", "completed", "failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class AgentSessionEvent:
    event_type: str
    data: dict[str, Any]
    timestamp: str

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise ValueError("event_type must be a non-empty string")
        if self.event_type not in _VALID_EVENT_TYPES:
            raise ValueError(
                f"event_type must be one of {sorted(_VALID_EVENT_TYPES)}, got {self.event_type!r}"
            )
        if not isinstance(self.data, dict):
            raise ValueError("data must be a dict")
        if not isinstance(self.timestamp, str) or not self.timestamp.strip():
            raise ValueError("timestamp must be a non-empty string")


@dataclass(frozen=True, slots=True)
class AgentSessionRecord:
    agent_id: str
    profile_id: str
    run_id: str
    events: list[AgentSessionEvent] = field(default_factory=list)
    status: str = "running"
    output: dict[str, Any] = field(default_factory=dict)
    memory_scope: str = "none"
    capability_ids: tuple[str, ...] = ()
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, str) or not self.agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("profile_id must be a non-empty string")
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        if self.status not in _VALID_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(_VALID_STATUSES)}, got {self.status!r}"
            )

    def append_event(self, event: AgentSessionEvent) -> AgentSessionRecord:
        """Return a new record with the event appended (frozen dataclass)."""
        new_events = [*self.events, event]
        return AgentSessionRecord(
            agent_id=self.agent_id,
            profile_id=self.profile_id,
            run_id=self.run_id,
            events=new_events,
            status=self.status,
            output=self.output,
            memory_scope=self.memory_scope,
            capability_ids=self.capability_ids,
            error=self.error,
        )

    def to_delegated_run(self) -> dict[str, Any]:
        """Convert to the dict format used in TurnArtifact.delegated_runs."""
        return {
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "profile_id": self.profile_id,
            "status": self.status,
            "output": self.output,
            "event_count": len(self.events),
            "memory_scope": self.memory_scope,
            "capability_ids": list(self.capability_ids),
            "error": self.error,
        }


def build_session_record(
    agent_profile: AgentProfile,
    run_id: str,
    events: list[AgentSessionEvent] | None = None,
) -> AgentSessionRecord:
    """Build a record from an AgentProfile and collected events."""
    return AgentSessionRecord(
        agent_id=agent_profile.profile_id,
        profile_id=agent_profile.profile_id,
        run_id=run_id,
        events=list(events) if events else [],
        status="running",
        output={},
        memory_scope=agent_profile.memory_scope,
        capability_ids=agent_profile.capability_ids,
        error=None,
    )


__all__ = [
    "AgentSessionEvent",
    "AgentSessionRecord",
    "build_session_record",
]
