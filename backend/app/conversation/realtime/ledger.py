from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.conversation.states import ConversationState
from backend.app.conversation.realtime.events import RealtimeEvent, RealtimeEventType


@dataclass(slots=True)
class RealtimeEventLedger:
    session_id: str
    events: list[RealtimeEvent] = field(default_factory=list)
    _next_sequence: int = 1

    def append(
        self,
        event_type: RealtimeEventType,
        *,
        source: str | None = None,
        turn_id: str | None = None,
        state: ConversationState | str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RealtimeEvent:
        event = RealtimeEvent.create(
            session_id=self.session_id,
            event_type=event_type,
            sequence=self._next_sequence,
            source=source,
            turn_id=turn_id,
            state=state,
            metadata=metadata,
        )
        self.events.append(event)
        self._next_sequence += 1
        return event

    def event_types(self) -> list[RealtimeEventType]:
        return [event.event_type for event in self.events]

    def to_dicts(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.events]
