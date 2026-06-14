from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from backend.app.conversation.states import ConversationState


class RealtimeEventType(str, Enum):
    SESSION_ACTIVE = "SESSION_ACTIVE"
    INVOCATION_RECEIVED = "INVOCATION_RECEIVED"
    AUDIO_CAPTURE_STARTED = "AUDIO_CAPTURE_STARTED"
    AUDIO_CAPTURE_COMPLETED = "AUDIO_CAPTURE_COMPLETED"
    USER_TURN_COMMITTED = "USER_TURN_COMMITTED"
    TRANSCRIBING = "TRANSCRIBING"
    REASONING = "REASONING"
    RESPONDING = "RESPONDING"
    SPEAKING = "SPEAKING"
    TURN_COMPLETED = "TURN_COMPLETED"
    ASSISTANT_SPEECH_STARTED = "ASSISTANT_SPEECH_STARTED"
    USER_INTERRUPTION_DETECTED = "USER_INTERRUPTION_DETECTED"
    ASSISTANT_SPEECH_STOP_REQUESTED = "ASSISTANT_SPEECH_STOP_REQUESTED"
    TURN_RECOVERING = "TURN_RECOVERING"
    SESSION_IDLE = "SESSION_IDLE"
    SESSION_FAILED = "SESSION_FAILED"


@dataclass(frozen=True, slots=True)
class RealtimeEvent:
    session_id: str
    event_type: RealtimeEventType
    sequence: int
    timestamp: str
    source: str | None = None
    turn_id: str | None = None
    state: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        event_type: RealtimeEventType,
        sequence: int,
        source: str | None = None,
        turn_id: str | None = None,
        state: ConversationState | str | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> RealtimeEvent:
        state_value = state.value if isinstance(state, ConversationState) else state
        return cls(
            session_id=session_id,
            event_type=event_type,
            sequence=sequence,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            source=source,
            turn_id=turn_id,
            state=state_value,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "event_type": self.event_type.value,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "source": self.source,
            "turn_id": self.turn_id,
            "state": self.state,
            "metadata": dict(self.metadata),
        }
