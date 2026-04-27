from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from backend.app.conversation.states import ConversationState, validate_transition


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class TurnContext:
    session_id: str
    modality: Literal["voice", "text"]
    turn_id: str = field(default_factory=lambda: uuid4().hex)
    state: ConversationState = ConversationState.IDLE
    started_at: datetime = field(default_factory=utc_now)
    phase_timestamps: dict[str, datetime] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.phase_timestamps.setdefault(self.state.value, self.started_at)

    def advance(self, new_state: ConversationState) -> None:
        validate_transition(self.state, new_state)
        self.state = new_state
        self.phase_timestamps[new_state.value] = utc_now()