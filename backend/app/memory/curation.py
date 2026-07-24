"""Typed contracts for deterministic semantic-memory lifecycle operations."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar

from backend.app.memory.curation_contract import (
    MAX_SESSION_ID_CHARS,
    MAX_TEXT_CHARS,
    MAX_TURN_ID_CHARS,
    EvidenceField,
    GovernedClaimIdentity,
    GovernedMemoryKind,
    validate_claim_key,
)

MAX_VALUE_CHARS = 160
MAX_METADATA_CHARS = 16_384
MAX_SOURCE_FIELD_CHARS = 64
MAX_ACTION_ID_CHARS = 128
MAX_ACTION_SURFACE_CHARS = 64
MAX_REASON_CHARS = 256
MAX_ARTIFACT_REF_CHARS = 1_024
MAX_WORKER_ID_CHARS = 128
MAX_ERROR_CHARS = 2_048
MAX_LIST_LIMIT = 100
MAX_VECTOR_DIM = 4_096


class LifecycleState(StrEnum):
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    DISPUTED = "disputed"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    FORGOTTEN = "forgotten"


TRANSITION_MATRIX: dict[LifecycleState, frozenset[LifecycleState]] = {
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
}


class GovernedEvidenceAuthority(StrEnum):
    DIRECT_USER_STATEMENT = "direct_user_statement"
    DIRECT_USER_ACTION = "direct_user_action"
    ASSISTANT_INFERENCE = "assistant_inference"
    SYNTHESIZED_SUMMARY = "synthesized_summary"
    IMPORTED_RECORD = "imported_record"
    LEGACY_UNKNOWN = "legacy_unknown"


class CurationJobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OperationStatus(StrEnum):
    SUCCESS = "success"
    NO_CHANGE = "no_change"
    REVIEW_REQUIRED = "review_required"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    INVALID = "invalid"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"


class CurationValidationError(ValueError):
    """An application-owned lifecycle input failed validation."""


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class StoreResult(Generic[T]):
    status: OperationStatus
    value: T | None = None
    message: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status in {
            OperationStatus.SUCCESS,
            OperationStatus.NO_CHANGE,
            OperationStatus.REVIEW_REQUIRED,
        }


def require_bounded_string(
    value: str,
    label: str,
    maximum: int,
    *,
    allow_blank: bool = False,
) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise CurationValidationError(f"{label} must be a string of at most {maximum} chars")
    if not allow_blank and not value.strip():
        raise CurationValidationError(f"{label} must not be blank")
    return value


def require_optional_bounded_string(
    value: str | None,
    label: str,
    maximum: int,
    *,
    allow_blank: bool = False,
) -> str | None:
    if value is None:
        return None
    return require_bounded_string(value, label, maximum, allow_blank=allow_blank)


def require_timestamp(value: str, label: str) -> str:
    require_bounded_string(value, label, 64)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CurationValidationError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CurationValidationError(f"{label} must include a timezone offset")
    return value


def require_optional_timestamp(value: str | None, label: str) -> str | None:
    return None if value is None else require_timestamp(value, label)


def require_score(value: float | None, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CurationValidationError(f"{label} must be numeric")
    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise CurationValidationError(f"{label} must be finite and between 0 and 1")
    return score


def require_metadata(value: dict[str, Any], label: str = "metadata") -> str:
    if not isinstance(value, dict):
        raise CurationValidationError(f"{label} must be an object")
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise CurationValidationError(f"{label} must be JSON serializable") from exc
    if len(encoded) > MAX_METADATA_CHARS:
        raise CurationValidationError(f"{label} must encode to at most {MAX_METADATA_CHARS} chars")
    return encoded


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    authority: GovernedEvidenceAuthority
    observed_at: str
    source_session_id: str | None = None
    source_turn_id: str | None = None
    source_field: str | None = None
    action_id: str | None = None
    action_surface: str | None = None
    action_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.authority, GovernedEvidenceAuthority):
            raise CurationValidationError("evidence authority must be application-owned")
        require_timestamp(self.observed_at, "observed_at")
        require_metadata(self.metadata, "evidence metadata")
        is_action = self.action_id is not None
        if is_action:
            if self.authority is not GovernedEvidenceAuthority.DIRECT_USER_ACTION:
                raise CurationValidationError(
                    "action evidence must use direct_user_action authority"
                )
            if any(
                value is not None
                for value in (
                    self.source_session_id,
                    self.source_turn_id,
                    self.source_field,
                )
            ):
                raise CurationValidationError("action evidence cannot fabricate turn provenance")
            require_bounded_string(self.action_id or "", "action_id", MAX_ACTION_ID_CHARS)
            require_bounded_string(
                self.action_surface or "",
                "action_surface",
                MAX_ACTION_SURFACE_CHARS,
            )
            require_bounded_string(
                self.action_reason or "",
                "action_reason",
                MAX_REASON_CHARS,
            )
            return

        if any(value is not None for value in (self.action_surface, self.action_reason)):
            raise CurationValidationError("turn evidence cannot contain action fields")
        if self.authority is GovernedEvidenceAuthority.DIRECT_USER_ACTION:
            raise CurationValidationError("direct_user_action authority requires an action origin")
        require_bounded_string(
            self.source_session_id or "",
            "source_session_id",
            MAX_SESSION_ID_CHARS,
        )
        require_bounded_string(
            self.source_turn_id or "",
            "source_turn_id",
            MAX_TURN_ID_CHARS,
        )
        require_bounded_string(
            self.source_field or "",
            "source_field",
            MAX_SOURCE_FIELD_CHARS,
        )
        try:
            EvidenceField(self.source_field or "")
        except ValueError as exc:
            raise CurationValidationError(
                "source_field must be transcript or response_text"
            ) from exc

    @property
    def origin_key(self) -> tuple[str, ...]:
        if self.action_id is not None:
            return ("action", self.action_id)
        return (
            "turn",
            self.source_session_id or "",
            self.source_turn_id or "",
            self.source_field or "",
        )


@dataclass(frozen=True, slots=True)
class GovernedFactInput:
    text: str
    identity: GovernedClaimIdentity
    value_text: str | None
    evidence_authority: GovernedEvidenceAuthority
    state: LifecycleState
    confidence: float | None
    importance: float | None
    evidence: tuple[EvidenceInput, ...]
    vector: tuple[float, ...] | None = None
    vectorizer_id: str | None = None
    expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_bounded_string(self.text, "text", MAX_TEXT_CHARS)
        if not isinstance(self.identity.kind, GovernedMemoryKind):
            raise CurationValidationError("kind must be application-owned")
        if not isinstance(self.evidence_authority, GovernedEvidenceAuthority):
            raise CurationValidationError("fact evidence authority must be application-owned")
        try:
            validate_claim_key(self.identity.claim_key)
        except ValueError as exc:
            raise CurationValidationError(str(exc)) from exc
        require_optional_bounded_string(
            self.value_text,
            "value_text",
            MAX_VALUE_CHARS,
            allow_blank=True,
        )
        if self.state not in {
            LifecycleState.PENDING_REVIEW,
            LifecycleState.ACTIVE,
            LifecycleState.DISPUTED,
        }:
            raise CurationValidationError("new governed facts cannot start terminal")
        require_score(self.confidence, "confidence")
        require_score(self.importance, "importance")
        require_optional_timestamp(self.expires_at, "expires_at")
        require_metadata(self.metadata)
        if not self.evidence:
            raise CurationValidationError("at least one evidence reference is required")
        origins = [item.origin_key for item in self.evidence]
        if len(origins) != len(set(origins)):
            raise CurationValidationError("duplicate evidence origins are not allowed")
        if self.vector is not None:
            if not 1 <= len(self.vector) <= MAX_VECTOR_DIM:
                raise CurationValidationError(f"vector must contain 1..{MAX_VECTOR_DIM} values")
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in self.vector
            ):
                raise CurationValidationError("vector values must be finite numbers")
        require_optional_bounded_string(
            self.vectorizer_id,
            "vectorizer_id",
            128,
        )


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    fact_id: str
    authority: str
    observed_at: str
    created_at: str
    source_session_id: str | None
    source_turn_id: str | None
    source_field: str | None
    action_id: str | None
    action_surface: str | None
    action_reason: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LifecycleEventRecord:
    event_id: str
    fact_id: str
    event_type: str
    prior_state: str | None
    resulting_state: str | None
    related_fact_id: str | None
    reason_code: str
    occurred_at: str
    source_session_id: str | None
    source_turn_id: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GovernedFactRecord:
    fact_id: str
    text: str
    kind: str
    claim_key: str | None
    value_text: str | None
    evidence_authority: str
    state: str
    confidence: float | None
    importance: float | None
    reinforcement_count: int
    created_at: str
    updated_at: str
    last_confirmed_at: str | None
    expires_at: str | None
    superseded_by_fact_id: str | None
    revision: int
    metadata: dict[str, Any]
    vectorizer_id: str
    vector_dim: int
    text_hash: str


@dataclass(frozen=True, slots=True)
class FactDetail:
    fact: GovernedFactRecord
    evidence: tuple[EvidenceRecord, ...]
    events: tuple[LifecycleEventRecord, ...]


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    automatic_curation_enabled: bool
    revision: int
    updated_at: str


@dataclass(frozen=True, slots=True)
class CurationJob:
    session_id: str
    artifact_ref: str
    status: CurationJobStatus
    attempt_count: int
    created_at: str
    started_at: str | None
    updated_at: str
    last_attempt_at: str | None
    last_error: str | None
    last_reason: str | None
    lease_token: str | None
    lease_owner: str | None
    lease_expires_at: str | None


@dataclass(frozen=True, slots=True)
class CorrectionResult:
    original: GovernedFactRecord
    replacement: GovernedFactRecord


def validate_list_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIST_LIMIT:
        raise CurationValidationError(f"limit must be between 1 and {MAX_LIST_LIMIT}")
    return limit


def validate_kind_filter(kind: GovernedMemoryKind | None) -> str | None:
    if kind is None:
        return None
    if not isinstance(kind, GovernedMemoryKind):
        raise CurationValidationError("kind filter must be application-owned")
    return kind.value


def validate_query(query: str | None) -> str | None:
    if query is None:
        return None
    return require_bounded_string(query, "query", MAX_TEXT_CHARS)


def validate_job_identity(session_id: str, artifact_ref: str | None = None) -> None:
    require_bounded_string(session_id, "session_id", MAX_SESSION_ID_CHARS)
    if artifact_ref is not None:
        require_bounded_string(artifact_ref, "artifact_ref", MAX_ARTIFACT_REF_CHARS)


def validate_worker_identity(worker_id: str) -> str:
    return require_bounded_string(worker_id, "worker_id", MAX_WORKER_ID_CHARS)


def validate_reason(reason: str, label: str = "reason") -> str:
    return require_bounded_string(reason, label, MAX_REASON_CHARS)


def validate_error(error: str | None) -> str | None:
    return require_optional_bounded_string(
        error,
        "error",
        MAX_ERROR_CHARS,
        allow_blank=True,
    )
