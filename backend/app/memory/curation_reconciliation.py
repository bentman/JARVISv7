"""Deterministic review-only reconciliation for extracted memory candidates."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path

from backend.app.memory.curation import (
    EvidenceInput,
    GovernedEvidenceAuthority,
    GovernedFactInput,
    LifecycleState,
    OperationStatus,
)
from backend.app.memory.curation_contract import (
    GovernedClaimIdentity,
    GovernedMemoryKind,
    ModelMemoryProposal,
    ProvisionalMemoryCandidate,
    VerifiedEvidenceRef,
)
from backend.app.memory.semantic import SemanticMemory

MAX_OWNED_VALUES = 512
MAX_OWNED_VALUE_CHARS = 256

_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\b(?:sk|pk)_(?:live|test)_[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"\b(?:api[_ -]?key|password|passwd|token|secret|credential|private[_ -]?key)"
        r"\s*(?:is|=|:)\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
)
_QUOTED_OR_EXTERNAL_PATTERNS = (
    re.compile("^\\s*[\"'\\u201c\\u2018]"),
    re.compile(
        r"\b(?:quote|quoted|the (?:assistant|system|tool) (?:said|says)|"
        r"tool output|retrieved (?:text|memory|context)|according to)\b",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True, slots=True)
class ReconciliationCounts:
    pending_review_created: int = 0
    duplicate_noops: int = 0
    rejected: int = 0


class ReviewOnlyCurationPolicy:
    def __init__(
        self,
        semantic_memory: SemanticMemory,
        *,
        application_owned_values: Iterable[str] = (),
        application_owned_values_provider: Callable[[], Iterable[str]] | None = None,
    ) -> None:
        self._memory = semantic_memory
        self._owned_values = _normalize_owned_values(application_owned_values)
        self._owned_values_provider = application_owned_values_provider

    def reconcile(
        self,
        *,
        proposal: ModelMemoryProposal,
        candidate: ProvisionalMemoryCandidate,
        observed_at: str,
        additional_owned_values: Iterable[str] = (),
    ) -> ReconciliationCounts:
        current_values = (
            self._owned_values_provider()
            if self._owned_values_provider is not None
            else ()
        )
        owned_values = (
            self._owned_values
            | _normalize_owned_values(current_values)
            | _normalize_owned_values(additional_owned_values)
        )
        inspected = (
            proposal.text,
            *(ref.excerpt for ref in candidate.evidence_refs),
        )
        if any(_contains_secret(value) for value in inspected):
            return ReconciliationCounts(rejected=1)
        if any(_is_quoted_or_external(value) for value in inspected):
            return ReconciliationCounts(rejected=1)
        if _contains_owned_value(inspected, owned_values):
            return ReconciliationCounts(rejected=1)

        evidence = _evidence_inputs(candidate.evidence_refs, observed_at)
        fact = GovernedFactInput(
            text=candidate.text,
            identity=GovernedClaimIdentity(
                kind=GovernedMemoryKind.UNCLASSIFIED,
                claim_key=candidate.claim_key,
            ),
            value_text=None,
            evidence_authority=GovernedEvidenceAuthority.DIRECT_USER_STATEMENT,
            state=LifecycleState.PENDING_REVIEW,
            confidence=candidate.confidence,
            importance=candidate.importance,
            evidence=evidence,
            metadata={
                "curation_contract": "review_only_v1",
                "candidate_id": _candidate_id(candidate),
            },
        )
        result = self._memory.create_governed_fact(fact)
        if result.status is OperationStatus.SUCCESS:
            return ReconciliationCounts(pending_review_created=1)
        if result.status is OperationStatus.NO_CHANGE:
            return ReconciliationCounts(duplicate_noops=1)
        if result.status in {
            OperationStatus.CONFLICT,
            OperationStatus.INVALID,
            OperationStatus.REVIEW_REQUIRED,
        }:
            return ReconciliationCounts(rejected=1)
        raise RuntimeError(f"review-only persistence unavailable:{result.status.value}")


def collect_application_owned_values(*authorities: object) -> frozenset[str]:
    values: list[str] = []
    for authority in authorities:
        _collect_scalars(authority, values)
        if len(values) >= MAX_OWNED_VALUES:
            break
    return _normalize_owned_values(values)


def _collect_scalars(value: object, output: list[str]) -> None:
    if len(output) >= MAX_OWNED_VALUES or value is None or isinstance(value, bool):
        return
    if isinstance(value, (str, int, float, Path)):
        text = str(value)
        if text:
            output.append(text)
        return
    if is_dataclass(value) and not isinstance(value, type):
        _collect_scalars(asdict(value), output)
        return
    if isinstance(value, Mapping):
        for item in value.values():
            _collect_scalars(item, output)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _collect_scalars(item, output)


def _normalize_owned_values(values: Iterable[str]) -> frozenset[str]:
    normalized: set[str] = set()
    for value in values:
        text = " ".join(str(value).strip().casefold().split())
        if 4 <= len(text) <= MAX_OWNED_VALUE_CHARS:
            normalized.add(text)
        if len(normalized) >= MAX_OWNED_VALUES:
            break
    return frozenset(normalized)


def _contains_secret(value: str) -> bool:
    return any(pattern.search(value) is not None for pattern in _SECRET_PATTERNS)


def _is_quoted_or_external(value: str) -> bool:
    return any(pattern.search(value) is not None for pattern in _QUOTED_OR_EXTERNAL_PATTERNS)


def _contains_owned_value(values: Iterable[str], owned_values: frozenset[str]) -> bool:
    normalized = tuple(" ".join(value.casefold().split()) for value in values if value)
    return any(owned in value for owned in owned_values for value in normalized)


def _candidate_id(candidate: ProvisionalMemoryCandidate) -> str:
    canonical = "|".join(
        (
            candidate.claim_key,
            GovernedMemoryKind.UNCLASSIFIED.value,
            *sorted(
                f"{ref.session_id}:{ref.source_turn_id}:{ref.source_field.value}:"
                f"{hashlib.sha256(ref.excerpt.encode('utf-8')).hexdigest()}"
                for ref in candidate.evidence_refs
            ),
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _evidence_inputs(
    refs: tuple[VerifiedEvidenceRef, ...],
    observed_at: str,
) -> tuple[EvidenceInput, ...]:
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for ref in refs:
        origin = (ref.session_id, ref.source_turn_id, ref.source_field.value)
        grouped.setdefault(origin, []).append(
            hashlib.sha256(ref.excerpt.encode("utf-8")).hexdigest()
        )
    return tuple(
        EvidenceInput(
            authority=GovernedEvidenceAuthority.DIRECT_USER_STATEMENT,
            observed_at=observed_at,
            source_session_id=session_id,
            source_turn_id=turn_id,
            source_field=source_field,
            metadata={"excerpt_sha256": sorted(excerpt_hashes)},
        )
        for (session_id, turn_id, source_field), excerpt_hashes in sorted(grouped.items())
    )
