from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from backend.app.actions.boundaries import require_boundaries

EffectClass = Literal[
    "local_read",
    "local_write",
    "external_read",
    "external_write",
    "cloud_model",
    "privileged_execution",
    "destructive_action",
]
ReadinessState = Literal["ready", "degraded", "unavailable"]
AvailabilityState = Literal["available", "disabled", "misconfigured", "unknown"]
AuthorizationRule = Literal["allow", "requires_approval", "deny"]
AuthorizationOutcome = Literal["allowed", "approval_required", "denied"]
ApprovalOutcome = Literal["approved", "denied"]
ExecutionStatus = Literal["success", "failure", "cancelled"]
ApprovalMode = Literal["turn_boundary", "same_turn"]

EFFECT_CLASSES = {
    "local_read",
    "local_write",
    "external_read",
    "external_write",
    "cloud_model",
    "privileged_execution",
    "destructive_action",
}
READINESS_STATES = {"ready", "degraded", "unavailable"}
AVAILABILITY_STATES = {"available", "disabled", "misconfigured", "unknown"}
AUTHORIZATION_RULES = {"allow", "requires_approval", "deny"}
AUTHORIZATION_OUTCOMES = {"allowed", "approval_required", "denied"}
APPROVAL_OUTCOMES = {"approved", "denied"}
EXECUTION_STATUSES = {"success", "failure", "cancelled"}
APPROVAL_MODES = {"turn_boundary", "same_turn"}


@dataclass(frozen=True, slots=True)
class ModelActionProposal:
    proposal_id: str
    capability_id: str
    arguments: dict[str, Any]
    proposed_by: str
    reason: str

    def __post_init__(self) -> None:
        _require_non_empty("proposal_id", self.proposal_id)
        _require_non_empty("capability_id", self.capability_id)
        _require_non_empty("proposed_by", self.proposed_by)
        _require_mapping("arguments", self.arguments)

    def to_dict(self) -> dict[str, Any]:
        return _deep_asdict(self)


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    capability_id: str
    source: str
    provenance: str
    input_schema: dict[str, Any]
    effect_class: EffectClass
    readiness: ReadinessState
    availability: AvailabilityState
    authorization_rule: AuthorizationRule
    execution_owner: str
    timeout_policy: dict[str, Any]
    cancellation_policy: dict[str, Any]
    result_schema: dict[str, Any]
    artifact_evidence: dict[str, Any]
    unavailable_explanation: str
    metadata_claims: dict[str, Any] = field(default_factory=dict)
    approval_mode: ApprovalMode = "same_turn"
    boundaries: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "capability_id",
            "source",
            "provenance",
            "effect_class",
            "readiness",
            "availability",
            "authorization_rule",
            "execution_owner",
        ):
            _require_non_empty(name, getattr(self, name))
        for name in (
            "input_schema",
            "timeout_policy",
            "cancellation_policy",
            "result_schema",
            "artifact_evidence",
            "metadata_claims",
            "boundaries",
        ):
            _require_mapping(name, getattr(self, name))
        if self.availability != "available":
            _require_non_empty("unavailable_explanation", self.unavailable_explanation)
        _require_one_of("effect_class", self.effect_class, EFFECT_CLASSES)
        _require_one_of("readiness", self.readiness, READINESS_STATES)
        _require_one_of("availability", self.availability, AVAILABILITY_STATES)
        _require_one_of("authorization_rule", self.authorization_rule, AUTHORIZATION_RULES)
        _require_one_of("approval_mode", self.approval_mode, APPROVAL_MODES)
        if "type" not in self.input_schema:
            raise ValueError("input_schema must declare a type")
        if "type" not in self.result_schema:
            raise ValueError("result_schema must declare a type")
        if "timeout_ms" not in self.timeout_policy:
            raise ValueError("timeout_policy must declare timeout_ms")
        if "cancellable" not in self.cancellation_policy:
            raise ValueError("cancellation_policy must declare cancellable")
        if "records" not in self.artifact_evidence:
            raise ValueError("artifact_evidence must declare records")
        _validate_untrusted_claims(self.metadata_claims)

    def to_dict(self) -> dict[str, Any]:
        return _deep_asdict(self)


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    session_id: str
    turn_id: str
    caller: str
    operator_approved: bool = False
    approval_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("session_id", self.session_id)
        _require_non_empty("turn_id", self.turn_id)
        _require_non_empty("caller", self.caller)

    def to_dict(self) -> dict[str, Any]:
        return _deep_asdict(self)


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    proposal_id: str
    capability_id: str
    outcome: AuthorizationOutcome
    reason: str
    approval_required: bool = False
    approval_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("proposal_id", self.proposal_id)
        _require_non_empty("capability_id", self.capability_id)
        _require_non_empty("outcome", self.outcome)
        _require_non_empty("reason", self.reason)
        _require_one_of("outcome", self.outcome, AUTHORIZATION_OUTCOMES)
        if self.outcome == "approval_required" and not self.approval_required:
            raise ValueError("approval_required decisions must set approval_required")

    def to_dict(self) -> dict[str, Any]:
        return _deep_asdict(self)


@dataclass(frozen=True, slots=True)
class ApprovalAuditRecord:
    approval_id: str
    proposal_id: str
    capability_id: str
    outcome: ApprovalOutcome
    decided_by: str
    decided_at: str
    reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("approval_id", "proposal_id", "capability_id", "outcome", "decided_by", "decided_at"):
            _require_non_empty(name, getattr(self, name))
        _require_one_of("outcome", self.outcome, APPROVAL_OUTCOMES)

    def to_dict(self) -> dict[str, Any]:
        return _deep_asdict(self)


@dataclass(frozen=True, slots=True)
class ExecutionResultRecord:
    proposal_id: str
    capability_id: str
    status: ExecutionStatus
    result: dict[str, Any]
    started_at: str
    completed_at: str
    error: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("proposal_id", "capability_id", "status", "started_at", "completed_at"):
            _require_non_empty(name, getattr(self, name))
        _require_one_of("status", self.status, EXECUTION_STATUSES)
        _require_mapping("result", self.result)
        _require_mapping("artifacts", self.artifacts)
        if self.status == "failure" and not self.error:
            raise ValueError("failure results must include error")

    def to_dict(self) -> dict[str, Any]:
        return _deep_asdict(self)


@dataclass(frozen=True, slots=True)
class ActionCancellationRecord:
    proposal_id: str
    capability_id: str
    cancelled_by: str
    cancelled_at: str
    reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("proposal_id", "capability_id", "cancelled_by", "cancelled_at"):
            _require_non_empty(name, getattr(self, name))

    def to_dict(self) -> dict[str, Any]:
        return _deep_asdict(self)


@dataclass(slots=True)
class ActionEvidence:
    proposals: list[dict[str, Any]] = field(default_factory=list)
    authorization_decisions: list[dict[str, Any]] = field(default_factory=list)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    executions: list[dict[str, Any]] = field(default_factory=list)
    cancellations: list[dict[str, Any]] = field(default_factory=list)

    def record(
        self,
        record: ModelActionProposal
        | AuthorizationDecision
        | ApprovalAuditRecord
        | ExecutionResultRecord
        | ActionCancellationRecord,
    ) -> None:
        _EVIDENCE_SINKS[type(record)](self).append(record.to_dict())


class CapabilityRegistry:
    def __init__(self) -> None:
        self._descriptors: dict[str, CapabilityDescriptor] = {}

    def register(self, descriptor: CapabilityDescriptor) -> CapabilityDescriptor:
        require_boundaries(
            descriptor.effect_class,
            descriptor.boundaries,
            descriptor.timeout_policy,
            descriptor.cancellation_policy,
        )
        validate_schema(descriptor.input_schema)
        if descriptor.capability_id in self._descriptors:
            raise ValueError(f"capability already registered: {descriptor.capability_id}")
        self._descriptors[descriptor.capability_id] = descriptor
        return descriptor

    def get(self, capability_id: str) -> CapabilityDescriptor | None:
        return self._descriptors.get(capability_id)

    def snapshot(self) -> list[dict[str, Any]]:
        return [self._descriptors[key].to_dict() for key in sorted(self._descriptors)]

    def authorize(
        self,
        proposal: ModelActionProposal,
        context: AuthorizationContext,
    ) -> AuthorizationDecision:
        descriptor = self.get(proposal.capability_id)
        if descriptor is None:
            return AuthorizationDecision(
                proposal_id=proposal.proposal_id,
                capability_id=proposal.capability_id,
                outcome="denied",
                reason="capability is not registered",
            )
        violations = validate_arguments(descriptor.input_schema, proposal.arguments)
        if violations:
            return AuthorizationDecision(
                proposal_id=proposal.proposal_id,
                capability_id=proposal.capability_id,
                outcome="denied",
                reason=f"invalid arguments: {violations[0]}",
            )
        if descriptor.readiness == "unavailable":
            return AuthorizationDecision(
                proposal_id=proposal.proposal_id,
                capability_id=proposal.capability_id,
                outcome="denied",
                reason=descriptor.unavailable_explanation or "capability is unavailable",
            )
        if descriptor.availability != "available":
            return AuthorizationDecision(
                proposal_id=proposal.proposal_id,
                capability_id=proposal.capability_id,
                outcome="denied",
                reason=descriptor.unavailable_explanation,
            )
        if descriptor.authorization_rule == "deny":
            return AuthorizationDecision(
                proposal_id=proposal.proposal_id,
                capability_id=proposal.capability_id,
                outcome="denied",
                reason="authorization rule denies execution",
            )
        if descriptor.authorization_rule == "requires_approval" and not context.operator_approved:
            return AuthorizationDecision(
                proposal_id=proposal.proposal_id,
                capability_id=proposal.capability_id,
                outcome="approval_required",
                reason="operator approval is required",
                approval_required=True,
            )
        return AuthorizationDecision(
            proposal_id=proposal.proposal_id,
            capability_id=proposal.capability_id,
            outcome="allowed",
            reason="authorization rule allows execution",
            approval_id=context.approval_id,
        )




def validate_schema(schema: dict[str, Any]) -> None:
    from jsonschema.validators import validator_for

    if not isinstance(schema, dict):
        raise ValueError("input_schema must be a mapping")
    validator_for(schema).check_schema(schema)


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> tuple[str, ...]:
    from jsonschema.validators import validator_for
    from referencing import Registry

    # An empty registry resolves local references without fetching remote schemas.
    validator = validator_for(schema)(schema, registry=Registry())
    try:
        return tuple(
            f"arguments{''.join(f'[{part}]' for part in error.absolute_path)} violates {error.validator}"
            + (f": {', '.join(error.validator_value)}" if error.validator == "required" else "")
            for error in validator.iter_errors(arguments)
        )
    except Exception:
        return ("arguments could not be validated against the declared schema",)




_EVIDENCE_SINKS: dict[type, Any] = {
    ModelActionProposal: lambda evidence: evidence.proposals,
    AuthorizationDecision: lambda evidence: evidence.authorization_decisions,
    ApprovalAuditRecord: lambda evidence: evidence.approvals,
    ExecutionResultRecord: lambda evidence: evidence.executions,
    ActionCancellationRecord: lambda evidence: evidence.cancellations,
}


def _require_non_empty(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_mapping(name: str, value: dict[str, Any]) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")


def _require_one_of(name: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(sorted(allowed))}")


def _validate_untrusted_claims(claims: dict[str, Any]) -> None:
    for key, claim in claims.items():
        _require_non_empty("metadata claim key", key)
        if not isinstance(claim, dict):
            raise ValueError("metadata claims must be mappings")
        if claim.get("trusted", False) is not False:
            raise ValueError("metadata claims must remain untrusted")


def _deep_asdict(value: Any) -> dict[str, Any]:
    return deepcopy(asdict(value))
