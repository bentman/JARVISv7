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


SCHEMA_KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "propertyNames",
    "enum", "items", "minLength", "maxLength", "minItems", "maxItems",
    "minimum", "maximum", "description",
}
SCHEMA_TYPES: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": (list, tuple),
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}


def validate_schema(schema: dict[str, Any]) -> None:
    if not isinstance(schema, dict):
        raise ValueError("input_schema must be a mapping")
    unsupported = sorted(set(schema) - SCHEMA_KEYWORDS)
    if unsupported:
        raise ValueError(f"input_schema uses unsupported keywords: {', '.join(unsupported)}")
    declared = schema.get("type")
    if declared is not None and declared not in SCHEMA_TYPES:
        raise ValueError(f"input_schema declares an unsupported type: {declared}")
    for subschema in schema.get("properties", {}).values():
        validate_schema(subschema)
    if "items" in schema:
        validate_schema(schema["items"])
    if "propertyNames" in schema:
        validate_schema(schema["propertyNames"])


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> tuple[str, ...]:
    return tuple(_schema_violations(schema, arguments, "arguments"))


def _schema_violations(schema: dict[str, Any], value: Any, path: str) -> list[str]:
    declared = schema.get("type")
    if declared is not None:
        expected = SCHEMA_TYPES[declared]
        if declared in {"integer", "number"} and isinstance(value, bool):
            return [f"{path} must be {declared}"]
        if not isinstance(value, expected):
            return [f"{path} must be {declared}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path} must be one of: {', '.join(str(item) for item in schema['enum'])}"]

    violations: list[str] = []
    if isinstance(value, str):
        violations += _bounds(path, len(value), schema.get("minLength"), schema.get("maxLength"), "characters")
    elif isinstance(value, (list, tuple)):
        violations += _bounds(path, len(value), schema.get("minItems"), schema.get("maxItems"), "items")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                violations += _schema_violations(item_schema, item, f"{path}[{index}]")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum, maximum = schema.get("minimum"), schema.get("maximum")
        if minimum is not None and value < minimum:
            violations.append(f"{path} must be at least {minimum}")
        if maximum is not None and value > maximum:
            violations.append(f"{path} must be at most {maximum}")
    elif isinstance(value, dict):
        violations += _object_violations(schema, value, path)
    return violations


def _object_violations(schema: dict[str, Any], value: dict[str, Any], path: str) -> list[str]:
    violations: list[str] = []
    properties = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in value:
            violations.append(f"{path} is missing required field {name}")
    if schema.get("additionalProperties") is False:
        for name in value:
            if name not in properties:
                violations.append(f"{path} does not accept field {name}")
    allowed_names = schema.get("propertyNames", {}).get("enum")
    if allowed_names is not None:
        for name in value:
            if name not in allowed_names:
                violations.append(f"{path} does not accept key {name}")
    for name, subschema in properties.items():
        if name in value:
            violations += _schema_violations(subschema, value[name], f"{path}.{name}")
    return violations


def _bounds(path: str, size: int, minimum: Any, maximum: Any, unit: str) -> list[str]:
    violations: list[str] = []
    if minimum is not None and size < minimum:
        violations.append(f"{path} must have at least {minimum} {unit}")
    if maximum is not None and size > maximum:
        violations.append(f"{path} must have at most {maximum} {unit}")
    return violations


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
