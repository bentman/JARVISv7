from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from backend.app.memory.curation import (
    CurationJob,
    EvidenceInput,
    GovernedEvidenceAuthority,
    GovernedFactInput,
    GovernedFactRecord,
    LifecycleState,
    MemoryPolicy,
    OperationStatus,
    StoreResult,
)
from backend.app.memory.curation_contract import (
    GovernedClaimIdentity,
    GovernedMemoryKind,
)
from backend.app.memory.semantic import SemanticMemory
from backend.app.services.memory_curation_service import (
    MAX_ATTEMPTS,
    MemoryCurationService,
)

DEFAULT_LIST_STATES = (
    LifecycleState.ACTIVE,
    LifecycleState.PENDING_REVIEW,
    LifecycleState.DISPUTED,
)
MAX_PAGE_LIMIT = 50
MAX_PAGE_OFFSET = 250
MAX_DETAIL_ITEMS = 50
DEFAULT_DETAIL_ITEMS = 20
MAX_RECENT_JOBS = 20
FORGETTING_SCOPE = (
    "Forgetting marks this semantic memory record as forgotten. Source turn and "
    "session artifacts are separate evidence and are not erased by this operation."
)


@dataclass(frozen=True, slots=True)
class MemoryServiceError(Exception):
    status_code: int
    error: str
    message: str
    current_revision: int | None = None
    current_state: str | None = None

    def detail(self) -> dict[str, str | int | None]:
        detail: dict[str, str | int | None] = {
            "error": self.error,
            "message": self.message[:256],
        }
        if self.status_code == 409:
            detail["current_revision"] = self.current_revision
            detail["current_state"] = self.current_state
        return detail


@dataclass(frozen=True, slots=True)
class MemoryPolicyView:
    automatic_curation_enabled: bool
    revision: int
    updated_at: str


@dataclass(frozen=True, slots=True)
class MemoryRecordView:
    fact_id: str
    revision: int
    text: str
    kind: str
    claim_key: str | None
    value: str | None
    evidence_authority: str
    lifecycle_state: str
    confidence: float | None
    importance: float | None
    reinforcement_count: int
    created_at: str
    updated_at: str
    confirmed_at: str | None
    expires_at: str | None
    superseded_by_fact_id: str | None
    eligible_for_normal_retrieval: bool


@dataclass(frozen=True, slots=True)
class MemoryRecordPage:
    records: tuple[MemoryRecordView, ...]
    offset: int
    limit: int
    returned_count: int
    bounded_match_count: int
    has_more: bool
    next_offset: int | None
    results_truncated: bool


@dataclass(frozen=True, slots=True)
class MemoryEvidenceView:
    evidence_id: str
    authority: str
    observed_at: str
    created_at: str
    source_session_id: str | None
    source_turn_id: str | None
    source_field: str | None


@dataclass(frozen=True, slots=True)
class MemoryEventView:
    event_id: str
    event_type: str
    prior_state: str | None
    resulting_state: str | None
    related_fact_id: str | None
    reason_code: str
    occurred_at: str
    source_session_id: str | None
    source_turn_id: str | None


@dataclass(frozen=True, slots=True)
class MemoryDetailView:
    record: MemoryRecordView
    evidence: tuple[MemoryEvidenceView, ...]
    events: tuple[MemoryEventView, ...]
    evidence_total: int
    evidence_returned: int
    evidence_limit: int
    evidence_truncated: bool
    events_total: int
    events_returned: int
    events_limit: int
    events_truncated: bool
    forgetting_scope: str = FORGETTING_SCOPE


@dataclass(frozen=True, slots=True)
class MemoryCorrectionView:
    original: MemoryRecordView
    replacement: MemoryRecordView
    relation: str = "replacement_supersedes_original"


@dataclass(frozen=True, slots=True)
class CurationJobView:
    job_id: str
    session_id: str
    status: str
    attempt_count: int
    max_attempts: int
    enqueued_at: str
    updated_at: str
    started_at: str | None
    completed_at: str | None
    last_reason: str | None
    blocked_reason: str | None
    retry_condition: str


@dataclass(frozen=True, slots=True)
class MemoryCurationStatusView:
    service_available: bool
    processor_available: bool
    automatic_curation_enabled: bool
    worker_running: bool
    drain_active: bool
    degraded: bool
    degraded_reason: str | None
    pending_count: int
    processing_count: int
    failed_count: int
    completed_count: int
    current_job_id: str | None
    current_session_id: str | None
    last_result_reason: str | None
    last_updated_at: str | None
    retry_blocked: bool
    jobs_returned: int
    jobs_truncated: bool
    recent_jobs: tuple[CurationJobView, ...]


class MemoryService:
    """Bounded application mapping over governed memory and curation state."""

    def __init__(
        self,
        *,
        semantic_memory: SemanticMemory,
        curation_service: MemoryCurationService | None,
    ) -> None:
        self._memory = semantic_memory
        self._curation = curation_service

    def read_policy(self) -> MemoryPolicyView:
        policy = self._value(self._memory.read_policy(), operation="read policy")
        return self._policy_view(policy)

    def update_policy(
        self,
        *,
        automatic_curation_enabled: bool,
        expected_revision: int,
    ) -> MemoryPolicyView:
        result = self._memory.update_policy(
            automatic_curation_enabled=automatic_curation_enabled,
            expected_revision=expected_revision,
        )
        policy = self._value(result, operation="update policy", policy_conflict=True)
        return self._policy_view(policy)

    def list_records(
        self,
        *,
        state: LifecycleState | None,
        kind: GovernedMemoryKind | None,
        query: str | None,
        offset: int,
        limit: int,
    ) -> MemoryRecordPage:
        if not 0 <= offset <= MAX_PAGE_OFFSET:
            raise MemoryServiceError(422, "invalid_input", "offset is outside the bounded window")
        if not 1 <= limit <= MAX_PAGE_LIMIT:
            raise MemoryServiceError(422, "invalid_input", "limit is outside the bounded range")

        states = (state,) if state is not None else DEFAULT_LIST_STATES
        records: list[GovernedFactRecord] = []
        results_truncated = False
        for selected_state in states:
            result = self._memory.list_facts(
                state=selected_state,
                kind=kind,
                query=query,
                limit=100,
            )
            selected = self._value(result, operation="list memory")
            records.extend(selected)
            results_truncated = results_truncated or len(selected) == 100

        deduplicated = {record.fact_id: record for record in records}
        ordered = sorted(deduplicated.values(), key=lambda item: item.fact_id)
        ordered.sort(key=lambda item: item.created_at, reverse=True)
        end = offset + limit
        page = ordered[offset:end]
        has_more = end < len(ordered)
        return MemoryRecordPage(
            records=tuple(self._record_view(record) for record in page),
            offset=offset,
            limit=limit,
            returned_count=len(page),
            bounded_match_count=len(ordered),
            has_more=has_more,
            next_offset=end if has_more else None,
            results_truncated=results_truncated,
        )

    def read_record(
        self,
        fact_id: str,
        *,
        evidence_limit: int = DEFAULT_DETAIL_ITEMS,
        events_limit: int = DEFAULT_DETAIL_ITEMS,
    ) -> MemoryDetailView:
        self._validate_detail_limit(evidence_limit, "evidence_limit")
        self._validate_detail_limit(events_limit, "events_limit")
        detail = self._value(
            self._memory.read_fact(fact_id),
            operation="read memory",
            fact_id=fact_id,
        )
        evidence = detail.evidence[-evidence_limit:]
        events = detail.events[-events_limit:]
        return MemoryDetailView(
            record=self._record_view(detail.fact),
            evidence=tuple(
                MemoryEvidenceView(
                    evidence_id=item.evidence_id,
                    authority=item.authority,
                    observed_at=item.observed_at,
                    created_at=item.created_at,
                    source_session_id=item.source_session_id,
                    source_turn_id=item.source_turn_id,
                    source_field=item.source_field,
                )
                for item in evidence
            ),
            events=tuple(
                MemoryEventView(
                    event_id=item.event_id,
                    event_type=item.event_type,
                    prior_state=item.prior_state,
                    resulting_state=item.resulting_state,
                    related_fact_id=item.related_fact_id,
                    reason_code=item.reason_code,
                    occurred_at=item.occurred_at,
                    source_session_id=item.source_session_id,
                    source_turn_id=item.source_turn_id,
                )
                for item in events
            ),
            evidence_total=len(detail.evidence),
            evidence_returned=len(evidence),
            evidence_limit=evidence_limit,
            evidence_truncated=len(detail.evidence) > len(evidence),
            events_total=len(detail.events),
            events_returned=len(events),
            events_limit=events_limit,
            events_truncated=len(detail.events) > len(events),
        )

    def confirm(
        self, fact_id: str, *, expected_revision: int, reason: str | None
    ) -> MemoryRecordView:
        evidence, selected_reason = self._user_action(reason, "user_confirmed")
        result = self._memory.confirm_fact(
            fact_id,
            expected_revision=expected_revision,
            evidence=evidence,
            reason=selected_reason,
        )
        return self._record_view(self._value(result, operation="confirm memory", fact_id=fact_id))

    def dispute(
        self, fact_id: str, *, expected_revision: int, reason: str | None
    ) -> MemoryRecordView:
        evidence, selected_reason = self._user_action(reason, "user_disputed")
        result = self._memory.dispute_fact(
            fact_id,
            expected_revision=expected_revision,
            evidence=evidence,
            reason=selected_reason,
        )
        return self._record_view(self._value(result, operation="dispute memory", fact_id=fact_id))

    def forget(
        self, fact_id: str, *, expected_revision: int, reason: str | None
    ) -> MemoryDetailView:
        evidence, selected_reason = self._user_action(reason, "user_forgotten")
        result = self._memory.forget_fact(
            fact_id,
            expected_revision=expected_revision,
            evidence=evidence,
            reason=selected_reason,
        )
        self._value(result, operation="forget memory", fact_id=fact_id)
        return self.read_record(fact_id)

    def correct(
        self,
        fact_id: str,
        *,
        expected_revision: int,
        replacement_text: str,
        replacement_value: str | None,
        reason: str | None,
    ) -> MemoryCorrectionView:
        current = self._value(
            self._memory.read_fact(fact_id),
            operation="read memory for correction",
            fact_id=fact_id,
        ).fact
        evidence, selected_reason = self._user_action(reason, "explicit_user_correction")
        try:
            replacement = GovernedFactInput(
                text=replacement_text,
                identity=GovernedClaimIdentity(
                    kind=GovernedMemoryKind(current.kind),
                    claim_key=current.claim_key or "",
                ),
                value_text=replacement_value,
                evidence_authority=GovernedEvidenceAuthority.DIRECT_USER_ACTION,
                state=LifecycleState.ACTIVE,
                confidence=current.confidence,
                importance=current.importance,
                evidence=(evidence,),
                expires_at=current.expires_at,
            )
        except (TypeError, ValueError) as exc:
            raise MemoryServiceError(
                422,
                "invalid_input",
                "replacement does not satisfy the governed claim contract",
            ) from exc
        result = self._memory.correct_fact(
            fact_id,
            expected_revision=expected_revision,
            replacement=replacement,
            evidence=evidence,
            reason=selected_reason,
        )
        corrected = self._value(result, operation="correct memory", fact_id=fact_id)
        return MemoryCorrectionView(
            original=self._record_view(corrected.original),
            replacement=self._record_view(corrected.replacement),
        )

    def curation_status(self) -> MemoryCurationStatusView:
        if self._curation is None:
            raise MemoryServiceError(503, "unavailable", "memory curation is unavailable")
        policy = self._value(self._memory.read_policy(), operation="read curation policy")
        jobs = self._value(
            self._memory.list_curation_jobs(
                max_attempts=MAX_ATTEMPTS + 1,
                limit=100,
                include_terminal=True,
            ),
            operation="read curation jobs",
        )
        try:
            runtime = self._curation.status()
        except Exception as exc:
            raise MemoryServiceError(
                500,
                "internal_error",
                "memory curation status could not be produced",
            ) from exc

        counts = Counter(job.status.value for job in jobs)
        recent = sorted(jobs, key=lambda item: (item.updated_at, item.job_id), reverse=True)
        current = next(
            (job for job in recent if job.status.value == "processing"),
            None,
        )
        latest_result = next((job for job in recent if job.last_reason is not None), None)
        degraded_reasons: list[str] = []
        if not runtime.processor_available:
            degraded_reasons.append("processor_unavailable")
        if runtime.enqueue_failures:
            degraded_reasons.append("enqueue_failures")
        retry_blocked = not runtime.processor_available or any(
            job.blocked_reason is not None
            or (job.status.value == "failed" and job.attempt_count >= job.max_attempts)
            for job in jobs
        )
        return MemoryCurationStatusView(
            service_available=True,
            processor_available=runtime.processor_available,
            automatic_curation_enabled=policy.automatic_curation_enabled,
            worker_running=runtime.worker_running,
            drain_active=runtime.drain_active,
            degraded=bool(degraded_reasons),
            degraded_reason=",".join(degraded_reasons) or None,
            pending_count=counts["pending"] + counts["retry_wait"],
            processing_count=counts["processing"],
            failed_count=counts["failed"],
            completed_count=counts["succeeded"],
            current_job_id=current.job_id if current else None,
            current_session_id=current.session_id if current else None,
            last_result_reason=latest_result.last_reason if latest_result else None,
            last_updated_at=latest_result.updated_at if latest_result else None,
            retry_blocked=retry_blocked,
            jobs_returned=len(jobs),
            jobs_truncated=len(jobs) == 100,
            recent_jobs=tuple(self._curation_job_view(job) for job in recent[:MAX_RECENT_JOBS]),
        )

    def _value(
        self,
        result: StoreResult,
        *,
        operation: str,
        fact_id: str | None = None,
        policy_conflict: bool = False,
    ):
        if (
            result.status
            in {
                OperationStatus.SUCCESS,
                OperationStatus.NO_CHANGE,
                OperationStatus.REVIEW_REQUIRED,
            }
            and result.value is not None
        ):
            return result.value
        if result.status is OperationStatus.NOT_FOUND:
            raise MemoryServiceError(404, "not_found", f"{operation} target was not found")
        if result.status is OperationStatus.CONFLICT:
            revision, state = self._conflict_snapshot(
                fact_id=fact_id,
                policy=policy_conflict,
            )
            raise MemoryServiceError(
                409,
                "conflict",
                f"{operation} conflicted with the current governed state",
                current_revision=revision,
                current_state=state,
            )
        if result.status is OperationStatus.INVALID:
            raise MemoryServiceError(
                422,
                "invalid_input",
                (result.message or f"{operation} input is invalid")[:256],
            )
        if result.status in {OperationStatus.BUSY, OperationStatus.UNAVAILABLE}:
            raise MemoryServiceError(503, "unavailable", f"{operation} is unavailable")
        raise MemoryServiceError(500, "internal_error", f"{operation} failed")

    def _conflict_snapshot(
        self,
        *,
        fact_id: str | None,
        policy: bool,
    ) -> tuple[int | None, str | None]:
        if policy:
            current = self._memory.read_policy()
            if current.succeeded and current.value is not None:
                state = "enabled" if current.value.automatic_curation_enabled else "disabled"
                return current.value.revision, state
        if fact_id is not None:
            current_fact = self._memory.read_fact(fact_id)
            if current_fact.succeeded and current_fact.value is not None:
                return current_fact.value.fact.revision, current_fact.value.fact.state
        return None, None

    @staticmethod
    def _policy_view(policy: MemoryPolicy) -> MemoryPolicyView:
        return MemoryPolicyView(
            automatic_curation_enabled=policy.automatic_curation_enabled,
            revision=policy.revision,
            updated_at=policy.updated_at,
        )

    @staticmethod
    def _record_view(record: GovernedFactRecord) -> MemoryRecordView:
        return MemoryRecordView(
            fact_id=record.fact_id,
            revision=record.revision,
            text=record.text,
            kind=record.kind,
            claim_key=record.claim_key,
            value=record.value_text,
            evidence_authority=record.evidence_authority,
            lifecycle_state=record.state,
            confidence=record.confidence,
            importance=record.importance,
            reinforcement_count=record.reinforcement_count,
            created_at=record.created_at,
            updated_at=record.updated_at,
            confirmed_at=record.last_confirmed_at,
            expires_at=record.expires_at,
            superseded_by_fact_id=record.superseded_by_fact_id,
            eligible_for_normal_retrieval=MemoryService._eligible_for_retrieval(record),
        )

    @staticmethod
    def _eligible_for_retrieval(record: GovernedFactRecord) -> bool:
        permitted_kinds = {"fact", *(kind.value for kind in GovernedMemoryKind)}
        if (
            record.kind not in permitted_kinds
            or record.state != LifecycleState.ACTIVE.value
            or record.superseded_by_fact_id is not None
        ):
            return False
        if record.expires_at is None:
            return True
        try:
            return datetime.fromisoformat(record.expires_at) > datetime.now(UTC)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _user_action(reason: str | None, default_reason: str) -> tuple[EvidenceInput, str]:
        selected_reason = reason or default_reason
        try:
            evidence = EvidenceInput(
                authority=GovernedEvidenceAuthority.DIRECT_USER_ACTION,
                observed_at=datetime.now(UTC).isoformat(),
                action_id=uuid.uuid4().hex,
                action_surface="memory_api",
                action_reason=selected_reason,
            )
        except ValueError as exc:
            raise MemoryServiceError(422, "invalid_input", "reason is invalid") from exc
        return evidence, selected_reason

    @staticmethod
    def _validate_detail_limit(value: int, label: str) -> None:
        if not 1 <= value <= MAX_DETAIL_ITEMS:
            raise MemoryServiceError(422, "invalid_input", f"{label} is outside the bounded range")

    @staticmethod
    def _curation_job_view(job: CurationJob) -> CurationJobView:
        if job.status.value == "retry_wait" and job.attempt_count < job.max_attempts:
            retry_condition = "automatic_retry_pending"
        elif job.status.value == "failed":
            retry_condition = "no_explicit_retry_operation"
        else:
            retry_condition = "not_applicable"
        return CurationJobView(
            job_id=job.job_id,
            session_id=job.session_id,
            status=job.status.value,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            enqueued_at=job.enqueued_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            last_reason=job.last_reason,
            blocked_reason=job.blocked_reason,
            retry_condition=retry_condition,
        )


__all__ = [
    "DEFAULT_DETAIL_ITEMS",
    "FORGETTING_SCOPE",
    "MAX_DETAIL_ITEMS",
    "MAX_PAGE_LIMIT",
    "MAX_PAGE_OFFSET",
    "MemoryService",
    "MemoryServiceError",
]
