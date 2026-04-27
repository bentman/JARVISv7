from __future__ import annotations

import pytest

from backend.app.conversation.states import (
    VALID_TRANSITIONS,
    ConversationState,
    InvalidStateTransitionError,
    validate_transition,
)
from backend.app.conversation.turn_manager import TurnContext


def test_valid_transitions_defined_for_all_states():
    assert set(VALID_TRANSITIONS) == set(ConversationState)


def test_invalid_transition_raises_error():
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        validate_transition(ConversationState.IDLE, ConversationState.SPEAKING)

    assert exc_info.value.from_state == ConversationState.IDLE
    assert exc_info.value.to_state == ConversationState.SPEAKING


def test_turn_context_advance_records_timestamp():
    context = TurnContext(session_id="session", modality="text")

    context.advance(ConversationState.REASONING)


    assert context.state == ConversationState.REASONING
    assert ConversationState.REASONING.value in context.phase_timestamps


def test_turn_context_advance_rejects_invalid_transition():
    context = TurnContext(session_id="session", modality="text")

    with pytest.raises(InvalidStateTransitionError):
        context.advance(ConversationState.SPEAKING)