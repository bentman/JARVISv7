from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from backend.app.memory.curation import (
    TRANSITION_MATRIX,
    CurationJobStatus,
    CurationValidationError,
    EvidenceInput,
    GovernedEvidenceAuthority,
    GovernedFactInput,
    LifecycleState,
    OperationStatus,
)
from backend.app.memory.curation_contract import (
    GovernedClaimIdentity,
    GovernedMemoryKind,
)
from backend.app.memory.semantic import SemanticMemory

NOW = "2026-07-24T12:00:00+00:00"


def _turn_evidence(index: int = 1) -> EvidenceInput:
    return EvidenceInput(
        authority=GovernedEvidenceAuthority.DIRECT_USER_STATEMENT,
        observed_at=NOW,
        source_session_id="session-1",
        source_turn_id=f"turn-{index}",
        source_field="transcript",
        metadata={"excerpt": f"evidence-{index}"},
    )


def _action_evidence(index: int = 1, reason: str = "confirm") -> EvidenceInput:
    return EvidenceInput(
        authority=GovernedEvidenceAuthority.DIRECT_USER_ACTION,
        observed_at=NOW,
        action_id=f"action-{index}",
        action_surface="api",
        action_reason=reason,
    )


def _fact(
    *,
    text: str = "The user lives in Chicago.",
    key: str = "claim.home_city",
    value: str | None = "Chicago",
    state: LifecycleState = LifecycleState.ACTIVE,
    evidence: tuple[EvidenceInput, ...] | None = None,
    authority: GovernedEvidenceAuthority = (GovernedEvidenceAuthority.DIRECT_USER_STATEMENT),
    kind: GovernedMemoryKind = GovernedMemoryKind.PERSONAL_FACT,
) -> GovernedFactInput:
    return GovernedFactInput(
        text=text,
        identity=GovernedClaimIdentity(kind=kind, claim_key=key),
        value_text=value,
        evidence_authority=authority,
        state=state,
        confidence=0.7,
        importance=0.6,
        evidence=evidence or (_turn_evidence(),),
    )


def _created(memory: SemanticMemory, fact: GovernedFactInput) -> str:
    result = memory.create_governed_fact(fact)
    assert result.status is OperationStatus.SUCCESS
    assert result.value is not None
    return result.value.fact_id


def _revision(memory: SemanticMemory) -> int:
    result = memory.read_content_revision()
    assert result.status is OperationStatus.SUCCESS
    assert result.value is not None
    return result.value


def _counts(memory: SemanticMemory) -> tuple[int, int, int, int]:
    with memory._get_conn() as conn:
        return (
            int(conn.execute("SELECT COUNT(*) FROM semantic_fact").fetchone()[0]),
            int(conn.execute("SELECT COUNT(*) FROM semantic_evidence").fetchone()[0]),
            int(conn.execute("SELECT COUNT(*) FROM semantic_event").fetchone()[0]),
            int(
                conn.execute(
                    "SELECT content_revision FROM semantic_meta WHERE singleton_id = 1"
                ).fetchone()[0]
            ),
        )


def test_transition_matrix_is_explicit_and_terminal_states_have_no_exits() -> None:
    assert {
        LifecycleState.PENDING_REVIEW: frozenset(
            {
                LifecycleState.ACTIVE,
                LifecycleState.DISPUTED,
                LifecycleState.FORGOTTEN,
            }
        ),
        LifecycleState.ACTIVE: frozenset(
            {
                LifecycleState.DISPUTED,
                LifecycleState.SUPERSEDED,
                LifecycleState.EXPIRED,
                LifecycleState.FORGOTTEN,
            }
        ),
        LifecycleState.DISPUTED: frozenset(
            {
                LifecycleState.ACTIVE,
                LifecycleState.SUPERSEDED,
                LifecycleState.FORGOTTEN,
            }
        ),
        LifecycleState.SUPERSEDED: frozenset(),
        LifecycleState.EXPIRED: frozenset(),
        LifecycleState.FORGOTTEN: frozenset(),
    } == TRANSITION_MATRIX


def test_create_read_and_list_are_bounded_stable_and_side_effect_free(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    fact_id = _created(memory, _fact(state=LifecycleState.PENDING_REVIEW))
    before = _counts(memory)

    detail = memory.read_fact(fact_id)
    listed = memory.list_facts(
        state=LifecycleState.PENDING_REVIEW,
        kind=GovernedMemoryKind.PERSONAL_FACT,
        query="Chicago",
        limit=10,
    )
    after = _counts(memory)

    assert detail.status is OperationStatus.SUCCESS
    assert detail.value is not None
    assert detail.value.fact.vector_dim == 128
    assert len(detail.value.evidence) == 1
    assert [event.event_type for event in detail.value.events] == ["created"]
    assert listed.status is OperationStatus.SUCCESS
    assert listed.value is not None
    assert [record.fact_id for record in listed.value] == [fact_id]
    assert before == after == (1, 1, 1, 1)
    assert memory.list_facts(limit=101).status is OperationStatus.INVALID
    assert (
        memory.list_facts(state="unknown").status  # type: ignore[arg-type]
        is OperationStatus.INVALID
    )
    assert (
        memory.list_facts(kind="personal_fact").status  # type: ignore[arg-type]
        is OperationStatus.INVALID
    )


def test_text_hash_collision_matrix_is_deterministic(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    original = _fact()
    fact_id = _created(memory, original)

    duplicate = memory.create_governed_fact(original)
    reinforced = memory.create_governed_fact(_fact(evidence=(_turn_evidence(2),)))
    before_conflict = _counts(memory)
    conflict = memory.create_governed_fact(
        _fact(
            key="claim.birth_city",
            value="Chicago",
            kind=GovernedMemoryKind.PERSONAL_FACT,
            evidence=(_turn_evidence(3),),
        )
    )

    assert duplicate.status is OperationStatus.NO_CHANGE
    assert duplicate.value is not None and duplicate.value.fact_id == fact_id
    assert reinforced.status is OperationStatus.SUCCESS
    assert reinforced.value is not None
    assert reinforced.value.reinforcement_count == 2
    assert conflict.status is OperationStatus.CONFLICT
    assert _counts(memory) == before_conflict


def test_same_claim_compatible_concurrent_creation_has_one_occupant(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")

    def create(index: int) -> OperationStatus:
        result = memory.create_governed_fact(
            _fact(
                text=f"The user's home city is Chicago ({index}).",
                evidence=(_turn_evidence(index),),
            )
        )
        return result.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(create, (1, 2)))

    listed = memory.list_facts(
        state=LifecycleState.ACTIVE,
        kind=GovernedMemoryKind.PERSONAL_FACT,
    )
    assert statuses.count(OperationStatus.SUCCESS) == 2
    assert listed.value is not None and len(listed.value) == 1
    assert listed.value[0].reinforcement_count == 2
    assert _counts(memory) == (1, 2, 2, 2)


def test_different_value_without_correction_creates_review_record(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    original_id = _created(memory, _fact())

    result = memory.create_governed_fact(
        _fact(
            text="The user now lives in Milwaukee.",
            value="Milwaukee",
            evidence=(_turn_evidence(2),),
        )
    )

    assert result.status is OperationStatus.REVIEW_REQUIRED
    assert result.value is not None
    assert result.value.state == LifecycleState.PENDING_REVIEW.value
    assert result.value.superseded_by_fact_id is None
    original = memory.read_fact(original_id)
    assert original.value is not None
    assert original.value.fact.state == LifecycleState.ACTIVE.value
    assert _revision(memory) == 2


def test_operator_transitions_require_exact_revision_and_action_evidence(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    fact_id = _created(memory, _fact(state=LifecycleState.PENDING_REVIEW))
    before_stale = _counts(memory)

    stale = memory.confirm_fact(
        fact_id,
        expected_revision=2,
        evidence=_action_evidence(),
    )
    wrong_evidence = memory.confirm_fact(
        fact_id,
        expected_revision=1,
        evidence=_turn_evidence(2),
    )
    confirmed = memory.confirm_fact(
        fact_id,
        expected_revision=1,
        evidence=_action_evidence(),
    )
    repeated_stale = memory.confirm_fact(
        fact_id,
        expected_revision=1,
        evidence=_action_evidence(),
    )

    assert stale.status is OperationStatus.CONFLICT
    assert wrong_evidence.status is OperationStatus.INVALID
    assert _counts(memory) != before_stale
    assert confirmed.status is OperationStatus.SUCCESS
    assert confirmed.value is not None
    assert confirmed.value.state == LifecycleState.ACTIVE.value
    assert confirmed.value.revision == 2
    assert repeated_stale.status is OperationStatus.CONFLICT
    assert _counts(memory) == (1, 2, 2, 2)


def test_allowed_dispute_confirm_expire_and_forget_transitions(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    fact_id = _created(memory, _fact())

    disputed = memory.dispute_fact(
        fact_id,
        expected_revision=1,
        evidence=_action_evidence(1, "dispute"),
    )
    confirmed = memory.confirm_fact(
        fact_id,
        expected_revision=2,
        evidence=_action_evidence(2, "confirm"),
    )
    expired = memory.expire_fact(
        fact_id,
        expected_revision=3,
        evidence=_action_evidence(3, "expire"),
    )
    terminal = memory.confirm_fact(
        fact_id,
        expected_revision=4,
        evidence=_action_evidence(4, "confirm"),
    )

    assert disputed.value is not None
    assert disputed.value.state == LifecycleState.DISPUTED.value
    assert confirmed.value is not None
    assert confirmed.value.state == LifecycleState.ACTIVE.value
    assert expired.value is not None
    assert expired.value.state == LifecycleState.EXPIRED.value
    assert terminal.status is OperationStatus.CONFLICT

    pending_id = _created(
        memory,
        _fact(
            text="A pending preference.",
            key="claim.pending_preference",
            value="pending",
            state=LifecycleState.PENDING_REVIEW,
            evidence=(_turn_evidence(9),),
            kind=GovernedMemoryKind.USER_PREFERENCE,
        ),
    )
    forgotten = memory.forget_fact(
        pending_id,
        expected_revision=1,
        evidence=_action_evidence(9, "forget"),
    )
    assert forgotten.value is not None
    assert forgotten.value.state == LifecycleState.FORGOTTEN.value


@pytest.mark.parametrize(
    ("initial_state", "operation_name", "expected_state"),
    [
        (LifecycleState.PENDING_REVIEW, "confirm_fact", LifecycleState.ACTIVE),
        (LifecycleState.PENDING_REVIEW, "dispute_fact", LifecycleState.DISPUTED),
        (LifecycleState.PENDING_REVIEW, "forget_fact", LifecycleState.FORGOTTEN),
        (LifecycleState.ACTIVE, "dispute_fact", LifecycleState.DISPUTED),
        (LifecycleState.ACTIVE, "expire_fact", LifecycleState.EXPIRED),
        (LifecycleState.ACTIVE, "forget_fact", LifecycleState.FORGOTTEN),
        (LifecycleState.DISPUTED, "confirm_fact", LifecycleState.ACTIVE),
        (LifecycleState.DISPUTED, "forget_fact", LifecycleState.FORGOTTEN),
    ],
)
def test_each_direct_transition_matrix_edge_is_behavior_covered(
    tmp_path: Path,
    initial_state: LifecycleState,
    operation_name: str,
    expected_state: LifecycleState,
) -> None:
    memory = SemanticMemory(tmp_path / f"{initial_state}-{operation_name}.sqlite")
    fact_id = _created(memory, _fact(state=initial_state))

    operation = getattr(memory, operation_name)
    result = operation(
        fact_id,
        expected_revision=1,
        evidence=_action_evidence(20, operation_name),
    )

    assert result.status is OperationStatus.SUCCESS
    assert result.value is not None
    assert result.value.state == expected_state.value
    assert _revision(memory) == 2


def test_correction_is_atomic_and_preserves_direct_user_action_provenance(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    fact_id = _created(memory, _fact())
    action = _action_evidence(7, "explicit_correction")
    replacement = _fact(
        text="The user lives in Milwaukee.",
        value="Milwaukee",
        evidence=(action,),
        authority=GovernedEvidenceAuthority.DIRECT_USER_ACTION,
    )

    result = memory.correct_fact(
        fact_id,
        expected_revision=1,
        replacement=replacement,
        evidence=action,
    )

    assert result.status is OperationStatus.SUCCESS
    assert result.value is not None
    assert result.value.original.state == LifecycleState.SUPERSEDED.value
    assert result.value.original.superseded_by_fact_id == result.value.replacement.fact_id
    assert result.value.replacement.state == LifecycleState.ACTIVE.value
    assert _counts(memory) == (2, 3, 4, 2)
    replacement_detail = memory.read_fact(result.value.replacement.fact_id)
    assert replacement_detail.value is not None
    action_evidence = replacement_detail.value.evidence[0]
    assert action_evidence.authority == "direct_user_action"
    assert action_evidence.source_session_id is None
    assert action_evidence.action_id == "action-7"


def test_failed_correction_rolls_back_all_rows_and_revision(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    first_id = _created(memory, _fact())
    _created(
        memory,
        _fact(
            text="Already used replacement text.",
            key="claim.other",
            value="other",
            evidence=(_turn_evidence(2),),
        ),
    )
    before = _counts(memory)
    action = _action_evidence(8, "explicit_correction")

    result = memory.correct_fact(
        first_id,
        expected_revision=1,
        replacement=_fact(
            text="Already used replacement text.",
            evidence=(action,),
            authority=GovernedEvidenceAuthority.DIRECT_USER_ACTION,
        ),
        evidence=action,
    )

    assert result.status is OperationStatus.CONFLICT
    assert _counts(memory) == before


def test_injected_correction_failure_rolls_back_partial_replacement(
    tmp_path: Path,
) -> None:
    class FailingCorrectionMemory(SemanticMemory):
        @staticmethod
        def _insert_event(
            conn: sqlite3.Connection,
            *,
            fact_id: str,
            event_type: str,
            prior_state: str | None,
            resulting_state: str | None,
            related_fact_id: str | None,
            reason_code: str,
            occurred_at: str,
            evidence: EvidenceInput | None = None,
            metadata: dict[str, object] | None = None,
        ) -> None:
            if event_type == "corrected":
                raise RuntimeError("injected correction failure")
            SemanticMemory._insert_event(
                conn,
                fact_id=fact_id,
                event_type=event_type,
                prior_state=prior_state,
                resulting_state=resulting_state,
                related_fact_id=related_fact_id,
                reason_code=reason_code,
                occurred_at=occurred_at,
                evidence=evidence,
                metadata=metadata,
            )

    memory = FailingCorrectionMemory(tmp_path / "memory.sqlite")
    fact_id = _created(memory, _fact())
    before = _counts(memory)
    action = _action_evidence(18, "explicit_correction")

    result = memory.correct_fact(
        fact_id,
        expected_revision=1,
        replacement=_fact(
            text="The user lives in Milwaukee.",
            value="Milwaukee",
            evidence=(action,),
            authority=GovernedEvidenceAuthority.DIRECT_USER_ACTION,
        ),
        evidence=action,
    )

    assert result.status is OperationStatus.UNAVAILABLE
    assert result.message == "injected correction failure"
    assert _counts(memory) == before


def test_append_evidence_is_idempotent_and_does_not_change_content_revision(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    fact_id = _created(memory, _fact())
    evidence = _turn_evidence(2)

    appended = memory.append_evidence(
        fact_id,
        evidence,
        expected_revision=1,
    )
    duplicate = memory.append_evidence(
        fact_id,
        evidence,
        expected_revision=2,
    )
    conflicting_origin = EvidenceInput(
        authority=GovernedEvidenceAuthority.ASSISTANT_INFERENCE,
        observed_at=NOW,
        source_session_id="session-1",
        source_turn_id="turn-2",
        source_field="transcript",
    )
    conflict = memory.append_evidence(
        fact_id,
        conflicting_origin,
        expected_revision=2,
    )

    assert appended.status is OperationStatus.SUCCESS
    assert appended.value is not None and appended.value.revision == 2
    assert duplicate.status is OperationStatus.NO_CHANGE
    assert conflict.status is OperationStatus.CONFLICT
    assert _counts(memory) == (1, 2, 2, 1)


def test_concurrent_reinforcement_loses_no_increment_or_evidence(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    fact_id = _created(memory, _fact())

    def reinforce(index: int) -> OperationStatus:
        return memory.reinforce_fact(
            fact_id,
            evidence=_turn_evidence(index),
            confidence=min(1.0, 0.7 + index / 100),
        ).status

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(reinforce, range(2, 10)))

    detail = memory.read_fact(fact_id)
    assert statuses == [OperationStatus.SUCCESS] * 8
    assert detail.value is not None
    assert detail.value.fact.reinforcement_count == 9
    assert detail.value.fact.revision == 9
    assert len(detail.value.evidence) == 9
    assert _revision(memory) == 9
    duplicate = memory.reinforce_fact(fact_id, evidence=_turn_evidence(9))
    assert duplicate.status is OperationStatus.NO_CHANGE
    assert _revision(memory) == 9


def test_supersession_rejects_self_unrelated_identity_and_cycles(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    original_id = _created(memory, _fact())
    other_id = _created(
        memory,
        _fact(
            text="The user prefers Vim.",
            key="claim.editor",
            value="vim",
            evidence=(_turn_evidence(2),),
            kind=GovernedMemoryKind.USER_PREFERENCE,
        ),
    )
    action = _action_evidence(4, "supersede")
    before = _counts(memory)

    assert (
        memory.supersede_fact(
            original_id,
            related_fact_id=original_id,
            expected_revision=1,
            evidence=action,
        ).status
        is OperationStatus.INVALID
    )
    assert (
        memory.supersede_fact(
            original_id,
            related_fact_id=other_id,
            expected_revision=1,
            evidence=action,
        ).status
        is OperationStatus.CONFLICT
    )
    assert _counts(memory) == before

    with memory._get_conn() as conn:
        conn.execute(
            """
            UPDATE semantic_fact
            SET kind = 'personal_fact',
                claim_key = 'claim.home_city',
                superseded_by_fact_id = ?
            WHERE fact_id = ?
            """,
            (original_id, other_id),
        )
    cycle = memory.supersede_fact(
        original_id,
        related_fact_id=other_id,
        expected_revision=1,
        evidence=action,
    )
    assert cycle.status is OperationStatus.CONFLICT


def test_explicit_related_supersession_from_disputed_is_traceable(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    original_id = _created(memory, _fact())
    proposed = memory.create_governed_fact(
        _fact(
            text="The user lives in Milwaukee.",
            value="Milwaukee",
            evidence=(_turn_evidence(2),),
        )
    )
    assert proposed.value is not None
    replacement_id = proposed.value.fact_id
    disputed = memory.dispute_fact(
        original_id,
        expected_revision=1,
        evidence=_action_evidence(31, "dispute_before_supersession"),
    )
    assert disputed.status is OperationStatus.SUCCESS
    activated = memory.confirm_fact(
        replacement_id,
        expected_revision=1,
        evidence=_action_evidence(32, "confirm_replacement"),
    )
    assert activated.status is OperationStatus.SUCCESS

    superseded = memory.supersede_fact(
        original_id,
        related_fact_id=replacement_id,
        expected_revision=2,
        evidence=_action_evidence(33, "supersede"),
    )

    assert superseded.status is OperationStatus.SUCCESS
    assert superseded.value is not None
    assert superseded.value.state == LifecycleState.SUPERSEDED.value
    assert superseded.value.superseded_by_fact_id == replacement_id
    detail = memory.read_fact(original_id)
    assert detail.value is not None
    assert detail.value.events[-1].related_fact_id == replacement_id
    assert detail.value.events[-1].event_type == "superseded"


def test_unknown_legacy_kind_remains_inspectable_but_not_mutable(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    fact_id = memory.write_fact("Legacy fact")
    assert fact_id is not None

    detail = memory.read_fact(fact_id)
    mutation = memory.dispute_fact(
        fact_id,
        expected_revision=1,
        evidence=_action_evidence(),
    )

    assert detail.status is OperationStatus.SUCCESS
    assert detail.value is not None and detail.value.fact.kind == "fact"
    assert mutation.status is OperationStatus.CONFLICT


def test_policy_defaults_disabled_and_rejects_stale_writes(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    policy = memory.read_policy()
    assert policy.value is not None
    assert policy.value.automatic_curation_enabled is False
    assert policy.value.revision == 1

    enabled = memory.update_policy(
        automatic_curation_enabled=True,
        expected_revision=1,
    )
    stale = memory.update_policy(
        automatic_curation_enabled=False,
        expected_revision=1,
    )
    unchanged = memory.update_policy(
        automatic_curation_enabled=True,
        expected_revision=2,
    )

    assert enabled.status is OperationStatus.SUCCESS
    assert enabled.value is not None and enabled.value.revision == 2
    assert stale.status is OperationStatus.CONFLICT
    assert unchanged.status is OperationStatus.NO_CHANGE
    assert _revision(memory) == 0


def test_curation_jobs_are_idempotent_claimable_and_restart_safe(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    enqueued = memory.enqueue_curation_job(
        session_id="session-1",
        artifact_ref="sessions/session-1/session.json",
    )
    duplicate = memory.enqueue_curation_job(
        session_id="session-1",
        artifact_ref="sessions/session-1/session.json",
    )
    conflict = memory.enqueue_curation_job(
        session_id="session-1",
        artifact_ref="different.json",
    )
    listed = memory.list_curation_jobs(max_attempts=3)
    claimed = memory.claim_curation_job(
        worker_id="worker-1",
        max_attempts=3,
        lease_seconds=30,
    )

    assert enqueued.status is OperationStatus.SUCCESS
    assert duplicate.status is OperationStatus.NO_CHANGE
    assert conflict.status is OperationStatus.CONFLICT
    assert listed.value is not None and len(listed.value) == 1
    assert claimed.value is not None
    assert claimed.value.status is CurationJobStatus.PROCESSING
    assert claimed.value.attempt_count == 1
    lease = claimed.value.lease_token
    assert lease is not None

    failed = memory.fail_curation_job(
        session_id="session-1",
        lease_token=lease,
        reason="processor_error",
        error="bounded failure",
    )
    reclaimed = memory.claim_curation_job(
        worker_id="worker-2",
        max_attempts=3,
        lease_seconds=30,
    )
    assert failed.value is not None
    assert failed.value.status is CurationJobStatus.FAILED
    assert reclaimed.value is not None
    assert reclaimed.value.attempt_count == 2
    returned = memory.return_curation_job_to_pending(
        session_id="session-1",
        lease_token=reclaimed.value.lease_token or "",
        reason="shutdown",
    )
    assert returned.value is not None
    assert returned.value.status is CurationJobStatus.PENDING
    exhausted = memory.claim_curation_job(
        worker_id="worker-3",
        max_attempts=2,
        lease_seconds=30,
    )
    assert exhausted.status is OperationStatus.NOT_FOUND
    assert _revision(memory) == 0


def test_curation_claim_is_atomic_and_reads_do_not_recover_stale_jobs(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    memory.enqueue_curation_job(
        session_id="session-1",
        artifact_ref="sessions/session-1/session.json",
    )

    def claim(worker: str) -> OperationStatus:
        return memory.claim_curation_job(
            worker_id=worker,
            max_attempts=2,
            lease_seconds=1,
        ).status

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(claim, ("worker-1", "worker-2")))
    assert sorted(statuses) == sorted([OperationStatus.SUCCESS, OperationStatus.NOT_FOUND])

    jobs_before = memory.list_curation_jobs(max_attempts=2)
    assert jobs_before.value == ()
    recovered = memory.recover_stale_curation_jobs(recovered_at="2099-01-01T00:00:00+00:00")
    jobs_after = memory.list_curation_jobs(max_attempts=2)
    assert recovered.value == 1
    assert jobs_after.value is not None
    assert len(jobs_after.value) == 1
    assert jobs_after.value[0].status is CurationJobStatus.PENDING


def test_curation_jobs_can_complete_and_cancel_with_owned_leases(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    for session_id in ("session-a", "session-b"):
        memory.enqueue_curation_job(
            session_id=session_id,
            artifact_ref=f"sessions/{session_id}/session.json",
        )

    first = memory.claim_curation_job(
        worker_id="worker-1",
        max_attempts=2,
        lease_seconds=30,
    )
    assert first.value is not None and first.value.lease_token is not None
    completed = memory.complete_curation_job(
        session_id=first.value.session_id,
        lease_token=first.value.lease_token,
    )
    second = memory.claim_curation_job(
        worker_id="worker-1",
        max_attempts=2,
        lease_seconds=30,
    )
    assert second.value is not None and second.value.lease_token is not None
    cancelled = memory.cancel_curation_job(
        session_id=second.value.session_id,
        lease_token=second.value.lease_token,
        reason="user_cancelled",
    )

    assert completed.value is not None
    assert completed.value.status is CurationJobStatus.COMPLETED
    assert cancelled.value is not None
    assert cancelled.value.status is CurationJobStatus.CANCELLED
    assert memory.list_curation_jobs(max_attempts=2).value == ()
    assert _revision(memory) == 0


def test_bounded_busy_conflict_does_not_partially_mutate(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite"
    memory = SemanticMemory(db_path)
    before = _counts(memory)
    lock = sqlite3.connect(db_path)
    try:
        lock.execute("BEGIN IMMEDIATE")
        result = memory.update_policy(
            automatic_curation_enabled=True,
            expected_revision=1,
        )
    finally:
        lock.rollback()
        lock.close()

    assert result.status is OperationStatus.BUSY
    assert _counts(memory) == before


def test_legacy_write_increments_revision_once_and_preserves_dedup(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    fact_id = memory.write_fact("Legacy compatibility fact")
    duplicate_id = memory.write_fact("Legacy compatibility fact")

    assert fact_id is not None and duplicate_id == fact_id
    assert _counts(memory) == (1, 0, 0, 1)


def test_application_boundary_rejects_invalid_fact_and_evidence_inputs() -> None:
    with pytest.raises(CurationValidationError, match="timezone"):
        _turn_evidence().__class__(
            authority=GovernedEvidenceAuthority.DIRECT_USER_STATEMENT,
            observed_at="2026-07-24T12:00:00",
            source_session_id="session",
            source_turn_id="turn",
            source_field="transcript",
        )
    with pytest.raises(CurationValidationError, match="finite"):
        _fact().__class__(
            text="Invalid score",
            identity=GovernedClaimIdentity(
                kind=GovernedMemoryKind.PERSONAL_FACT,
                claim_key="claim.invalid_score",
            ),
            value_text="value",
            evidence_authority=GovernedEvidenceAuthority.DIRECT_USER_STATEMENT,
            state=LifecycleState.ACTIVE,
            confidence=float("nan"),
            importance=0.5,
            evidence=(_turn_evidence(),),
        )
