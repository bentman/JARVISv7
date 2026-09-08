from __future__ import annotations

import json
import threading
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

from backend.app.actions.boundaries import (
    ActionCancelledError,
    ActionOperation,
    ExecutionBoundary,
    bound_result,
    bounded_deadline,
    run_bounded,
)
from backend.app.actions.catalog import CapabilityObservation, build_descriptors
from backend.app.actions.contracts import (
    ActionCancellationRecord,
    ApprovalAuditRecord,
    ApprovalOutcome,
    AuthorizationContext,
    AuthorizationDecision,
    CapabilityDescriptor,
    CapabilityRegistry,
    ExecutionResultRecord,
    ExecutionStatus,
    ModelActionProposal,
)
from backend.app.artifacts.storage import append_action_event

CapabilityHandler = Callable[[dict[str, Any], ActionOperation], dict[str, Any]]
T = TypeVar("T")

MAX_PENDING = 8
PENDING_TTL_S = 300.0
MAX_AUDIT_RECORDS = 100
MAX_ARGUMENT_BYTES = 8_000
SECRET_MASK = "***"
SECRET_ARGUMENT_KEYS = frozenset({"api_key", "tavily_api_key", "secret", "token", "password"})
SECRET_FIELD_KEYS = frozenset({"TAVILY_API_KEY"})

DEFAULT_BOUNDARY = ExecutionBoundary(
    storage_roots=(), timeout_ms=30_000, cancellable=False, max_result_bytes=16_000
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class CapabilityServiceError(Exception):
    status_code: int
    error: str
    message: str

    def detail(self) -> dict[str, str]:
        return {"error": self.error, "message": self.message}


@dataclass(frozen=True, slots=True)
class CapabilityView:
    capability_id: str
    effect_class: str
    readiness: str
    availability: str
    authorization_rule: str
    approval_mode: str
    execution_owner: str
    unavailable_explanation: str
    input_schema: dict[str, Any]
    result_schema: dict[str, Any]
    timeout_policy: dict[str, Any]
    cancellation_policy: dict[str, Any]
    executable: bool


@dataclass(frozen=True, slots=True)
class CapabilityCatalogView:
    capabilities: list[CapabilityView] = field(default_factory=list)
    problems: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ActionProposalView:
    proposal_id: str
    capability_id: str
    status: str
    outcome: str
    reason: str
    arguments: dict[str, Any]
    approval_id: str | None = None
    expires_at: str | None = None
    execution: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class PendingApprovalView:
    proposal_id: str
    capability_id: str
    approval_id: str
    arguments: dict[str, Any]
    reason: str
    expires_at: str


@dataclass(frozen=True, slots=True)
class ActionAuditView:
    records: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class _PendingProposal:
    proposal: ModelActionProposal
    decision: AuthorizationDecision
    created_at: float
    expires_at: str
    definition_claim: dict[str, Any] = field(default_factory=dict)
    decided: bool = False
    status: str = "awaiting_approval"
    execution: dict[str, Any] | None = None


class CapabilityService:
    def __init__(
        self,
        *,
        observe: Callable[[], CapabilityObservation],
        handlers: dict[str, CapabilityHandler] | None = None,
        on_event: Callable[[str, dict[str, object]], None] | None = None,
        evidence_dir: Path | None = None,
    ) -> None:
        self._observe = observe
        self._handlers = dict(handlers or {})
        self._on_event = on_event
        self._evidence_dir = evidence_dir
        self._lock = threading.RLock()
        self._registry = CapabilityRegistry()
        self._pending: dict[str, _PendingProposal] = {}
        self._audit: deque[dict[str, Any]] = deque(maxlen=MAX_AUDIT_RECORDS)
        self._active: dict[str, ActionOperation] = {}
        self._extension_bindings: Callable[[], list[tuple[CapabilityDescriptor, CapabilityHandler]]] | None = None
        self._handler_providers: list[Callable[[], dict[str, CapabilityHandler]]] = []
        self._problems: list[dict[str, str]] = []
        self._contexts: dict[str, AuthorizationContext] = {}
        self.refresh()

    def bind_extensions(
        self, provider: Callable[[], list[tuple[CapabilityDescriptor, CapabilityHandler | None]]]
    ) -> None:
        self._extension_bindings = provider
        self.refresh()

    def bind_handler_provider(
        self, provider: Callable[[], dict[str, CapabilityHandler]]
    ) -> None:
        """Bind executors for descriptors another source already owns.

        The provider is re-read on every refresh, so a capability whose descriptor is rebuilt
        from live observation cannot end up served without its executor.
        """
        self._handler_providers.append(provider)
        self.refresh()

    def refresh(self) -> None:
        registry = CapabilityRegistry()
        observation = self._observe()
        problems: list[dict[str, str]] = [
            {"capability_id": capability_id, "reason": reason}
            for capability_id, reason in observation.agent_errors
        ]
        bindings = self._extension_bindings() if self._extension_bindings else []
        descriptors = [*build_descriptors(observation), *(item for item, _ in bindings)]
        for descriptor in descriptors:
            # One malformed descriptor must not take the whole governed loop offline; it is
            # reported in the catalog instead of hidden.
            try:
                registry.register(descriptor)
            except Exception as exc:
                problems.append(
                    {"capability_id": descriptor.capability_id, "reason": handler_error(exc)}
                )
        provided: dict[str, CapabilityHandler] = {}
        for provider in self._handler_providers:
            with suppress(Exception):
                provided.update(provider())
        with self._lock:
            for descriptor, handler in bindings:
                if handler is not None:
                    self._handlers[descriptor.capability_id] = handler
            self._handlers.update(provided)
            self._registry = registry
            self._problems = problems
            self._evict_expired()

    def descriptor(self, capability_id: str) -> CapabilityDescriptor | None:
        with self._lock:
            return self._registry.get(capability_id)

    def catalog(self) -> CapabilityCatalogView:
        self.refresh()
        with self._lock:
            descriptors = [self._registry.get(row["capability_id"]) for row in self._registry.snapshot()]
            problems = sorted(self._problems, key=lambda item: item["capability_id"])
        return CapabilityCatalogView(
            capabilities=[self._view(descriptor) for descriptor in descriptors if descriptor],
            problems=problems,
        )

    def authorize_turn(
        self, proposal: ModelActionProposal, context: AuthorizationContext
    ) -> AuthorizationDecision:
        with self._lock:
            return self._registry.authorize(proposal, context)

    def propose(
        self,
        *,
        capability_id: str,
        arguments: dict[str, Any],
        proposed_by: str,
        reason: str,
        caller: str = "actions_api",
        session_id: str = "api",
        turn_id: str | None = None,
    ) -> ActionProposalView:
        self.refresh()
        descriptor = self.descriptor(capability_id)
        if descriptor is None:
            raise CapabilityServiceError(404, "unknown_capability", "capability is not registered")
        if descriptor.approval_mode == "turn_boundary":
            raise CapabilityServiceError(
                409,
                "turn_boundary_capability",
                "this capability is proposed and executed inside a conversation turn",
            )
        if _argument_bytes(arguments) > MAX_ARGUMENT_BYTES:
            raise CapabilityServiceError(
                413, "arguments_too_large", "action arguments exceed the accepted size"
            )

        proposal_id = uuid4().hex
        proposal = ModelActionProposal(
            proposal_id=proposal_id,
            capability_id=capability_id,
            arguments=dict(arguments),
            proposed_by=proposed_by,
            reason=reason,
        )
        context = AuthorizationContext(
            session_id=session_id, turn_id=turn_id or f"api:{proposal_id}", caller=caller
        )
        with self._lock:
            self._contexts[proposal_id] = context
            decision = self._registry.authorize(proposal, context)
        self._record("action_proposal", proposal, capability_id)
        self._record("authorization_decision", decision, capability_id)

        if decision.outcome == "approval_required":
            # Only a parked proposal needs its context later; eviction owns it from here.
            return self._park(proposal, decision)
        try:
            if decision.outcome == "denied":
                return self._view_proposal(proposal, decision, status="denied")
            return self._execute(proposal, descriptor, decision)
        finally:
            with self._lock:
                self._contexts.pop(proposal_id, None)

    def decide(
        self,
        *,
        proposal_id: str,
        outcome: ApprovalOutcome,
        decided_by: str,
        reason: str | None = None,
    ) -> ActionProposalView:
        with self._lock:
            self._evict_expired()
            pending = self._pending.get(proposal_id)
            if pending is None:
                raise CapabilityServiceError(
                    404, "unknown_proposal", "no pending action awaits this decision"
                )
            if pending.decided:
                raise CapabilityServiceError(
                    409, "already_decided", "this action has already been decided"
                )
            pending.decided = True
            proposal = pending.proposal

        approval = ApprovalAuditRecord(
            approval_id=pending.decision.approval_id or uuid4().hex,
            proposal_id=proposal_id,
            capability_id=proposal.capability_id,
            outcome=outcome,
            decided_by=decided_by,
            decided_at=utc_now_iso(),
            reason=reason,
        )
        self._record("approval_record", approval, proposal.capability_id)

        if outcome == "denied":
            with self._lock:
                pending.status = "denied"
            return self._view_proposal(proposal, pending.decision, status="denied")

        # Availability can change between proposal and approval, so the ladder runs again.
        self.refresh()
        descriptor = self.descriptor(proposal.capability_id)
        if descriptor is None:
            with self._lock:
                pending.status = "denied"
            raise CapabilityServiceError(
                409, "capability_unavailable", "capability is no longer registered"
            )
        if descriptor.metadata_claims.get("definition", {}) != pending.definition_claim:
            with self._lock:
                pending.status = "denied"
            raise CapabilityServiceError(409, "definition_changed", "extension changed; propose the action again")
        original = self._contexts.get(proposal_id)
        context = AuthorizationContext(
            session_id=original.session_id if original else "api",
            turn_id=original.turn_id if original else f"api:{proposal_id}",
            caller=original.caller if original else "actions_api",
            operator_approved=True,
            approval_id=approval.approval_id,
        )
        with self._lock:
            decision = self._registry.authorize(proposal, context)
        self._record("authorization_decision", decision, proposal.capability_id)
        if decision.outcome != "allowed":
            with self._lock:
                pending.status = "denied"
            return self._view_proposal(proposal, decision, status="denied")
        view = self._execute(proposal, descriptor, decision)
        with self._lock:
            pending.status = view.status
            pending.execution = view.execution
        return view

    def status(self, proposal_id: str) -> ActionProposalView:
        with self._lock:
            self._evict_expired()
            pending = self._pending.get(proposal_id)
            if pending is not None:
                return self._view_proposal(
                    pending.proposal, pending.decision, status=pending.status,
                    expires_at=pending.expires_at, execution=pending.execution,
                )
            for record in reversed(self._audit):
                if record.get("proposal_id") == proposal_id and record["kind"] == "execution_result":
                    return ActionProposalView(
                        proposal_id=proposal_id,
                        capability_id=str(record["capability_id"]),
                        status=str(record["record"]["status"]),
                        outcome="allowed",
                        reason="execution recorded",
                        arguments={},
                        execution=record["record"],
                    )
        raise CapabilityServiceError(404, "unknown_proposal", "no action matches this identifier")

    def cancel(self, proposal_id: str) -> bool:
        with self._lock:
            operation = self._active.get(proposal_id)
            if operation is not None:
                operation.cancel.set()
                return True
            pending = self._pending.get(proposal_id)
            if pending is not None and pending.decided:
                return False
            self._pending.pop(proposal_id, None)
        if pending is None:
            return False
        self._record(
            "action_cancellation",
            ActionCancellationRecord(
                proposal_id=proposal_id,
                capability_id=pending.proposal.capability_id,
                cancelled_by="operator",
                cancelled_at=utc_now_iso(),
                reason="approval cancelled before execution",
            ),
            pending.proposal.capability_id,
        )
        return True

    def pending(self) -> list[PendingApprovalView]:
        with self._lock:
            self._evict_expired()
            return [
                PendingApprovalView(
                    proposal_id=proposal_id,
                    capability_id=item.proposal.capability_id,
                    approval_id=item.decision.approval_id or "",
                    arguments=mask_arguments(item.proposal.capability_id, item.proposal.arguments),
                    reason=item.proposal.reason,
                    expires_at=item.expires_at,
                )
                for proposal_id, item in sorted(self._pending.items())
                if not item.decided
            ]

    def audit(self, *, limit: int = 20) -> ActionAuditView:
        with self._lock:
            records = list(self._audit)[-limit:]
        return ActionAuditView(records=list(reversed(records)))

    def execute_operator_action(
        self,
        capability_id: str,
        arguments: dict[str, Any],
        operation: Callable[[], T],
    ) -> T:
        """Authorize, execute, and record one direct operator request.

        The owning service's typed error is recorded and then re-raised, so route status
        codes and conflict payloads stay exactly what they were before convergence.
        """
        self.refresh()
        proposal_id = uuid4().hex
        started_at = utc_now_iso()
        proposal = ModelActionProposal(
            proposal_id=proposal_id,
            capability_id=capability_id,
            arguments=mask_arguments(capability_id, arguments),
            proposed_by="operator",
            reason="direct operator request",
        )
        approval_id = uuid4().hex
        context = AuthorizationContext(
            session_id="api",
            turn_id=f"api:{proposal_id}",
            caller="operator_api",
            operator_approved=True,
            approval_id=approval_id,
        )
        with self._lock:
            descriptor = self._registry.get(capability_id)
            decision = self._registry.authorize(proposal, context)
        self._record("action_proposal", proposal, capability_id)
        self._record("authorization_decision", decision, capability_id)
        if descriptor is not None and descriptor.authorization_rule == "requires_approval":
            self._record(
                "approval_record",
                ApprovalAuditRecord(
                    approval_id=approval_id,
                    proposal_id=proposal_id,
                    capability_id=capability_id,
                    outcome="approved",
                    decided_by="operator_api",
                    decided_at=started_at,
                    reason="direct operator request",
                ),
                capability_id,
            )
        # An operator request carries its own authority, so availability and readiness are
        # recorded but do not gate: the owning service reports those conditions with more
        # fidelity than a descriptor explanation can.
        if _blocks_operator_action(descriptor, decision):
            raise CapabilityServiceError(403, "not_authorized", decision.reason)

        boundary = (
            ExecutionBoundary.from_mapping(descriptor.boundaries)
            if descriptor is not None and descriptor.boundaries
            else DEFAULT_BOUNDARY
        )
        action = ActionOperation(
            "api", f"api:{proposal_id}", proposal_id, capability_id, boundary
        )
        with self._lock:
            self._active[proposal_id] = action
        try:
            with bounded_deadline(action):
                value = operation()
        except Exception as exc:
            self._record(
                "execution_result",
                ExecutionResultRecord(
                    proposal_id=proposal_id,
                    capability_id=capability_id,
                    status="failure",
                    result={},
                    started_at=started_at,
                    completed_at=utc_now_iso(),
                    error=handler_error(exc),
                ),
                capability_id,
            )
            raise
        finally:
            with self._lock:
                self._active.pop(proposal_id, None)

        artifacts: dict[str, Any] = {"duration_ms": round(action.elapsed_ms(), 3)}
        if action.expired():
            artifacts["timeout_exceeded"] = True
        self._record(
            "execution_result",
            ExecutionResultRecord(
                proposal_id=proposal_id,
                capability_id=capability_id,
                status="success",
                result=bound_result(_recordable(value), boundary.max_result_bytes, artifacts),
                started_at=started_at,
                completed_at=utc_now_iso(),
                artifacts=artifacts,
            ),
            capability_id,
        )
        return value

    def _execute(
        self,
        proposal: ModelActionProposal,
        descriptor: CapabilityDescriptor,
        decision: AuthorizationDecision,
    ) -> ActionProposalView:
        handler = self._handlers.get(proposal.capability_id)
        started_at = utc_now_iso()
        if handler is None:
            record = ExecutionResultRecord(
                proposal_id=proposal.proposal_id,
                capability_id=proposal.capability_id,
                status="failure",
                result={},
                started_at=started_at,
                completed_at=utc_now_iso(),
                error="capability has no application-owned execution handler",
            )
            self._record("execution_result", record, proposal.capability_id)
            return self._view_proposal(
                proposal, decision, status="failure", execution=record.to_dict()
            )

        boundary = (
            ExecutionBoundary.from_mapping(descriptor.boundaries)
            if descriptor.boundaries
            else DEFAULT_BOUNDARY
        )
        context = self._contexts.get(proposal.proposal_id)
        operation = ActionOperation(
            context.session_id if context else "api",
            context.turn_id if context else f"api:{proposal.proposal_id}", proposal.proposal_id,
            proposal.capability_id, boundary,
        )
        with self._lock:
            self._active[proposal.proposal_id] = operation
        status: ExecutionStatus = "success"
        result: dict[str, Any] = {}
        artifacts: dict[str, Any] = {}
        error: str | None = None
        try:
            result, artifacts = run_bounded(
                operation, lambda op: handler(proposal.arguments, op)
            )
        except ActionCancelledError:
            status, error = "cancelled", None
        except Exception as exc:
            status, error = "failure", handler_error(exc)
        finally:
            with self._lock:
                self._active.pop(proposal.proposal_id, None)

        record = ExecutionResultRecord(
            proposal_id=proposal.proposal_id,
            capability_id=proposal.capability_id,
            status=status,
            result=result,
            started_at=started_at,
            completed_at=utc_now_iso(),
            error=error,
            artifacts=artifacts,
        )
        self._record("execution_result", record, proposal.capability_id)
        if status == "cancelled":
            self._record(
                "action_cancellation",
                ActionCancellationRecord(
                    proposal_id=proposal.proposal_id,
                    capability_id=proposal.capability_id,
                    cancelled_by="operator",
                    cancelled_at=utc_now_iso(),
                    reason="execution cancelled or timed out",
                ),
                proposal.capability_id,
            )
        return self._view_proposal(proposal, decision, status=status, execution=record.to_dict())

    def _park(
        self, proposal: ModelActionProposal, decision: AuthorizationDecision
    ) -> ActionProposalView:
        approval_id = decision.approval_id or uuid4().hex
        decision = AuthorizationDecision(
            proposal_id=decision.proposal_id,
            capability_id=decision.capability_id,
            outcome=decision.outcome,
            reason=decision.reason,
            approval_required=True,
            approval_id=approval_id,
        )
        now = datetime.now(UTC)
        expires_at = datetime.fromtimestamp(now.timestamp() + PENDING_TTL_S, tz=UTC).isoformat()
        with self._lock:
            self._evict_expired()
            if len(self._pending) >= MAX_PENDING:
                oldest = min(self._pending, key=lambda key: self._pending[key].created_at)
                self._pending.pop(oldest)
            self._pending[proposal.proposal_id] = _PendingProposal(
                proposal=proposal,
                decision=decision,
                created_at=now.timestamp(),
                expires_at=expires_at,
                definition_claim=dict(self._registry.get(proposal.capability_id).metadata_claims.get("definition", {})),
            )
        return self._view_proposal(
            proposal, decision, status="awaiting_approval", expires_at=expires_at
        )

    def _evict_expired(self) -> None:
        cutoff = datetime.now(UTC).timestamp() - PENDING_TTL_S
        for proposal_id in [
            key for key, item in self._pending.items() if item.created_at < cutoff
        ]:
            self._pending.pop(proposal_id, None)
            self._contexts.pop(proposal_id, None)

    def _view(self, descriptor: CapabilityDescriptor) -> CapabilityView:
        return CapabilityView(
            capability_id=descriptor.capability_id,
            effect_class=descriptor.effect_class,
            readiness=descriptor.readiness,
            availability=descriptor.availability,
            authorization_rule=descriptor.authorization_rule,
            approval_mode=descriptor.approval_mode,
            execution_owner=descriptor.execution_owner,
            unavailable_explanation=descriptor.unavailable_explanation,
            input_schema=descriptor.input_schema,
            result_schema=descriptor.result_schema,
            timeout_policy=descriptor.timeout_policy,
            cancellation_policy=descriptor.cancellation_policy,
            executable=descriptor.capability_id in self._handlers,
        )

    def _view_proposal(
        self,
        proposal: ModelActionProposal,
        decision: AuthorizationDecision,
        *,
        status: str,
        expires_at: str | None = None,
        execution: dict[str, Any] | None = None,
    ) -> ActionProposalView:
        return ActionProposalView(
            proposal_id=proposal.proposal_id,
            capability_id=proposal.capability_id,
            status=status,
            outcome=decision.outcome,
            reason=decision.reason,
            arguments=mask_arguments(proposal.capability_id, proposal.arguments),
            approval_id=decision.approval_id,
            expires_at=expires_at,
            execution=execution,
        )

    def _record(self, kind: str, record: Any, capability_id: str) -> None:
        payload = record.to_dict()
        if "arguments" in payload:
            payload["arguments"] = mask_arguments(capability_id, payload["arguments"])
        if "result" in payload:
            payload["result"] = mask_arguments(capability_id, payload["result"])
        entry = {
            "kind": kind,
            "capability_id": capability_id,
            "proposal_id": payload.get("proposal_id"),
            "recorded_at": utc_now_iso(),
            "record": payload,
        }
        with self._lock:
            self._audit.append(entry)
        if self._evidence_dir is not None:
            # Durable evidence must not depend on an active session or survive only in memory.
            with suppress(Exception):
                append_action_event(entry, self._evidence_dir)
        if self._on_event is not None:
            # A timeline sink must never be able to fail an action that already ran.
            with suppress(Exception):
                self._on_event(f"action.{kind}", dict(entry))


def _blocks_operator_action(
    descriptor: CapabilityDescriptor | None, decision: AuthorizationDecision
) -> bool:
    if descriptor is None:
        return True
    if decision.outcome == "allowed":
        return False
    return descriptor.authorization_rule == "deny" or decision.reason.startswith(
        "invalid arguments:"
    )


def _recordable(value: Any) -> dict[str, Any]:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        with suppress(Exception):
            return dump(mode="json")
    return {"value": str(value)[:256]}


def _argument_bytes(arguments: dict[str, Any]) -> int:
    return len(json.dumps(arguments, default=str).encode("utf-8"))


def mask_arguments(capability_id: str, arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return {}
    masked: dict[str, Any] = {}
    for key, value in arguments.items():
        if key.lower() in SECRET_ARGUMENT_KEYS:
            masked[key] = SECRET_MASK
        elif key == "fields" and isinstance(value, dict):
            masked[key] = {
                name: SECRET_MASK if name in SECRET_FIELD_KEYS else item
                for name, item in value.items()
            }
        else:
            masked[key] = value
    return masked


def handler_error(exc: Exception) -> str:
    message = getattr(exc, "message", None)
    if isinstance(message, str) and message:
        return message[:256]
    if isinstance(exc, (ValueError, RuntimeError)):
        return str(exc)[:256]
    return "capability execution failed"


def execute_operator_action(
    service: CapabilityService | None,
    capability_id: str,
    arguments: dict[str, Any],
    operation: Callable[[], T],
) -> T:
    if service is None:
        return operation()
    return service.execute_operator_action(capability_id, arguments, operation)


def build_capability_handlers(
    *,
    memory_service_provider: Callable[[], Any],
    operator_config: Any = None,
    provider_store_factory: Callable[[], Any] | None = None,
    env_file: Any = None,
) -> dict[str, CapabilityHandler]:
    from backend.app.actions import catalog

    def memory(operation: str) -> CapabilityHandler:
        def handler(arguments: dict[str, Any], _operation: ActionOperation) -> dict[str, Any]:
            service = memory_service_provider()
            if service is None:
                raise CapabilityServiceError(503, "unavailable", "memory service is unavailable")
            return asdict(getattr(service, operation)(**arguments))

        return handler

    def memory_lifecycle(operation: str) -> CapabilityHandler:
        def handler(arguments: dict[str, Any], _operation: ActionOperation) -> dict[str, Any]:
            service = memory_service_provider()
            if service is None:
                raise CapabilityServiceError(503, "unavailable", "memory service is unavailable")
            arguments = dict(arguments)
            fact_id = arguments.pop("fact_id")
            return asdict(getattr(service, operation)(fact_id, **arguments))

        return handler

    handlers: dict[str, CapabilityHandler] = {
        catalog.MEMORY_RECORD_CONFIRM: memory_lifecycle("confirm"),
        catalog.MEMORY_RECORD_DISPUTE: memory_lifecycle("dispute"),
        catalog.MEMORY_RECORD_CORRECT: memory_lifecycle("correct"),
        catalog.MEMORY_RECORD_FORGET: memory_lifecycle("forget"),
        catalog.MEMORY_POLICY_UPDATE: memory("update_policy"),
    }

    if operator_config is not None and env_file is not None:
        def write_operator_config(
            arguments: dict[str, Any], _operation: ActionOperation
        ) -> dict[str, Any]:
            return asdict(operator_config.write(arguments["fields"], env_file=env_file))

        handlers[catalog.OPERATOR_CONFIG_WRITE] = write_operator_config

    if provider_store_factory is not None:
        def profile_write(
            arguments: dict[str, Any], _operation: ActionOperation
        ) -> dict[str, Any]:
            arguments = dict(arguments)
            profile_id = arguments.pop("profile_id", None)
            store = provider_store_factory()
            profile = (
                store.update_profile(profile_id, **arguments)
                if profile_id
                else store.create_profile(**arguments)
            )
            return {"profile_id": profile.profile_id, "readiness_state": profile.readiness_state}

        def profile_delete(
            arguments: dict[str, Any], _operation: ActionOperation
        ) -> dict[str, Any]:
            provider_store_factory().delete_profile(arguments["profile_id"])
            return {"deleted": True}

        def selection_update(
            arguments: dict[str, Any], _operation: ActionOperation
        ) -> dict[str, Any]:
            return asdict(provider_store_factory().set_selection(**arguments))

        def rotate_secret(
            _arguments: dict[str, Any], _operation: ActionOperation
        ) -> dict[str, Any]:
            provider_store_factory().rotate_key()
            return {"rotated": True}

        def connectivity_test(
            arguments: dict[str, Any], _operation: ActionOperation
        ) -> dict[str, Any]:
            from backend.app.services.llm_provider_service import provider_model_discovery

            store = provider_store_factory()
            profile = store.get_profile(arguments["profile_id"])
            if profile.kind == "managed_llama_cpp":
                return {"status": "configured", "models": []}
            models = provider_model_discovery(store, profile)
            return {"status": "ready", "models": [item.get("id") for item in models]}

        handlers[catalog.PROVIDER_PROFILE_WRITE] = profile_write
        handlers[catalog.PROVIDER_PROFILE_DELETE] = profile_delete
        handlers[catalog.PROVIDER_SELECTION_UPDATE] = selection_update
        handlers[catalog.PROVIDER_SECRET_ROTATE] = rotate_secret
        handlers[catalog.PROVIDER_CONNECTIVITY_TEST] = connectivity_test

    return handlers


def build_agent_handlers(
    *,
    agent_registry_provider: Callable[[], Any],
    engine_provider: Callable[[], Any],
) -> dict[str, CapabilityHandler]:
    """Executors for the `agent-invoke-*` descriptors the catalog builds from the registry."""
    from backend.app.agents.invocation import AgentInvoker

    registry = agent_registry_provider()
    if registry is None:
        return {}
    invoker = AgentInvoker(registry)

    def invoke(profile_id: str) -> CapabilityHandler:
        def handler(arguments: dict[str, Any], _operation: ActionOperation) -> dict[str, Any]:
            return invoker.invoke_direct(profile_id, arguments["prompt"], engine_provider).to_dict()

        return handler

    return {
        f"agent-invoke-{profile.profile_id}": invoke(profile.profile_id)
        for profile in registry.profiles()
    }


def build_extension_handlers(
    *,
    extension_service_provider: Callable[[], Any],
    extension_runtime_provider: Callable[[], Any] | None = None,
) -> dict[str, CapabilityHandler]:
    """Executors for the extension descriptors the catalog builds from live observation."""
    from backend.app.actions import catalog

    def set_state(arguments: dict[str, Any], _operation: ActionOperation) -> dict[str, Any]:
        service = extension_service_provider()
        if service is None:
            raise CapabilityServiceError(503, "unavailable", "extension catalog is unavailable")
        return asdict(
            service.set_state(
                extension_id=arguments["extension_id"],
                state=arguments["state"],
                expected_revision=arguments.get("expected_revision"),
                reason=arguments.get("reason"),
            )
        )

    def _runtime() -> Any:
        runtime = extension_runtime_provider() if extension_runtime_provider else None
        if runtime is None:
            raise CapabilityServiceError(503, "unavailable", "extension runtime is unavailable")
        return runtime

    def write_definition(arguments: dict[str, Any], _operation: ActionOperation) -> dict[str, Any]:
        payload = {
            "name": arguments["name"],
            "version": arguments["version"],
            "definition": arguments["definition"],
        }
        if "enabled" in arguments:
            payload["enabled"] = arguments["enabled"]
        return _runtime().write_definition(
            arguments["family"], arguments["local_id"], payload
        )

    def delete_definition(arguments: dict[str, Any], _operation: ActionOperation) -> dict[str, Any]:
        return _runtime().delete_definition(arguments["family"], arguments["local_id"])

    return {
        catalog.EXTENSION_STATE_UPDATE: set_state,
        catalog.EXTENSION_DEFINITION_WRITE: write_definition,
        catalog.EXTENSION_DEFINITION_DELETE: delete_definition,
    }


def observe_capabilities(
    *,
    settings_provider: Callable[[], Any],
    memory_service_provider: Callable[[], Any],
    provider_store_factory: Callable[[], Any] | None = None,
    operator_config_keys: tuple[str, ...] = (),
    env_file: Any = None,
    extension_catalog_present: bool = False,
    agent_registry_provider: Callable[[], Any] | None = None,
) -> CapabilityObservation:
    from backend.app.actions.catalog import ProviderObservation
    from backend.app.services.llm_provider_profiles import SecretStoreLockedError

    settings = settings_provider()
    memory_service = memory_service_provider()
    providers: tuple[ProviderObservation, ...] = ()
    store_present = False
    store_locked = False
    if provider_store_factory is not None:
        try:
            profiles = provider_store_factory().list_profiles(settings)
            providers = tuple(
                ProviderObservation(
                    profile_id=profile.profile_id,
                    kind=profile.kind,
                    readiness_state=profile.readiness_state,
                    cloud_eligible=profile.cloud_eligible,
                    builtin=profile.builtin,
                )
                for profile in profiles
            )
            store_present = True
        except SecretStoreLockedError:
            store_present, store_locked = True, True
        except Exception:
            store_present = False

    agent_capability_records: tuple[tuple[str, str, str, str, str, int, bool, str], ...] = ()
    agent_errors: tuple[tuple[str, str], ...] = ()
    if agent_registry_provider is not None:
        registry = agent_registry_provider()
        if registry is not None:
            agent_capability_records = tuple(registry.to_capability_records())
            agent_errors = tuple(registry.errors())

    return CapabilityObservation(
        search_providers=(
            ("ddgs", bool(getattr(settings, "use_ddgs", False))),
            ("searxng", bool(getattr(settings, "use_searxng", False))),
            ("tavily", bool(getattr(settings, "use_tavily", False))),
        ),
        memory_service_present=memory_service is not None,
        memory_curation_present=getattr(memory_service, "curation_service", None) is not None,
        provider_store_present=store_present,
        provider_store_locked=store_locked,
        providers=providers,
        operator_config_present=bool(env_file is not None and env_file.is_file()),
        operator_config_keys=operator_config_keys,
        extension_catalog_present=extension_catalog_present,
        agents=agent_capability_records,
        agent_errors=agent_errors,
    )


__all__ = [
    "ActionAuditView",
    "ActionProposalView",
    "CapabilityCatalogView",
    "CapabilityHandler",
    "CapabilityService",
    "CapabilityServiceError",
    "CapabilityView",
    "PendingApprovalView",
    "build_agent_handlers",
    "build_capability_handlers",
    "build_extension_handlers",
    "execute_operator_action",
    "mask_arguments",
    "observe_capabilities",
]
