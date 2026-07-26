from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from backend.app.memory.curation import CurationJobStatus, OperationStatus
from backend.app.memory.semantic import SemanticMemory


def _enabled_memory(tmp_path: Path) -> SemanticMemory:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    enabled = memory.update_policy(
        automatic_curation_enabled=True,
        expected_revision=1,
    )
    assert enabled.status is OperationStatus.SUCCESS
    return memory


def test_disabling_policy_cancels_queued_and_claimed_jobs(tmp_path: Path) -> None:
    memory = _enabled_memory(tmp_path)
    for session_id in ("pending", "processing"):
        queued = memory.enqueue_curation_job(
            session_id=session_id,
            artifact_ref=f"sessions/{session_id}/session.json",
            policy_revision=2,
        )
        assert queued.status is OperationStatus.SUCCESS
    claimed = memory.claim_curation_job(
        worker_id="boot",
        boot_id="boot",
        max_attempts=3,
        lease_seconds=120,
    )
    assert claimed.value is not None and claimed.value.claim_token is not None

    disabled = memory.update_policy(
        automatic_curation_enabled=False,
        expected_revision=2,
    )
    completed = memory.complete_curation_job(
        session_id=claimed.value.session_id,
        lease_token=claimed.value.claim_token,
        boot_id="boot",
    )
    jobs = memory.list_curation_jobs(max_attempts=4, include_terminal=True).value

    assert disabled.status is OperationStatus.SUCCESS
    assert completed.value is not None
    assert completed.value.status is CurationJobStatus.CANCELLED
    assert jobs is not None
    assert {job.status for job in jobs} == {CurationJobStatus.CANCELLED}


def test_stale_recovery_fences_an_old_claim_before_reprocessing(tmp_path: Path) -> None:
    memory = _enabled_memory(tmp_path)
    queued = memory.enqueue_curation_job(
        session_id="session-1",
        artifact_ref="sessions/session-1/session.json",
        policy_revision=2,
    )
    assert queued.status is OperationStatus.SUCCESS
    old_claim = memory.claim_curation_job(
        worker_id="old-boot",
        boot_id="old-boot",
        max_attempts=3,
        lease_seconds=120,
    )
    assert old_claim.value is not None and old_claim.value.claim_token is not None

    recovered = memory.recover_stale_curation_jobs(
        current_boot_id="new-boot",
        recovered_at=datetime.now(UTC).isoformat(),
    )
    new_claim = memory.claim_curation_job(
        worker_id="new-boot",
        boot_id="new-boot",
        max_attempts=3,
        lease_seconds=120,
    )
    assert new_claim.value is not None and new_claim.value.claim_token is not None
    completed = memory.complete_curation_job(
        session_id="session-1",
        lease_token=new_claim.value.claim_token,
        boot_id="new-boot",
    )
    stale_completion = memory.complete_curation_job(
        session_id="session-1",
        lease_token=old_claim.value.claim_token,
        boot_id="old-boot",
    )

    assert recovered.value == 1
    assert completed.value is not None
    assert completed.value.status is CurationJobStatus.SUCCEEDED
    assert stale_completion.status is OperationStatus.CONFLICT
