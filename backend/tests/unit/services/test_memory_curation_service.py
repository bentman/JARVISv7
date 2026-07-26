from __future__ import annotations

import threading
import time
from pathlib import Path

from backend.app.artifacts.session_artifact import SessionArtifact
from backend.app.artifacts.storage import (
    write_session_artifact,
    write_turn_artifact,
)
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.memory.curation import CurationJobStatus, OperationStatus
from backend.app.memory.semantic import SemanticMemory
from backend.app.services.llm_execution_coordinator import LLMExecutionCoordinator
from backend.app.services.memory_curation_service import (
    CurationProcessorResult,
    MemoryCurationService,
)

NOW = "2026-07-24T12:00:00+00:00"


def test_enqueued_authorized_job_runs_during_normal_runtime(tmp_path: Path) -> None:
    memory, sessions, turns, artifact_path = _authorized_job(tmp_path)
    processed = threading.Event()

    def processor(_evidence) -> CurationProcessorResult:
        processed.set()
        return CurationProcessorResult(success=True, durable=True)

    service = _service(memory, sessions, turns, processor=processor)
    enqueue = service.enqueue_closed_session(
        session_id="session-1",
        artifact_path=artifact_path,
        policy_revision=2,
        authorized_at=NOW,
    )
    try:
        assert enqueue.status is OperationStatus.SUCCESS
        assert processed.wait(1)
        job = _wait_for_job(memory, "session-1", CurationJobStatus.SUCCEEDED)
        assert job is not None and job.status is CurationJobStatus.SUCCEEDED
    finally:
        service.stop()


def test_missing_artifact_is_visible_terminal_failure_without_processor_call(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    memory.update_policy(automatic_curation_enabled=True, expected_revision=1)
    calls: list[object] = []
    service = _service(
        memory,
        tmp_path / "sessions",
        tmp_path / "turns",
        processor=lambda evidence: calls.append(evidence),  # type: ignore[arg-type]
    )
    missing = tmp_path / "sessions" / "session-1" / "session.json"
    memory.enqueue_curation_job(
        session_id="session-1",
        artifact_ref=str(missing),
        policy_revision=2,
        authorized_at=NOW,
    )

    result = service.drain(timeout=1)
    job = memory.read_curation_job("session-1").value
    service.stop()

    assert result.outcome == "completed"
    assert calls == []
    assert job is not None and job.status is CurationJobStatus.FAILED
    assert job.last_error_code == "source_artifact_missing"


def test_processor_exception_enters_retry_wait_with_bounded_error(
    tmp_path: Path,
) -> None:
    memory, sessions, turns, artifact_path = _authorized_job(tmp_path)

    def processor(_evidence):
        raise RuntimeError("secret " + "x" * 4000)

    service = _service(memory, sessions, turns, processor=processor)
    memory.enqueue_curation_job(
        session_id="session-1",
        artifact_ref=str(artifact_path),
        policy_revision=2,
        authorized_at=NOW,
    )

    service.drain(timeout=1)
    job = memory.read_curation_job("session-1").value
    service.stop()

    assert job is not None and job.status is CurationJobStatus.RETRY_WAIT
    assert job.last_error_code == "processor_exception"
    assert job.last_error_detail is not None
    assert len(job.last_error_detail) <= 2048


def test_retry_wait_job_wakes_and_reprocesses_without_a_new_enqueue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    memory, sessions, turns, artifact_path = _authorized_job(tmp_path)
    calls = 0
    monkeypatch.setattr(
        "backend.app.memory.semantic.CURATION_RETRY_DELAYS_SECONDS",
        (0.01, 0.01),
    )

    def processor(_evidence) -> CurationProcessorResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return CurationProcessorResult(
                success=False,
                durable=False,
                reason_code="temporary_failure",
                retryable=True,
            )
        return CurationProcessorResult(success=True, durable=True)

    service = _service(memory, sessions, turns, processor=processor)
    try:
        service.enqueue_closed_session(
            session_id="session-1",
            artifact_path=artifact_path,
            policy_revision=2,
            authorized_at=NOW,
        )
        job = _wait_for_job(memory, "session-1", CurationJobStatus.SUCCEEDED)
        assert job is not None and job.attempt_count == 2
        assert calls == 2
    finally:
        service.stop()


def test_previous_boot_processing_is_recovered_and_fenced(tmp_path: Path) -> None:
    memory, sessions, turns, artifact_path = _authorized_job(tmp_path)
    memory.enqueue_curation_job(
        session_id="session-1",
        artifact_ref=str(artifact_path),
        policy_revision=2,
        authorized_at=NOW,
    )
    claimed = memory.claim_curation_job(
        worker_id="old-boot",
        boot_id="old-boot",
        max_attempts=3,
        lease_seconds=120,
    )
    assert claimed.value is not None and claimed.value.claim_token is not None

    service = _service(
        memory,
        sessions,
        turns,
        processor=lambda _evidence: CurationProcessorResult(True, True),
        boot_id="new-boot",
    )
    try:
        recovered = service.recover_and_reconcile()
        job = _wait_for_job(memory, "session-1", CurationJobStatus.SUCCEEDED)
        assert recovered.status is OperationStatus.SUCCESS
        assert job is not None and job.status is CurationJobStatus.SUCCEEDED
    finally:
        service.stop()


def test_status_is_side_effect_free(tmp_path: Path) -> None:
    memory, sessions, turns, artifact_path = _authorized_job(tmp_path)
    service = _service(memory, sessions, turns, processor=None)
    memory.enqueue_curation_job(
        session_id="session-1",
        artifact_ref=str(artifact_path),
        policy_revision=2,
        authorized_at=NOW,
    )
    before = memory.read_curation_job("session-1").value

    first = service.status()
    second = service.status()
    after = memory.read_curation_job("session-1").value

    assert first.jobs == second.jobs
    assert before == after


def _authorized_job(
    tmp_path: Path,
) -> tuple[SemanticMemory, Path, Path, Path]:
    sessions = tmp_path / "sessions"
    turns = tmp_path / "turns"
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    enabled = memory.update_policy(
        automatic_curation_enabled=True,
        expected_revision=1,
    )
    assert enabled.status is OperationStatus.SUCCESS
    turn = TurnArtifact(
        turn_id="turn-1",
        session_id="session-1",
        input_modality="text",
        final_state="IDLE",
        transcript="remember this",
        response_text="acknowledged",
    )
    write_turn_artifact(turn, turns)
    artifact = SessionArtifact(
        session_id="session-1",
        started_at=NOW,
        ended_at=NOW,
        turn_ids=[turn.turn_id],
        final_state="IDLE",
        memory_curation_candidate=True,
        memory_curation_authorized_at=NOW,
        memory_curation_policy_revision=2,
    )
    artifact_path = write_session_artifact(artifact, sessions)
    return memory, sessions, turns, artifact_path


def _wait_for_job(
    memory: SemanticMemory,
    session_id: str,
    status: CurationJobStatus,
):
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        job = memory.read_curation_job(session_id).value
        if job is not None and job.status is status:
            return job
        time.sleep(0.01)
    return memory.read_curation_job(session_id).value


def _service(
    memory: SemanticMemory,
    sessions: Path,
    turns: Path,
    *,
    processor,
    boot_id: str = "test-boot",
) -> MemoryCurationService:
    return MemoryCurationService(
        semantic_memory=memory,
        sessions_root=sessions,
        turns_root=turns,
        coordinator=LLMExecutionCoordinator(),
        session_is_active=lambda: False,
        processor=processor,
        runtime_status=lambda: {
            "ready": True,
            "runtime_name": "fake",
            "model_id": "fake-model",
            "serve_profile_id": "test",
            "accelerator": "cpu",
        },
        boot_id=boot_id,
    )
