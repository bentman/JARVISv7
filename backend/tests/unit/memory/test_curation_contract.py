from __future__ import annotations

import json

import pytest
from backend.app.memory.curation_contract import (
    PROVISIONAL_MEMORY_KIND,
    ApplicationIdentityDecision,
    CandidateDisposition,
    EvidenceAuthority,
    EvidenceField,
    GovernedMemoryKind,
    PersistedTurnEvidence,
    ProposalContractError,
    apply_identity_decision,
    build_provisional_candidate,
    build_provisional_candidates,
    derive_provisional_claim_key,
    parse_model_proposals,
    verify_evidence_refs,
)


def _candidate(
    *,
    field: str = "transcript",
    excerpt: str = "I live in Chicago.",
) -> dict[str, object]:
    return {
        "text": "The user lives in Chicago.",
        "evidence_refs": [
            {
                "source_turn_id": "turn-1",
                "source_field": field,
                "excerpt": excerpt,
            }
        ],
        "confidence": 0.9,
        "importance": 0.7,
    }


def _raw(candidate: dict[str, object] | None = None) -> str:
    return json.dumps({"candidates": [candidate or _candidate()]})


def _turn(
    *,
    transcript: str | None = "I live in Chicago.",
    response_text: str | None = "You live in Chicago.",
    failure_reason: str | None = None,
) -> PersistedTurnEvidence:
    return PersistedTurnEvidence(
        session_id="session-1",
        turn_id="turn-1",
        transcript=transcript,
        response_text=response_text,
        failure_reason=failure_reason,
    )


def test_governed_kind_vocabulary_is_application_owned_and_exact() -> None:
    assert {kind.value for kind in GovernedMemoryKind} == {
        "unclassified",
        "user_preference",
        "personal_fact",
        "project_fact",
        "decision",
        "commitment",
        "relationship",
        "summary",
    }
    assert GovernedMemoryKind.UNCLASSIFIED.value == PROVISIONAL_MEMORY_KIND


def test_strict_parser_accepts_measured_shape_and_surrounding_whitespace() -> None:
    proposal = parse_model_proposals(f" \n{_raw()}\t ")[0]

    assert proposal.text == "The user lives in Chicago."
    assert proposal.evidence_refs[0].source_field is EvidenceField.TRANSCRIPT
    assert proposal.confidence == 0.9


@pytest.mark.parametrize(
    "raw_output",
    [
        '{"candidates":[],"candidates":[]}',
        '{"candidates":[{"text":"x","text":"y"}]}',
        '{"candidates":[],"unknown":true}',
        '{"candidates":[]} trailing',
        '```json\n{"candidates":[]}\n```',
        '{"candidates":[{"text":"x","evidence_refs":[],'
        '"confidence":NaN,"importance":0.5}]}',
        "[]",
    ],
)
def test_strict_parser_rejects_recovered_or_nonstandard_json(raw_output: str) -> None:
    with pytest.raises(ProposalContractError):
        parse_model_proposals(raw_output)


def test_strict_parser_rejects_unknown_nested_fields_and_invalid_numbers() -> None:
    candidate = _candidate()
    evidence = candidate["evidence_refs"][0]  # type: ignore[index]
    evidence["unknown"] = "value"  # type: ignore[index]
    with pytest.raises(ProposalContractError, match="evidence reference fields"):
        parse_model_proposals(_raw(candidate))

    candidate = _candidate()
    candidate["confidence"] = True
    with pytest.raises(ProposalContractError, match="JSON number"):
        parse_model_proposals(_raw(candidate))

    candidate = _candidate()
    candidate["kind"] = "personal_fact"
    with pytest.raises(ProposalContractError, match="candidate fields"):
        parse_model_proposals(_raw(candidate))


def test_evidence_verification_derives_authority_from_persisted_field() -> None:
    transcript_proposal = parse_model_proposals(_raw())[0]
    transcript_ref = verify_evidence_refs(transcript_proposal, [_turn()])[0]
    assert transcript_ref.authority is EvidenceAuthority.DIRECT_USER_STATEMENT

    response_proposal = parse_model_proposals(
        _raw(
            _candidate(
                field="response_text",
                excerpt="You live in Chicago.",
            )
        )
    )[0]
    response_ref = verify_evidence_refs(response_proposal, [_turn()])[0]
    assert response_ref.authority is EvidenceAuthority.ASSISTANT_INFERENCE


@pytest.mark.parametrize(
    ("turn", "error"),
    [
        (
            PersistedTurnEvidence(
                session_id="session-1",
                turn_id="different-turn",
                transcript="I live in Chicago.",
                response_text=None,
            ),
            "allowlist",
        ),
        (_turn(transcript="I live elsewhere."), "exact persisted-field substring"),
        (_turn(failure_reason="runtime_error"), "failed turns"),
    ],
)
def test_evidence_verification_rejects_untrusted_origins(
    turn: PersistedTurnEvidence,
    error: str,
) -> None:
    proposal = parse_model_proposals(_raw())[0]
    with pytest.raises(ProposalContractError, match=error):
        verify_evidence_refs(proposal, [turn])


def test_provisional_identity_is_derived_without_model_identity_fields() -> None:
    proposal = parse_model_proposals(_raw())[0]
    candidate = build_provisional_candidate(proposal, [_turn()])

    assert candidate.kind == PROVISIONAL_MEMORY_KIND
    assert candidate.disposition is CandidateDisposition.REVIEW_REQUIRED
    assert candidate.can_auto_activate is False
    assert candidate.can_auto_reinforce is False
    assert candidate.can_auto_supersede is False


def test_provisional_key_is_order_stable_and_changes_with_evidence_origin() -> None:
    first_proposal = parse_model_proposals(_raw())[0]
    first_ref = verify_evidence_refs(first_proposal, [_turn()])[0]
    second_turn = PersistedTurnEvidence(
        session_id="session-1",
        turn_id="turn-2",
        transcript="Chicago is my home.",
        response_text=None,
    )
    second_proposal_data = _candidate(excerpt="Chicago is my home.")
    second_proposal_data["evidence_refs"] = [
        {
            "source_turn_id": "turn-2",
            "source_field": "transcript",
            "excerpt": "Chicago is my home.",
        }
    ]
    second_ref = verify_evidence_refs(
        parse_model_proposals(_raw(second_proposal_data))[0],
        [second_turn],
    )[0]

    assert derive_provisional_claim_key([first_ref, second_ref]) == (
        derive_provisional_claim_key([second_ref, first_ref])
    )
    assert derive_provisional_claim_key([first_ref]) != derive_provisional_claim_key([second_ref])


def test_response_only_proposals_cannot_become_provisional_memory() -> None:
    proposal = parse_model_proposals(
        _raw(_candidate(field="response_text", excerpt="You live in Chicago."))
    )[0]
    with pytest.raises(ProposalContractError, match="direct transcript evidence"):
        build_provisional_candidate(proposal, [_turn()])


def test_duplicate_evidence_identity_requires_operator_disambiguation() -> None:
    proposals = parse_model_proposals(
        json.dumps({"candidates": [_candidate(), _candidate()]})
    )
    with pytest.raises(ProposalContractError, match="operator disambiguation"):
        build_provisional_candidates(proposals, [_turn()])


def test_only_explicit_application_decision_assigns_governed_identity() -> None:
    proposal = parse_model_proposals(_raw())[0]
    candidate = build_provisional_candidate(proposal, [_turn()])

    new_identity = apply_identity_decision(
        candidate,
        ApplicationIdentityDecision(kind=GovernedMemoryKind.PERSONAL_FACT),
    )
    related_identity = apply_identity_decision(
        candidate,
        ApplicationIdentityDecision(
            kind=GovernedMemoryKind.PERSONAL_FACT,
            related_claim_key="claim.existingapplicationidentity",
        ),
    )

    assert new_identity.claim_key == candidate.claim_key
    assert new_identity.kind is GovernedMemoryKind.PERSONAL_FACT
    assert related_identity.claim_key == "claim.existingapplicationidentity"
    assert related_identity.claim_key != candidate.claim_key


def test_invalid_application_related_key_fails_closed() -> None:
    with pytest.raises(ProposalContractError):
        ApplicationIdentityDecision(
            kind=GovernedMemoryKind.PERSONAL_FACT,
            related_claim_key="Model Chosen Key",
        )
