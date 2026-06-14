from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from backend.app.conversation.states import ConversationState

ContinuityDecision = Literal[
    "continue_current_session",
    "start_new_session",
    "recover_interrupted_response",
    "ignore_stale_context",
    "summarize_and_close",
]

RESET_PHRASES: tuple[str, ...] = (
    "start over",
    "new topic",
    "reset context",
    "forget that",
    "ignore previous",
)
STOP_PHRASES: tuple[str, ...] = ("stop", "cancel", "never mind", "nevermind")
DEFAULT_STALE_AFTER = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class ContinuityPolicyInput:
    active_session: bool
    same_session: bool
    latest_text: str | None = None
    last_turn_at: datetime | None = None
    now: datetime | None = None
    stale_after: timedelta = DEFAULT_STALE_AFTER
    last_final_state: ConversationState | str | None = None
    failure_reason: str | None = None
    prior_interrupted: bool = False
    invocation_source: str | None = None


@dataclass(frozen=True, slots=True)
class ContinuityPolicyResult:
    decision: ContinuityDecision
    include_continuity: bool
    reason: str


def decide_continuity(inputs: ContinuityPolicyInput) -> ContinuityPolicyResult:
    latest_text = (inputs.latest_text or "").strip().lower()
    if _contains_phrase(latest_text, RESET_PHRASES):
        return ContinuityPolicyResult("start_new_session", False, "explicit reset phrase")
    if _contains_phrase(latest_text, STOP_PHRASES):
        return ContinuityPolicyResult("summarize_and_close", False, "explicit stop phrase")
    if not inputs.active_session or not inputs.same_session:
        return ContinuityPolicyResult("start_new_session", False, "no matching active session")
    if _is_stale(inputs):
        return ContinuityPolicyResult("ignore_stale_context", False, "session context is stale")
    if inputs.failure_reason:
        return ContinuityPolicyResult("ignore_stale_context", False, "prior turn failed")
    if inputs.prior_interrupted:
        return ContinuityPolicyResult("recover_interrupted_response", True, "prior response was interrupted")
    if _state_value(inputs.last_final_state) == ConversationState.FAILED.value:
        return ContinuityPolicyResult("ignore_stale_context", False, "prior state failed")
    return ContinuityPolicyResult("continue_current_session", True, "same active session")


def _contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _is_stale(inputs: ContinuityPolicyInput) -> bool:
    if inputs.last_turn_at is None or inputs.now is None:
        return False
    return inputs.now - inputs.last_turn_at > inputs.stale_after


def _state_value(state: ConversationState | str | None) -> str | None:
    if isinstance(state, ConversationState):
        return state.value
    return state
