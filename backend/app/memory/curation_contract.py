"""Deterministic boundary for model-proposed semantic-memory candidates.

The model may propose text and evidence locators, but its kind, claim key, and
relation are advisory.  Only application-owned evidence verification and an
explicit application identity decision can produce a governed claim identity.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

MAX_MODEL_OUTPUT_CHARS = 16_384
MAX_CANDIDATES = 3
MAX_TEXT_CHARS = 240
MAX_CLAIM_KEY_CHARS = 80
MAX_VALUE_CHARS = 160
MAX_EVIDENCE_REFS = 3
MAX_TURN_ID_CHARS = 64
MAX_SESSION_ID_CHARS = 128
MAX_EXCERPT_CHARS = 160
PROVISIONAL_MEMORY_KIND = "unclassified"

_CLAIM_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_CANDIDATE_FIELDS = frozenset(
    {
        "text",
        "kind",
        "claim_key",
        "value",
        "relation",
        "evidence_refs",
        "confidence",
        "importance",
    }
)
_EVIDENCE_FIELDS = frozenset({"source_turn_id", "source_field", "excerpt"})


class ProposalContractError(ValueError):
    """A model proposal or its evidence failed the deterministic contract."""


class GovernedMemoryKind(StrEnum):
    """Application-owned durable-memory vocabulary."""

    USER_PREFERENCE = "user_preference"
    PERSONAL_FACT = "personal_fact"
    PROJECT_FACT = "project_fact"
    DECISION = "decision"
    COMMITMENT = "commitment"
    RELATIONSHIP = "relationship"
    SUMMARY = "summary"


class EvidenceField(StrEnum):
    TRANSCRIPT = "transcript"
    RESPONSE_TEXT = "response_text"


class EvidenceAuthority(StrEnum):
    DIRECT_USER_STATEMENT = "direct_user_statement"
    ASSISTANT_INFERENCE = "assistant_inference"


class CandidateDisposition(StrEnum):
    REVIEW_REQUIRED = "review_required"


class AdvisoryRelation(StrEnum):
    ASSERTION = "assertion"
    EXPLICIT_CORRECTION = "explicit_correction"


@dataclass(frozen=True, slots=True)
class ModelEvidenceRef:
    source_turn_id: str
    source_field: EvidenceField
    excerpt: str


@dataclass(frozen=True, slots=True)
class ModelMemoryProposal:
    text: str
    advisory_kind: GovernedMemoryKind
    advisory_claim_key: str
    value: str | None
    advisory_relation: AdvisoryRelation
    evidence_refs: tuple[ModelEvidenceRef, ...]
    confidence: float
    importance: float


@dataclass(frozen=True, slots=True)
class PersistedTurnEvidence:
    """Application-owned persisted fields available for evidence verification."""

    session_id: str
    turn_id: str
    transcript: str | None
    response_text: str | None
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class VerifiedEvidenceRef:
    session_id: str
    source_turn_id: str
    source_field: EvidenceField
    excerpt: str
    authority: EvidenceAuthority


@dataclass(frozen=True, slots=True)
class ProvisionalMemoryCandidate:
    """Review-only candidate with identity derived without model semantics."""

    text: str
    kind: str
    claim_key: str
    evidence_refs: tuple[VerifiedEvidenceRef, ...]
    confidence: float
    importance: float
    disposition: CandidateDisposition
    advisory_kind: GovernedMemoryKind
    advisory_claim_key: str
    advisory_relation: AdvisoryRelation
    can_auto_activate: bool = False
    can_auto_reinforce: bool = False
    can_auto_supersede: bool = False


@dataclass(frozen=True, slots=True)
class ApplicationIdentityDecision:
    """Trusted application/user decision; never construct this from model fields."""

    kind: GovernedMemoryKind
    related_claim_key: str | None = None

    def __post_init__(self) -> None:
        if self.related_claim_key is not None:
            validate_claim_key(self.related_claim_key)


@dataclass(frozen=True, slots=True)
class GovernedClaimIdentity:
    kind: GovernedMemoryKind
    claim_key: str


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProposalContractError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ProposalContractError(f"non-finite JSON number: {value}")


def _require_exact_fields(value: dict[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ProposalContractError(
            f"{label} fields do not match contract; missing={missing}, unknown={unknown}"
        )


def _require_bounded_string(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ProposalContractError(f"{label} must be a non-blank string of 1..{maximum} chars")
    return value


def _require_score(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProposalContractError(f"{label} must be a JSON number")
    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ProposalContractError(f"{label} must be finite and between 0 and 1")
    return score


def validate_claim_key(value: str) -> str:
    """Validate the bounded syntax shared by provisional and governed claim keys."""

    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= MAX_CLAIM_KEY_CHARS
        or _CLAIM_KEY_PATTERN.fullmatch(value) is None
    ):
        raise ProposalContractError(
            "claim key must be 1..80 lowercase ASCII characters in dotted token form"
        )
    return value


def parse_model_proposals(raw_output: str) -> tuple[ModelMemoryProposal, ...]:
    """Strictly parse the measured model shape without trusting semantic fields."""

    if not isinstance(raw_output, str) or len(raw_output) > MAX_MODEL_OUTPUT_CHARS:
        raise ProposalContractError("model output must be a bounded string")
    leading_trimmed = raw_output.lstrip()
    decoder = json.JSONDecoder(
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=_reject_constant,
    )
    try:
        document, end = decoder.raw_decode(leading_trimmed)
    except ProposalContractError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProposalContractError("model output is not one strict JSON document") from exc
    if leading_trimmed[end:].strip():
        raise ProposalContractError("model output contains trailing non-whitespace")
    if not isinstance(document, dict):
        raise ProposalContractError("model output root must be an object")
    _require_exact_fields(document, frozenset({"candidates"}), "root")
    candidates = document["candidates"]
    if not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATES:
        raise ProposalContractError("candidates must be an array of 0..3 objects")
    return tuple(_parse_candidate(candidate) for candidate in candidates)


def _parse_candidate(value: Any) -> ModelMemoryProposal:
    if not isinstance(value, dict):
        raise ProposalContractError("candidate must be an object")
    _require_exact_fields(value, _CANDIDATE_FIELDS, "candidate")
    text = _require_bounded_string(value["text"], "candidate text", MAX_TEXT_CHARS)
    try:
        advisory_kind = GovernedMemoryKind(value["kind"])
    except (TypeError, ValueError) as exc:
        raise ProposalContractError("candidate kind is outside the advisory vocabulary") from exc
    advisory_claim_key = validate_claim_key(value["claim_key"])
    candidate_value = value["value"]
    if candidate_value is not None and (
        not isinstance(candidate_value, str) or len(candidate_value) > MAX_VALUE_CHARS
    ):
        raise ProposalContractError("candidate value must be null or a string of 0..160 chars")
    try:
        advisory_relation = AdvisoryRelation(value["relation"])
    except (TypeError, ValueError) as exc:
        raise ProposalContractError("candidate relation is unsupported") from exc
    evidence_values = value["evidence_refs"]
    if (
        not isinstance(evidence_values, list)
        or not 1 <= len(evidence_values) <= MAX_EVIDENCE_REFS
    ):
        raise ProposalContractError("candidate evidence_refs must contain 1..3 objects")
    evidence_refs = tuple(_parse_evidence_ref(item) for item in evidence_values)
    return ModelMemoryProposal(
        text=text,
        advisory_kind=advisory_kind,
        advisory_claim_key=advisory_claim_key,
        value=candidate_value,
        advisory_relation=advisory_relation,
        evidence_refs=evidence_refs,
        confidence=_require_score(value["confidence"], "confidence"),
        importance=_require_score(value["importance"], "importance"),
    )


def _parse_evidence_ref(value: Any) -> ModelEvidenceRef:
    if not isinstance(value, dict):
        raise ProposalContractError("evidence reference must be an object")
    _require_exact_fields(value, _EVIDENCE_FIELDS, "evidence reference")
    turn_id = _require_bounded_string(
        value["source_turn_id"],
        "source_turn_id",
        MAX_TURN_ID_CHARS,
    )
    try:
        source_field = EvidenceField(value["source_field"])
    except (TypeError, ValueError) as exc:
        raise ProposalContractError("source_field must be transcript or response_text") from exc
    excerpt = _require_bounded_string(value["excerpt"], "evidence excerpt", MAX_EXCERPT_CHARS)
    return ModelEvidenceRef(
        source_turn_id=turn_id,
        source_field=source_field,
        excerpt=excerpt,
    )


def verify_evidence_refs(
    proposal: ModelMemoryProposal,
    persisted_turns: Iterable[PersistedTurnEvidence],
) -> tuple[VerifiedEvidenceRef, ...]:
    """Verify allowlisted turn/field/excerpt evidence and derive its authority."""

    turns: dict[str, PersistedTurnEvidence] = {}
    for persisted_turn in persisted_turns:
        _require_bounded_string(persisted_turn.session_id, "session_id", MAX_SESSION_ID_CHARS)
        _require_bounded_string(persisted_turn.turn_id, "turn_id", MAX_TURN_ID_CHARS)
        if persisted_turn.turn_id in turns:
            raise ProposalContractError(f"duplicate persisted turn_id: {persisted_turn.turn_id}")
        turns[persisted_turn.turn_id] = persisted_turn

    verified: list[VerifiedEvidenceRef] = []
    origins: set[tuple[str, EvidenceField, str]] = set()
    for evidence in proposal.evidence_refs:
        matched_turn = turns.get(evidence.source_turn_id)
        if matched_turn is None:
            raise ProposalContractError(
                f"evidence turn is not in the persisted allowlist: {evidence.source_turn_id}"
            )
        if matched_turn.failure_reason is not None:
            raise ProposalContractError("failed turns cannot ground memory candidates")
        field_text = (
            matched_turn.transcript
            if evidence.source_field is EvidenceField.TRANSCRIPT
            else matched_turn.response_text
        )
        if field_text is None or evidence.excerpt not in field_text:
            raise ProposalContractError("evidence excerpt is not an exact persisted-field substring")
        origin = (matched_turn.turn_id, evidence.source_field, evidence.excerpt)
        if origin in origins:
            raise ProposalContractError("duplicate evidence reference")
        origins.add(origin)
        authority = (
            EvidenceAuthority.DIRECT_USER_STATEMENT
            if evidence.source_field is EvidenceField.TRANSCRIPT
            else EvidenceAuthority.ASSISTANT_INFERENCE
        )
        verified.append(
            VerifiedEvidenceRef(
                session_id=matched_turn.session_id,
                source_turn_id=matched_turn.turn_id,
                source_field=evidence.source_field,
                excerpt=evidence.excerpt,
                authority=authority,
            )
        )
    return tuple(verified)


def derive_provisional_claim_key(evidence_refs: Iterable[VerifiedEvidenceRef]) -> str:
    """Derive a stable application key from exact persisted evidence origins."""

    refs = tuple(evidence_refs)
    if not refs:
        raise ProposalContractError("at least one verified evidence reference is required")
    canonical = sorted(
        (
            {
                "session_id": ref.session_id,
                "source_turn_id": ref.source_turn_id,
                "source_field": ref.source_field.value,
                "excerpt": ref.excerpt,
            }
            for ref in refs
        ),
        key=lambda item: (
            item["session_id"],
            item["source_turn_id"],
            item["source_field"],
            item["excerpt"],
        ),
    )
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]
    return f"claim.{digest}"


def build_provisional_candidate(
    proposal: ModelMemoryProposal,
    persisted_turns: Iterable[PersistedTurnEvidence],
) -> ProvisionalMemoryCandidate:
    """Build a review-only candidate; never confer governed identity or lifecycle authority."""

    evidence_refs = verify_evidence_refs(proposal, persisted_turns)
    if any(
        ref.authority is not EvidenceAuthority.DIRECT_USER_STATEMENT for ref in evidence_refs
    ):
        raise ProposalContractError(
            "automatic proposals require direct transcript evidence; assistant evidence is rejected"
        )
    return ProvisionalMemoryCandidate(
        text=proposal.text,
        kind=PROVISIONAL_MEMORY_KIND,
        claim_key=derive_provisional_claim_key(evidence_refs),
        evidence_refs=evidence_refs,
        confidence=proposal.confidence,
        importance=proposal.importance,
        disposition=CandidateDisposition.REVIEW_REQUIRED,
        advisory_kind=proposal.advisory_kind,
        advisory_claim_key=proposal.advisory_claim_key,
        advisory_relation=proposal.advisory_relation,
    )


def build_provisional_candidates(
    proposals: Iterable[ModelMemoryProposal],
    persisted_turns: Iterable[PersistedTurnEvidence],
) -> tuple[ProvisionalMemoryCandidate, ...]:
    """Build candidates and reject ambiguous duplicate evidence identities."""

    turns = tuple(persisted_turns)
    candidates = tuple(build_provisional_candidate(proposal, turns) for proposal in proposals)
    keys = [candidate.claim_key for candidate in candidates]
    if len(keys) != len(set(keys)):
        raise ProposalContractError(
            "multiple proposals share one evidence identity and require operator disambiguation"
        )
    return candidates


def apply_identity_decision(
    candidate: ProvisionalMemoryCandidate,
    decision: ApplicationIdentityDecision,
) -> GovernedClaimIdentity:
    """Apply trusted application identity, ignoring every advisory model identity field."""

    claim_key = decision.related_claim_key or candidate.claim_key
    return GovernedClaimIdentity(kind=decision.kind, claim_key=validate_claim_key(claim_key))
