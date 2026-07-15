from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.app.conversation.continuity_policy import ContinuityPolicyInput, decide_continuity
from backend.app.conversation.states import ConversationState


def test_continuity_policy_continues_same_active_session():
    result = decide_continuity(ContinuityPolicyInput(active_session=True, same_session=True, latest_text="continue"))

    assert result.decision == "continue_current_session"
    assert result.include_continuity is True


def test_continuity_policy_excludes_stale_context():
    now = datetime(2026, 6, 14, tzinfo=UTC)
    result = decide_continuity(
        ContinuityPolicyInput(
            active_session=True,
            same_session=True,
            last_turn_at=now - timedelta(hours=1),
            now=now,
            stale_after=timedelta(minutes=30),
        )
    )

    assert result.decision == "ignore_stale_context"
    assert result.include_continuity is False


def test_continuity_policy_recovers_interrupted_response():
    result = decide_continuity(
        ContinuityPolicyInput(active_session=True, same_session=True, prior_interrupted=True)
    )

    assert result.decision == "recover_interrupted_response"
    assert result.include_continuity is True


def test_continuity_policy_fails_closed_after_failed_turn():
    result = decide_continuity(
        ContinuityPolicyInput(active_session=True, same_session=True, last_final_state=ConversationState.FAILED)
    )

    assert result.decision == "ignore_stale_context"
    assert result.include_continuity is False


def test_continuity_policy_respects_explicit_reset_phrase():
    result = decide_continuity(
        ContinuityPolicyInput(active_session=True, same_session=True, latest_text="reset context please")
    )

    assert result.decision == "start_new_session"
    assert result.include_continuity is False
