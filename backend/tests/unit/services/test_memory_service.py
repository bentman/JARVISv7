from __future__ import annotations

from pathlib import Path

import pytest
from backend.app.memory.curation import (
    EvidenceInput,
    GovernedEvidenceAuthority,
    GovernedFactInput,
    LifecycleState,
)
from backend.app.memory.curation_contract import (
    GovernedClaimIdentity,
    GovernedMemoryKind,
)
from backend.app.memory.semantic import SemanticMemory
from backend.app.services.llm_execution_coordinator import LLMExecutionCoordinator
from backend.app.services.memory_curation_service import MemoryCurationService
from backend.app.services.memory_service import MemoryService, MemoryServiceError

NOW = "2026-07-25T12:00:00+00:00"


def _evidence(turn: int = 1) -> EvidenceInput:
    return EvidenceInput(
        authority=GovernedEvidenceAuthority.DIRECT_USER_STATEMENT,
        observed_at=NOW,
        source_session_id="session-safe",
        source_turn_id=f"turn-{turn}",
        source_field="transcript",
        metadata={"raw_model_output": "must-not-leak"},
    )


def _create(
    memory: SemanticMemory,
    *,
    key: str,
    state: LifecycleState,
    kind: GovernedMemoryKind = GovernedMemoryKind.PERSONAL_FACT,
    text: str | None = None,
):
    result = memory.create_governed_fact(
        GovernedFactInput(
            text=text or f"fact for {key}",
            identity=GovernedClaimIdentity(kind=kind, claim_key=key),
            value_text="safe-value",
            evidence_authority=GovernedEvidenceAuthority.DIRECT_USER_STATEMENT,
            state=state,
            confidence=0.8,
            importance=0.7,
            evidence=(_evidence(),),
            vector=(0.1, 0.2),
            vectorizer_id="internal-vectorizer",
            metadata={
                "database_path": "C:/private/memory.sqlite",
                "raw_model_output": "must-not-leak",
            },
        )
    )
    assert result.value is not None
    return result.value


def _service(tmp_path: Path) -> tuple[MemoryService, SemanticMemory]:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    return MemoryService(semantic_memory=memory, curation_service=None), memory


def test_policy_is_opt_in_persisted_and_stale_conflict_is_actionable(tmp_path: Path) -> None:
    service, _memory = _service(tmp_path)

    initial = service.read_policy()
    updated = service.update_policy(
        automatic_curation_enabled=True,
        expected_revision=initial.revision,
    )

    assert initial.automatic_curation_enabled is False
    assert updated.automatic_curation_enabled is True
    assert service.read_policy() == updated
    with pytest.raises(MemoryServiceError) as caught:
        service.update_policy(
            automatic_curation_enabled=False,
            expected_revision=initial.revision,
        )
    assert caught.value.status_code == 409
    assert caught.value.detail() == {
        "error": "conflict",
        "message": "update policy conflicted with the current governed state",
        "current_revision": updated.revision,
        "current_state": "enabled",
    }


def test_default_list_is_stable_bounded_attention_only_and_side_effect_free(
    tmp_path: Path,
) -> None:
    service, memory = _service(tmp_path)
    active = _create(memory, key="profile.active", state=LifecycleState.ACTIVE)
    pending = _create(memory, key="profile.pending", state=LifecycleState.PENDING_REVIEW)
    disputed = _create(memory, key="profile.disputed", state=LifecycleState.DISPUTED)
    forgotten = _create(memory, key="profile.forgotten", state=LifecycleState.ACTIVE)
    forgotten_result = service.forget(
        forgotten.fact_id,
        expected_revision=forgotten.revision,
        reason=None,
    )
    revision_before = memory.read_content_revision().value

    first = service.list_records(state=None, kind=None, query=None, offset=0, limit=2)
    second = service.list_records(state=None, kind=None, query=None, offset=0, limit=2)
    history = service.list_records(
        state=LifecycleState.FORGOTTEN,
        kind=None,
        query=None,
        offset=0,
        limit=20,
    )

    assert first == second
    assert first.returned_count == 2
    assert first.has_more is True
    assert first.next_offset == 2
    assert {
        record.fact_id
        for record in service.list_records(
            state=None,
            kind=None,
            query=None,
            offset=0,
            limit=20,
        ).records
    } == {active.fact_id, pending.fact_id, disputed.fact_id}
    assert [record.fact_id for record in history.records] == [forgotten.fact_id]
    assert history.records[0].lifecycle_state == forgotten_result.record.lifecycle_state
    assert memory.read_content_revision().value == revision_before


def test_detail_is_bounded_signals_truncation_and_omits_internal_data(tmp_path: Path) -> None:
    service, memory = _service(tmp_path)
    fact = _create(memory, key="profile.detail", state=LifecycleState.PENDING_REVIEW)
    appended = memory.append_evidence(fact.fact_id, _evidence(2))
    assert appended.value is not None

    detail = service.read_record(fact.fact_id, evidence_limit=1, events_limit=1)
    payload = repr(detail)

    assert detail.evidence_total == 2
    assert detail.evidence_returned == 1
    assert detail.evidence_truncated is True
    assert detail.events_total == 2
    assert detail.events_returned == 1
    assert detail.events_truncated is True
    assert detail.record.eligible_for_normal_retrieval is False
    assert "separate evidence" in detail.forgetting_scope
    assert "raw_model_output" not in payload
    assert "database_path" not in payload
    assert "internal-vectorizer" not in payload
    assert "vector" not in payload


def test_lifecycle_mutations_reuse_revisioned_transitions(tmp_path: Path) -> None:
    service, memory = _service(tmp_path)
    pending = _create(memory, key="profile.lifecycle", state=LifecycleState.PENDING_REVIEW)

    confirmed = service.confirm(pending.fact_id, expected_revision=pending.revision, reason=None)
    assert confirmed.lifecycle_state == LifecycleState.ACTIVE.value
    assert confirmed.revision == pending.revision + 1
    assert confirmed.eligible_for_normal_retrieval is True

    with pytest.raises(MemoryServiceError) as stale:
        service.dispute(pending.fact_id, expected_revision=pending.revision, reason=None)
    assert stale.value.status_code == 409
    assert stale.value.current_revision == confirmed.revision
    assert stale.value.current_state == LifecycleState.ACTIVE.value

    disputed = service.dispute(
        pending.fact_id,
        expected_revision=confirmed.revision,
        reason="user challenged the record",
    )
    assert disputed.lifecycle_state == LifecycleState.DISPUTED.value
    forgotten = service.forget(
        pending.fact_id,
        expected_revision=disputed.revision,
        reason=None,
    )
    assert forgotten.record.lifecycle_state == LifecycleState.FORGOTTEN.value

    with pytest.raises(MemoryServiceError) as invalid:
        service.confirm(
            pending.fact_id,
            expected_revision=forgotten.record.revision,
            reason=None,
        )
    assert invalid.value.status_code == 409
    assert memory.read_fact(pending.fact_id).value.fact.revision == forgotten.record.revision


def test_correction_preserves_claim_identity_and_returns_supersession(tmp_path: Path) -> None:
    service, memory = _service(tmp_path)
    original = _create(
        memory,
        key="profile.correction",
        kind=GovernedMemoryKind.USER_PREFERENCE,
        state=LifecycleState.ACTIVE,
    )

    corrected = service.correct(
        original.fact_id,
        expected_revision=original.revision,
        replacement_text="I prefer concise answers.",
        replacement_value="concise",
        reason="user supplied a correction",
    )

    assert corrected.original.fact_id == original.fact_id
    assert corrected.original.lifecycle_state == LifecycleState.SUPERSEDED.value
    assert corrected.original.superseded_by_fact_id == corrected.replacement.fact_id
    assert corrected.replacement.lifecycle_state == LifecycleState.ACTIVE.value
    assert corrected.replacement.kind == original.kind
    assert corrected.replacement.claim_key == original.claim_key
    assert corrected.replacement.value == "concise"
    assert corrected.relation == "replacement_supersedes_original"


def test_curation_status_is_sanitized_and_does_not_trigger_drain(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    curation = MemoryCurationService(
        semantic_memory=memory,
        sessions_root=tmp_path / "sessions",
        turns_root=tmp_path / "turns",
        coordinator=LLMExecutionCoordinator(),
        session_is_active=lambda: False,
        processor=None,
    )
    service = MemoryService(semantic_memory=memory, curation_service=curation)

    status = service.curation_status()

    assert status.service_available is True
    assert status.automatic_curation_enabled is False
    assert status.worker_running is False
    assert status.processor_available is False
    assert status.degraded is True
    assert status.degraded_reason == "processor_unavailable"
    assert status.retry_blocked is True
    assert status.jobs_returned == 0
    assert status.jobs_truncated is False
    assert status.recent_jobs == ()
    assert curation.status().drain_active is False


def test_curation_status_exposes_only_durable_processor_summary(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    enabled = memory.update_policy(
        automatic_curation_enabled=True,
        expected_revision=1,
    )
    assert enabled.value is not None
    memory.enqueue_curation_job(
        session_id="session-result",
        artifact_ref="C:/private/source.json",
        policy_revision=enabled.value.revision,
    )
    claimed = memory.claim_curation_job(
        worker_id="boot",
        boot_id="boot",
        max_attempts=3,
        lease_seconds=30,
    )
    assert claimed.value is not None and claimed.value.claim_token is not None
    memory.complete_curation_job(
        session_id="session-result",
        lease_token=claimed.value.claim_token,
        boot_id="boot",
        reason="review_only_candidates_resolved",
        candidates_proposed=3,
        candidates_rejected=1,
        pending_review_created=2,
        duplicate_noops=1,
    )
    curation = MemoryCurationService(
        semantic_memory=memory,
        sessions_root=tmp_path / "sessions",
        turns_root=tmp_path / "turns",
        coordinator=LLMExecutionCoordinator(),
        session_is_active=lambda: False,
        processor=lambda _evidence: None,  # type: ignore[arg-type]
    )

    status = MemoryService(
        semantic_memory=memory,
        curation_service=curation,
    ).curation_status()

    assert status.last_result is not None
    assert status.last_result.reason_code == "review_only_candidates_resolved"
    assert status.last_result.candidates_proposed == 3
    assert status.last_result.pending_review_created == 2
    assert status.recent_jobs[0].result == status.last_result
    assert "private" not in repr(status)
