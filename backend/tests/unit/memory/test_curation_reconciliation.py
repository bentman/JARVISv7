from __future__ import annotations

import json
from pathlib import Path

from backend.app.memory.curation import LifecycleState
from backend.app.memory.curation_contract import (
    GovernedMemoryKind,
    PersistedTurnEvidence,
    build_provisional_candidate,
    parse_model_proposals,
)
from backend.app.memory.curation_reconciliation import ReviewOnlyCurationPolicy
from backend.app.memory.semantic import SemanticMemory

NOW = "2026-07-24T12:00:00+00:00"


def _proposal(*, text: str, excerpt: str, value: str | None = None):
    raw = json.dumps(
        {
            "candidates": [
                {
                    "text": text,
                    "kind": "personal_fact",
                    "claim_key": "model.untrusted",
                    "value": value,
                    "relation": "assertion",
                    "evidence_refs": [
                        {
                            "source_turn_id": "turn-1",
                            "source_field": "transcript",
                            "excerpt": excerpt,
                        }
                    ],
                    "confidence": 0.9,
                    "importance": 0.7,
                }
            ]
        }
    )
    proposal = parse_model_proposals(raw)[0]
    turn = PersistedTurnEvidence(
        session_id="session-1",
        turn_id="turn-1",
        transcript=excerpt,
        response_text=None,
    )
    return proposal, build_provisional_candidate(proposal, (turn,))


def test_review_candidate_is_unclassified_pending_and_idempotent(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    policy = ReviewOnlyCurationPolicy(memory)
    proposal, candidate = _proposal(
        text="The user lives in Chicago.",
        excerpt="I live in Chicago.",
        value="Chicago",
    )

    first = policy.reconcile(
        proposal=proposal,
        candidate=candidate,
        observed_at=NOW,
    )
    detail_before = memory.list_facts().value
    second = policy.reconcile(
        proposal=proposal,
        candidate=candidate,
        observed_at=NOW,
    )
    detail_after = memory.list_facts().value

    assert first.pending_review_created == 1
    assert second.duplicate_noops == 1
    assert detail_before is not None and len(detail_before) == 1
    assert detail_after is not None and detail_after == detail_before
    fact = detail_after[0]
    assert fact.kind == GovernedMemoryKind.UNCLASSIFIED.value
    assert fact.state == LifecycleState.PENDING_REVIEW.value
    assert fact.claim_key == candidate.claim_key
    assert fact.value_text is None
    assert fact.reinforcement_count == 1
    detail = memory.read_fact(fact.fact_id).value
    assert detail is not None
    assert len(detail.evidence) == 1
    assert len(detail.events) == 1


def test_secret_and_application_owned_values_are_rejected_without_persistence(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    policy = ReviewOnlyCurationPolicy(
        memory,
        application_owned_values=("default-profile",),
    )
    secret_proposal, secret_candidate = _proposal(
        text="The API key is sk-abcdefghijklmnop1234.",
        excerpt="My API key is sk-abcdefghijklmnop1234.",
    )
    owned_proposal, owned_candidate = _proposal(
        text="The profile is default-profile.",
        excerpt="The profile is default-profile.",
    )

    secret = policy.reconcile(
        proposal=secret_proposal,
        candidate=secret_candidate,
        observed_at=NOW,
    )
    owned = policy.reconcile(
        proposal=owned_proposal,
        candidate=owned_candidate,
        observed_at=NOW,
    )

    assert secret.rejected == 1
    assert owned.rejected == 1
    assert memory.list_facts().value == ()
