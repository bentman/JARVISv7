from __future__ import annotations

from enum import Enum


class ConversationState(str, Enum):
    BOOTSTRAP = "BOOTSTRAP"
    PROFILING = "PROFILING"
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    REASONING = "REASONING"
    ACTING = "ACTING"
    RESPONDING = "RESPONDING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    RECOVERING = "RECOVERING"
    FAILED = "FAILED"


class InvalidStateTransitionError(RuntimeError):
    def __init__(self, from_state: ConversationState, to_state: ConversationState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"invalid conversation transition: {from_state.value} -> {to_state.value}")


VALID_TRANSITIONS: dict[ConversationState, set[ConversationState]] = {
    ConversationState.BOOTSTRAP: {ConversationState.PROFILING, ConversationState.FAILED},
    ConversationState.PROFILING: {ConversationState.IDLE, ConversationState.FAILED},
    ConversationState.IDLE: {
        ConversationState.LISTENING,
        ConversationState.REASONING,
        ConversationState.FAILED,
    },
    ConversationState.LISTENING: {ConversationState.TRANSCRIBING, ConversationState.FAILED},
    ConversationState.TRANSCRIBING: {ConversationState.REASONING, ConversationState.FAILED},
    ConversationState.REASONING: {
        ConversationState.ACTING,
        ConversationState.RESPONDING,
        ConversationState.FAILED,
    },
    ConversationState.ACTING: {ConversationState.RESPONDING, ConversationState.FAILED},
    ConversationState.RESPONDING: {ConversationState.SPEAKING, ConversationState.IDLE, ConversationState.FAILED},
    ConversationState.SPEAKING: {
        ConversationState.INTERRUPTED,
        ConversationState.IDLE,
        ConversationState.FAILED,
    },
    ConversationState.INTERRUPTED: {ConversationState.RECOVERING, ConversationState.FAILED},
    ConversationState.RECOVERING: {ConversationState.IDLE, ConversationState.FAILED},
    ConversationState.FAILED: {ConversationState.IDLE},
}


def validate_transition(from_state: ConversationState, to_state: ConversationState) -> None:
    if to_state not in VALID_TRANSITIONS[from_state]:
        raise InvalidStateTransitionError(from_state, to_state)