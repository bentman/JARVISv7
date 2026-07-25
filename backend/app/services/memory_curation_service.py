from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from backend.app.artifacts.session_artifact import SessionArtifact
from backend.app.artifacts.storage import read_turn_artifact
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.memory.curation import (
    CurationJob,
    CurationJobStatus,
    OperationStatus,
    StoreResult,
)
from backend.app.memory.semantic import SemanticMemory
from backend.app.services.llm_execution_coordinator import LLMExecutionCoordinator

MAX_TURNS_PER_JOB = 100
MAX_STATUS_JOBS = 100
MAX_ENQUEUE_FAILURES = 20
LEASE_SECONDS = 120
MAX_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class PersistedSessionEvidence:
    session: SessionArtifact
    turns: tuple[TurnArtifact, ...]
    artifact_path: Path


@dataclass(frozen=True, slots=True)
class CurationProcessorResult:
    success: bool
    durable: bool
    reason_code: str = "processor_succeeded"
    error_detail: str | None = None
    retryable: bool = True
    candidates_proposed: int = 0
    candidates_rejected: int = 0
    active_records_created: int = 0
    pending_review_created: int = 0
    records_reinforced: int = 0
    records_superseded_or_disputed: int = 0
    duplicate_noops: int = 0
    failure_count: int = 0

    def __post_init__(self) -> None:
        counts = (
            self.candidates_proposed,
            self.candidates_rejected,
            self.active_records_created,
            self.pending_review_created,
            self.records_reinforced,
            self.records_superseded_or_disputed,
            self.duplicate_noops,
            self.failure_count,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= 3
            for value in counts
        ):
            raise ValueError("processor result counts must be integers between 0 and 3")
        if not self.reason_code or len(self.reason_code) > 128:
            raise ValueError("processor reason_code must contain 1..128 characters")
        if self.error_detail is not None and len(self.error_detail) > 2048:
            raise ValueError("processor error_detail must not exceed 2048 characters")


class CurationProcessor(Protocol):
    def __call__(self, evidence: PersistedSessionEvidence) -> CurationProcessorResult: ...


@dataclass(frozen=True, slots=True)
class DrainResult:
    outcome: str
    job_id: str | None
    remaining_queued: int
    running: bool
    blocked_reason: str | None = None


@dataclass(frozen=True, slots=True)
class EnqueueFailure:
    session_id: str
    artifact_path: str
    status: str
    error: str | None
    occurred_at: str


@dataclass(frozen=True, slots=True)
class MemoryCurationStatus:
    boot_id: str
    worker_running: bool
    drain_active: bool
    processor_available: bool
    coordinator: dict[str, object]
    jobs: tuple[dict[str, object], ...]
    enqueue_failures: tuple[EnqueueFailure, ...]


RuntimeStatus = Callable[[], dict[str, str | bool | None]]


class MemoryCurationService:
    """One explicit-drain worker backed exclusively by SemanticMemory jobs."""

    def __init__(
        self,
        *,
        semantic_memory: SemanticMemory,
        sessions_root: Path,
        turns_root: Path,
        coordinator: LLMExecutionCoordinator,
        session_is_active: Callable[[], bool],
        processor: CurationProcessor | None,
        runtime_status: RuntimeStatus | None = None,
        boot_id: str | None = None,
    ) -> None:
        self._memory = semantic_memory
        self._sessions_root = sessions_root
        self._turns_root = turns_root
        self._coordinator = coordinator
        self._session_is_active = session_is_active
        self._processor = processor
        self._runtime_status = runtime_status or (lambda: {"ready": False})
        self.boot_id = boot_id or uuid.uuid4().hex
        self._condition = threading.Condition()
        self._worker: threading.Thread | None = None
        self._stop_requested = False
        self._drain_requested = False
        self._drain_done: threading.Event | None = None
        self._drain_result: DrainResult | None = None
        self._enqueue_failures: deque[EnqueueFailure] = deque(maxlen=MAX_ENQUEUE_FAILURES)

    def recover_and_reconcile(self) -> StoreResult[int]:
        recovered = self._memory.recover_stale_curation_jobs(
            current_boot_id=self.boot_id,
            reason="previous_boot_recovered",
        )
        if not recovered.succeeded:
            return recovered
        reconciled = 0
        if self._sessions_root.exists():
            for artifact_path in sorted(self._sessions_root.glob("*/session.json")):
                try:
                    artifact = SessionArtifact.from_json(
                        artifact_path.read_text(encoding="utf-8")
                    )
                except Exception:
                    continue
                if (
                    not artifact.memory_curation_candidate
                    or artifact.memory_curation_authorized_at is None
                    or artifact.memory_curation_policy_revision is None
                ):
                    continue
                result = self.enqueue_closed_session(
                    session_id=artifact.session_id,
                    artifact_path=artifact_path,
                    policy_revision=artifact.memory_curation_policy_revision,
                    authorized_at=artifact.memory_curation_authorized_at,
                )
                if result.status is OperationStatus.SUCCESS:
                    reconciled += 1
        return StoreResult(OperationStatus.SUCCESS, int(recovered.value or 0) + reconciled)

    def start(self) -> None:
        with self._condition:
            if self._worker is not None and self._worker.is_alive():
                return
            self._stop_requested = False
            self._worker = threading.Thread(
                target=self._run,
                name="jarvis-memory-curation",
                daemon=True,
            )
            self._worker.start()

    def stop(self, timeout: float = 1.0) -> bool:
        self._coordinator.mark_stopping()
        with self._condition:
            self._stop_requested = True
            self._condition.notify_all()
            worker = self._worker
        if worker is not None:
            worker.join(max(0.0, timeout))
        return worker is None or not worker.is_alive()

    def enqueue_closed_session(
        self,
        *,
        session_id: str,
        artifact_path: Path,
        policy_revision: int,
        authorized_at: str,
    ) -> StoreResult[CurationJob]:
        result = self._memory.enqueue_curation_job(
            session_id=session_id,
            artifact_ref=str(artifact_path),
            policy_revision=policy_revision,
            authorized_at=authorized_at,
        )
        if result.status not in {OperationStatus.SUCCESS, OperationStatus.NO_CHANGE}:
            self._enqueue_failures.append(
                EnqueueFailure(
                    session_id=session_id,
                    artifact_path=str(artifact_path),
                    status=result.status.value,
                    error=(result.message or "")[:2048] or None,
                    occurred_at=datetime.now(UTC).isoformat(),
                )
            )
        return result

    def drain(self, timeout: float = 8.0) -> DrainResult:
        self._coordinator.begin_shutdown_drain()
        self.start()
        done = threading.Event()
        with self._condition:
            if self._drain_requested:
                return self._snapshot_drain("blocked", "drain_already_running")
            self._drain_requested = True
            self._drain_done = done
            self._drain_result = None
            self._condition.notify_all()
        if not done.wait(max(0.0, timeout)):
            return self._snapshot_drain("timed_out", None)
        with self._condition:
            return self._drain_result or self._snapshot_drain("blocked", "unknown")

    def status(self) -> MemoryCurationStatus:
        jobs_result = self._memory.list_curation_jobs(
            max_attempts=MAX_ATTEMPTS + 1,
            limit=MAX_STATUS_JOBS,
            include_terminal=True,
        )
        jobs = jobs_result.value or ()
        now = time.time()
        job_payloads: list[dict[str, object]] = []
        for job in jobs:
            payload = asdict(job)
            try:
                enqueued_epoch = datetime.fromisoformat(job.enqueued_at).timestamp()
                payload["starved"] = (
                    job.status in {CurationJobStatus.PENDING, CurationJobStatus.RETRY_WAIT}
                    and now - enqueued_epoch >= 86_400
                )
            except ValueError:
                payload["starved"] = False
            job_payloads.append(payload)
        with self._condition:
            worker_running = self._worker is not None and self._worker.is_alive()
        return MemoryCurationStatus(
            boot_id=self.boot_id,
            worker_running=worker_running,
            drain_active=self._coordinator.shutdown_drain_active,
            processor_available=self._processor is not None,
            coordinator=self._coordinator.snapshot(),
            jobs=tuple(job_payloads),
            enqueue_failures=tuple(self._enqueue_failures),
        )

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._drain_requested and not self._stop_requested:
                    self._condition.wait()
                if self._stop_requested:
                    return
                done = self._drain_done
            try:
                result = self._attempt_one()
            except Exception as exc:
                result = self._snapshot_drain(
                    "blocked",
                    f"worker_error:{str(exc)[:256]}",
                )
            with self._condition:
                self._drain_result = result
                self._drain_requested = False
                self._drain_done = None
                if done is not None:
                    done.set()

    def _attempt_one(self) -> DrainResult:
        queued = self._memory.list_curation_jobs(max_attempts=MAX_ATTEMPTS, limit=1)
        if not queued.succeeded:
            return self._snapshot_drain("blocked", queued.message or "store_unavailable")
        if not queued.value:
            return self._snapshot_drain("no_work", None)
        candidate = queued.value[0]
        policy_result = self._memory.read_policy()
        policy = policy_result.value
        if policy is None or not policy.automatic_curation_enabled:
            return self._snapshot_drain("blocked", "policy_disabled")
        runtime = self._runtime_status()
        llm_ready = bool(runtime.get("ready"))
        if self._processor is None:
            self._memory.mark_curation_job_blocked(
                session_id=candidate.session_id,
                reason="processor_unavailable",
            )
            return self._snapshot_drain("blocked", "processor_unavailable")
        if not llm_ready:
            self._memory.mark_curation_job_blocked(
                session_id=candidate.session_id,
                reason="llm_unavailable",
            )
            return self._snapshot_drain("blocked", "llm_unavailable")
        acquired = self._coordinator.try_acquire_background(
            session_inactive=not self._session_is_active(),
            policy_enabled=True,
            llm_ready=True,
        )
        if not acquired:
            return self._snapshot_drain("blocked", "interactive_or_session_active")
        try:
            claim = self._memory.claim_curation_job(
                worker_id=self.boot_id,
                boot_id=self.boot_id,
                max_attempts=MAX_ATTEMPTS,
                lease_seconds=LEASE_SECONDS,
            )
            if claim.value is None:
                return self._snapshot_drain("no_work", None)
            job = claim.value
            token = job.claim_token or ""
            self._memory.record_curation_generation_started(
                session_id=job.session_id,
                lease_token=token,
                boot_id=self.boot_id,
                runtime_name=_text(runtime.get("runtime_name")),
                model_id=_text(runtime.get("model_id")),
                serve_profile_id=_text(runtime.get("serve_profile_id")),
                accelerator=_text(runtime.get("accelerator")),
            )
            started = time.monotonic()
            evidence_result = self._load_evidence(job)
            if isinstance(evidence_result, str):
                self._memory.fail_curation_job(
                    session_id=job.session_id,
                    lease_token=token,
                    boot_id=self.boot_id,
                    reason=evidence_result,
                    error=evidence_result,
                    retryable=False,
                )
                return self._snapshot_drain("completed", None, job.job_id)
            try:
                processor_result = self._processor(evidence_result)
            except Exception as exc:
                processor_result = CurationProcessorResult(
                    success=False,
                    durable=False,
                    reason_code="processor_exception",
                    error_detail=str(exc)[:2048],
                    retryable=True,
                )
            duration_ms = (time.monotonic() - started) * 1000.0
            if (
                not isinstance(processor_result, CurationProcessorResult)
                or (processor_result.success and not processor_result.durable)
            ):
                processor_result = CurationProcessorResult(
                    success=False,
                    durable=False,
                    reason_code="malformed_processor_result",
                    error_detail="processor did not return a durable typed success",
                    retryable=True,
                )
            if processor_result.success:
                self._memory.complete_curation_job(
                    session_id=job.session_id,
                    lease_token=token,
                    boot_id=self.boot_id,
                    generation_duration_ms=duration_ms,
                    reason=processor_result.reason_code,
                    candidates_proposed=processor_result.candidates_proposed,
                    candidates_rejected=processor_result.candidates_rejected,
                    active_records_created=processor_result.active_records_created,
                    pending_review_created=processor_result.pending_review_created,
                    records_reinforced=processor_result.records_reinforced,
                    records_superseded_or_disputed=(
                        processor_result.records_superseded_or_disputed
                    ),
                    duplicate_noops=processor_result.duplicate_noops,
                    failure_count=processor_result.failure_count,
                )
            else:
                self._memory.fail_curation_job(
                    session_id=job.session_id,
                    lease_token=token,
                    boot_id=self.boot_id,
                    reason=processor_result.reason_code,
                    error=(processor_result.error_detail or processor_result.reason_code)[:2048],
                    retryable=processor_result.retryable,
                )
            return self._snapshot_drain("completed", None, job.job_id)
        finally:
            self._coordinator.release_background()

    def _load_evidence(self, job: CurationJob) -> PersistedSessionEvidence | str:
        path = Path(job.session_artifact_path)
        try:
            artifact = SessionArtifact.from_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return "source_artifact_missing"
        except Exception:
            return "source_artifact_corrupt"
        if artifact.session_id != job.session_id:
            return "source_session_mismatch"
        if artifact.ended_at is None:
            return "source_session_not_closed"
        if (
            not artifact.memory_curation_candidate
            or artifact.memory_curation_authorized_at is None
        ):
            return "source_not_authorized"
        if len(artifact.turn_ids) > MAX_TURNS_PER_JOB:
            return "source_turn_limit_exceeded"
        turns: list[TurnArtifact] = []
        for turn_id in artifact.turn_ids:
            try:
                turn = read_turn_artifact(
                    artifact.session_id,
                    turn_id,
                    self._turns_root,
                )
            except Exception:
                return "source_turn_corrupt"
            if turn is None:
                return "source_turn_missing"
            turns.append(turn)
        return PersistedSessionEvidence(
            session=artifact,
            turns=tuple(turns),
            artifact_path=path,
        )

    def _snapshot_drain(
        self,
        outcome: str,
        blocked_reason: str | None,
        job_id: str | None = None,
    ) -> DrainResult:
        jobs = self._memory.list_curation_jobs(max_attempts=MAX_ATTEMPTS, limit=MAX_STATUS_JOBS)
        remaining = len(jobs.value or ())
        coordinator = self._coordinator.snapshot()
        return DrainResult(
            outcome=outcome,
            job_id=job_id,
            remaining_queued=remaining,
            running=bool(coordinator["background_active"]),
            blocked_reason=blocked_reason,
        )


def _text(value: str | bool | None) -> str | None:
    return value if isinstance(value, str) else None
