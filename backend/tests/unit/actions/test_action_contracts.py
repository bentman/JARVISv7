from __future__ import annotations

import pytest
from backend.app.actions import (
    ActionCancellationRecord,
    ActionEvidence,
    ApprovalAuditRecord,
    AuthorizationContext,
    AuthorizationDecision,
    CapabilityDescriptor,
    CapabilityRegistry,
    ExecutionResultRecord,
    ModelActionProposal,
)

SEARCH_PUBLIC_WEB_CAPABILITY_ID = "search-public-web"
LOCAL_NOTE_WRITE_CAPABILITY_ID = "local-note-write"


def descriptor(
    capability_id: str = SEARCH_PUBLIC_WEB_CAPABILITY_ID,
    *,
    authorization_rule: str = "allow",
    availability: str = "available",
    unavailable_explanation: str = "",
    metadata_claims: dict | None = None,
    readiness: str = "ready",
    effect_class: str = "external_read",
    approval_mode: str = "turn_boundary",
    boundaries: dict | None = None,
    input_schema: dict | None = None,
    cancellable: bool = True,
) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id=capability_id,
        source="builtin",
        provenance="backend.app.services.search_service",
        input_schema=input_schema
        or {"type": "object", "properties": {"query": {"type": "string"}}},
        effect_class=effect_class,
        readiness=readiness,
        availability=availability,
        authorization_rule=authorization_rule,
        execution_owner="backend.app.services.search_service.SearchService",
        timeout_policy={"timeout_ms": 10000},
        cancellation_policy={"cancellable": cancellable, "owner": "SearchOperation"},
        result_schema={"type": "object", "properties": {"sources": {"type": "array"}}},
        artifact_evidence={"records": ["action_proposals", "authorization_decisions", "action_execution_results"]},
        unavailable_explanation=unavailable_explanation,
        metadata_claims=metadata_claims or {},
        approval_mode=approval_mode,
        boundaries=boundaries if boundaries is not None else {},
    )


def proposal(capability_id: str = SEARCH_PUBLIC_WEB_CAPABILITY_ID) -> ModelActionProposal:
    return ModelActionProposal(
        proposal_id="proposal-1",
        capability_id=capability_id,
        arguments={"query": "public topic"},
        proposed_by="model",
        reason="user asked to search",
    )


def auth_context(**overrides) -> AuthorizationContext:
    values = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "caller": "conversation-turn",
    }
    values.update(overrides)
    return AuthorizationContext(**values)


def test_descriptor_requires_real_capability_metadata() -> None:
    with pytest.raises(ValueError, match="execution_owner"):
        descriptor().__class__(
            capability_id=SEARCH_PUBLIC_WEB_CAPABILITY_ID,
            source="builtin",
            provenance="backend.app.services.search_service",
            input_schema={"type": "object"},
            effect_class="external_read",
            readiness="ready",
            availability="available",
            authorization_rule="allow",
            execution_owner="",
            timeout_policy={"timeout_ms": 10000},
            cancellation_policy={"cancellable": True},
            result_schema={"type": "object"},
            artifact_evidence={"records": ["action_execution_results"]},
            unavailable_explanation="",
        )


@pytest.mark.parametrize(
    "field_name,value,message",
    [
        ("timeout_policy", {}, "timeout_policy must declare timeout_ms"),
        ("cancellation_policy", {}, "cancellation_policy must declare cancellable"),
        ("result_schema", {}, "result_schema must declare a type"),
        ("artifact_evidence", {}, "artifact_evidence must declare records"),
    ],
)
def test_descriptor_validates_required_owner_timeout_cancellation_and_result_fields(
    field_name: str,
    value: dict,
    message: str,
) -> None:
    values = descriptor().to_dict()
    values[field_name] = value

    with pytest.raises(ValueError, match=message):
        CapabilityDescriptor(**values)


def test_unavailable_descriptor_requires_user_facing_explanation() -> None:
    with pytest.raises(ValueError, match="unavailable_explanation"):
        descriptor(availability="disabled")


def test_descriptor_rejects_unknown_contract_categories() -> None:
    values = descriptor().to_dict()
    values["effect_class"] = "networkish"

    with pytest.raises(ValueError, match="effect_class must be one of"):
        CapabilityDescriptor(**values)


def test_registry_rejects_capability_id_collisions() -> None:
    registry = CapabilityRegistry()
    registry.register(descriptor())

    with pytest.raises(ValueError, match=SEARCH_PUBLIC_WEB_CAPABILITY_ID):
        registry.register(descriptor())


def test_registry_snapshot_is_sorted_by_explicit_descriptor_id() -> None:
    registry = CapabilityRegistry()
    registry.register(descriptor("zeta-action"))
    registry.register(descriptor("alpha-action"))

    assert [item["capability_id"] for item in registry.snapshot()] == ["alpha-action", "zeta-action"]


def test_server_declared_metadata_is_preserved_as_untrusted_claims() -> None:
    registry = CapabilityRegistry()
    registry.register(
        descriptor(
            metadata_claims={
                "mcp_server": {
                    "source": "example-server",
                    "trusted": False,
                    "claims": {"readOnlyHint": True},
                }
            }
        )
    )

    [snapshot] = registry.snapshot()
    assert snapshot["metadata_claims"]["mcp_server"]["claims"] == {"readOnlyHint": True}
    assert snapshot["metadata_claims"]["mcp_server"]["trusted"] is False


def test_server_declared_metadata_cannot_be_marked_trusted() -> None:
    with pytest.raises(ValueError, match="metadata claims must remain untrusted"):
        descriptor(metadata_claims={"mcp_server": {"trusted": True, "claims": {}}})


def test_authorization_allows_direct_low_risk_action() -> None:
    registry = CapabilityRegistry()
    registry.register(descriptor())

    decision = registry.authorize(proposal(), auth_context())

    assert decision.outcome == "allowed"
    assert decision.approval_required is False


def test_authorization_requires_operator_approval_for_approval_rule() -> None:
    registry = CapabilityRegistry()
    registry.register(descriptor(LOCAL_NOTE_WRITE_CAPABILITY_ID, authorization_rule="requires_approval"))

    decision = registry.authorize(proposal(LOCAL_NOTE_WRITE_CAPABILITY_ID), auth_context())

    assert decision.outcome == "approval_required"
    assert decision.approval_required is True


def test_authorization_accepts_prior_operator_approval() -> None:
    registry = CapabilityRegistry()
    registry.register(descriptor(LOCAL_NOTE_WRITE_CAPABILITY_ID, authorization_rule="requires_approval"))

    decision = registry.authorize(
        proposal(LOCAL_NOTE_WRITE_CAPABILITY_ID),
        auth_context(operator_approved=True, approval_id="approval-1"),
    )

    assert decision.outcome == "allowed"
    assert decision.approval_id == "approval-1"


def test_authorization_denies_unknown_or_unavailable_capability() -> None:
    registry = CapabilityRegistry()
    registry.register(descriptor(availability="disabled", unavailable_explanation="search provider disabled"))

    unknown = registry.authorize(proposal("missing-capability"), auth_context())
    unavailable = registry.authorize(proposal(), auth_context())

    assert unknown.outcome == "denied"
    assert unavailable.outcome == "denied"
    assert unavailable.reason == "search provider disabled"


def bounded(**overrides) -> dict:
    values = {"storage_roots": [], "timeout_ms": 10000, "cancellable": True, "max_result_bytes": 16000}
    values.update(overrides)
    return values


def test_approval_mode_must_be_a_declared_mode() -> None:
    assert descriptor(approval_mode="same_turn").approval_mode == "same_turn"

    with pytest.raises(ValueError, match="approval_mode must be one of"):
        descriptor(approval_mode="whenever")


def test_registry_refuses_privileged_execution_without_declared_boundaries() -> None:
    registry = CapabilityRegistry()

    with pytest.raises(ValueError, match="privileged_execution capabilities must declare boundaries"):
        registry.register(descriptor(effect_class="privileged_execution"))

    assert registry.get(SEARCH_PUBLIC_WEB_CAPABILITY_ID) is None


def test_registry_refuses_storage_roots_outside_the_approved_roots() -> None:
    registry = CapabilityRegistry()

    with pytest.raises(ValueError, match="storage_roots must be within"):
        registry.register(descriptor(boundaries=bounded(storage_roots=["/etc"])))


def test_registry_refuses_boundaries_that_contradict_the_declared_policies() -> None:
    registry = CapabilityRegistry()

    with pytest.raises(ValueError, match="timeout_ms must match timeout_policy"):
        registry.register(descriptor(boundaries=bounded(timeout_ms=999)))


def test_registry_enforces_full_json_schema() -> None:
    registry = CapabilityRegistry()
    schema = {"type": "object", "properties": {"value": {"type": "string", "pattern": "^x$"}}}
    registry.register(descriptor(input_schema=schema))
    from backend.app.actions.contracts import validate_arguments
    assert not validate_arguments(schema, {"value": "x"})
    assert validate_arguments(schema, {"value": "y"})
    assert validate_arguments({"type": "object", "$ref": "https://invalid.example/schema"}, {})


def test_authorization_denies_arguments_the_input_schema_rejects() -> None:
    registry = CapabilityRegistry()
    registry.register(
        descriptor(
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "maxLength": 8}},
                "required": ["query"],
                "additionalProperties": False,
            }
        )
    )

    decision = registry.authorize(proposal(), auth_context())

    assert decision.outcome == "denied"
    assert "arguments[query] violates maxLength" in decision.reason


def test_authorization_denies_capabilities_whose_readiness_is_unavailable() -> None:
    registry = CapabilityRegistry()
    registry.register(
        descriptor(readiness="unavailable", unavailable_explanation="No search provider is enabled.")
    )

    decision = registry.authorize(proposal(), auth_context())

    assert decision.outcome == "denied"
    assert decision.reason == "No search provider is enabled."


def test_execution_result_requires_an_error_when_it_failed() -> None:
    with pytest.raises(ValueError, match="failure results must include error"):
        ExecutionResultRecord(
            proposal_id="proposal-1",
            capability_id=SEARCH_PUBLIC_WEB_CAPABILITY_ID,
            status="failure",
            result={},
            started_at="2026-09-04T00:00:00+00:00",
            completed_at="2026-09-04T00:00:01+00:00",
        )


def test_approval_and_cancellation_records_require_attributable_identity() -> None:
    approval = ApprovalAuditRecord(
        approval_id="approval-1",
        proposal_id="proposal-1",
        capability_id=SEARCH_PUBLIC_WEB_CAPABILITY_ID,
        outcome="approved",
        decided_by="user",
        decided_at="2026-09-04T00:00:00+00:00",
    )
    assert approval.to_dict()["outcome"] == "approved"

    with pytest.raises(ValueError, match="outcome must be one of"):
        ApprovalAuditRecord(
            approval_id="approval-1",
            proposal_id="proposal-1",
            capability_id=SEARCH_PUBLIC_WEB_CAPABILITY_ID,
            outcome="expired",
            decided_by="user",
            decided_at="2026-09-04T00:00:00+00:00",
        )

    with pytest.raises(ValueError, match="cancelled_by must be a non-empty string"):
        ActionCancellationRecord(
            proposal_id="proposal-1",
            capability_id=SEARCH_PUBLIC_WEB_CAPABILITY_ID,
            cancelled_by="",
            cancelled_at="2026-09-04T00:00:00+00:00",
        )


def test_action_evidence_routes_each_record_to_its_artifact_field() -> None:
    evidence = ActionEvidence()
    evidence.record(proposal())
    evidence.record(
        AuthorizationDecision(
            proposal_id="proposal-1",
            capability_id=SEARCH_PUBLIC_WEB_CAPABILITY_ID,
            outcome="approval_required",
            reason="operator approval is required",
            approval_required=True,
        )
    )
    evidence.record(
        ApprovalAuditRecord(
            approval_id="approval-1",
            proposal_id="proposal-1",
            capability_id=SEARCH_PUBLIC_WEB_CAPABILITY_ID,
            outcome="approved",
            decided_by="user",
            decided_at="2026-09-04T00:00:00+00:00",
        )
    )
    evidence.record(
        ExecutionResultRecord(
            proposal_id="proposal-1",
            capability_id=SEARCH_PUBLIC_WEB_CAPABILITY_ID,
            status="success",
            result={"source_count": 2},
            started_at="2026-09-04T00:00:00+00:00",
            completed_at="2026-09-04T00:00:01+00:00",
        )
    )
    evidence.record(
        ActionCancellationRecord(
            proposal_id="proposal-1",
            capability_id=SEARCH_PUBLIC_WEB_CAPABILITY_ID,
            cancelled_by="turn_boundary",
            cancelled_at="2026-09-04T00:00:02+00:00",
        )
    )

    assert [len(bucket) for bucket in (
        evidence.proposals,
        evidence.authorization_decisions,
        evidence.approvals,
        evidence.executions,
        evidence.cancellations,
    )] == [1, 1, 1, 1, 1]
    assert evidence.proposals[0]["capability_id"] == SEARCH_PUBLIC_WEB_CAPABILITY_ID


def privileged(**overrides) -> dict:
    values = {
        "storage_roots": ["data"],
        "timeout_ms": 10000,
        "cancellable": True,
        "max_result_bytes": 16000,
        "process": {
            "subprocess": True,
            "argv_allowlist": ["git"],
            "env_passthrough": [],
            "working_root": "data",
        },
    }
    values.update(overrides)
    return values


def test_registry_refuses_privileged_execution_without_process_boundaries() -> None:
    registry = CapabilityRegistry()
    boundaries = privileged()
    del boundaries["process"]

    with pytest.raises(ValueError, match="must declare process boundaries"):
        registry.register(descriptor(effect_class="privileged_execution", boundaries=boundaries))


def test_registry_refuses_a_process_working_root_outside_the_declared_storage_roots() -> None:
    registry = CapabilityRegistry()
    boundaries = privileged(storage_roots=["reports"])

    with pytest.raises(ValueError, match="working_root must be one of the declared storage_roots"):
        registry.register(descriptor(effect_class="privileged_execution", boundaries=boundaries))


def test_registry_refuses_a_process_capability_that_cannot_be_cancelled() -> None:
    registry = CapabilityRegistry()

    with pytest.raises(ValueError, match="must be cancellable"):
        registry.register(
            descriptor(
                effect_class="local_write",
                boundaries=privileged(cancellable=False),
                cancellable=False,
            )
        )


def test_a_fully_declared_privileged_capability_registers_but_none_is_shipped() -> None:
    registry = CapabilityRegistry()

    registry.register(descriptor(effect_class="privileged_execution", boundaries=privileged()))

    assert registry.get(SEARCH_PUBLIC_WEB_CAPABILITY_ID) is not None
    # The rule exists ahead of any shipped privileged capability; the catalog registers none.
    from backend.app.actions.catalog import CapabilityObservation, build_descriptors

    shipped = build_descriptors(CapabilityObservation())
    assert not [item for item in shipped if item.effect_class == "privileged_execution"]
