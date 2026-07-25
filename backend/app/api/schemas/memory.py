from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictMemoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemoryPolicyResponse(StrictMemoryModel):
    automatic_curation_enabled: bool
    revision: int
    updated_at: str


class MemoryPolicyUpdateRequest(StrictMemoryModel):
    automatic_curation_enabled: bool
    expected_revision: int = Field(ge=1)


class MemoryRecordResponse(StrictMemoryModel):
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


class MemoryRecordPageResponse(StrictMemoryModel):
    records: list[MemoryRecordResponse]
    offset: int
    limit: int
    returned_count: int
    bounded_match_count: int
    has_more: bool
    next_offset: int | None
    results_truncated: bool


class MemoryEvidenceResponse(StrictMemoryModel):
    evidence_id: str
    authority: str
    observed_at: str
    created_at: str
    source_session_id: str | None
    source_turn_id: str | None
    source_field: str | None


class MemoryEventResponse(StrictMemoryModel):
    event_id: str
    event_type: str
    prior_state: str | None
    resulting_state: str | None
    related_fact_id: str | None
    reason_code: str
    occurred_at: str
    source_session_id: str | None
    source_turn_id: str | None


class MemoryDetailResponse(StrictMemoryModel):
    record: MemoryRecordResponse
    evidence: list[MemoryEvidenceResponse]
    events: list[MemoryEventResponse]
    evidence_total: int
    evidence_returned: int
    evidence_limit: int
    evidence_truncated: bool
    events_total: int
    events_returned: int
    events_limit: int
    events_truncated: bool
    forgetting_scope: str


class MemoryLifecycleRequest(StrictMemoryModel):
    expected_revision: int = Field(ge=1)
    reason: str | None = Field(default=None, min_length=1, max_length=256)


class MemoryCorrectionRequest(StrictMemoryModel):
    expected_revision: int = Field(ge=1)
    replacement_text: str = Field(min_length=1, max_length=240)
    replacement_value: str | None = Field(default=None, max_length=160)
    reason: str | None = Field(default=None, min_length=1, max_length=256)


class MemoryCorrectionResponse(StrictMemoryModel):
    original: MemoryRecordResponse
    replacement: MemoryRecordResponse
    relation: str


class CurationResultResponse(StrictMemoryModel):
    reason_code: str = Field(min_length=1, max_length=128)
    candidates_proposed: int = Field(ge=0, le=3)
    candidates_rejected: int = Field(ge=0, le=3)
    active_records_created: int = Field(ge=0, le=3)
    pending_review_created: int = Field(ge=0, le=3)
    records_reinforced: int = Field(ge=0, le=3)
    records_superseded_or_disputed: int = Field(ge=0, le=3)
    duplicate_noops: int = Field(ge=0, le=3)
    failure_count: int = Field(ge=0, le=3)


class CurationJobResponse(StrictMemoryModel):
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
    result: CurationResultResponse | None


class MemoryCurationStatusResponse(StrictMemoryModel):
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
    last_result: CurationResultResponse | None
    last_updated_at: str | None
    retry_blocked: bool
    jobs_returned: int
    jobs_truncated: bool
    recent_jobs: list[CurationJobResponse]
