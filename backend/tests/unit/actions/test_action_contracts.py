from __future__ import annotations

import pytest

from backend.app.actions import (
    AuthorizationContext,
    CapabilityDescriptor,
    CapabilityRegistry,
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
) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id=capability_id,
        source="builtin",
        provenance="backend.app.services.search_service",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        effect_class="external_read",
        readiness="ready",
        availability=availability,
        authorization_rule=authorization_rule,
        execution_owner="backend.app.services.search_service.SearchService",
        timeout_policy={"timeout_ms": 10000},
        cancellation_policy={"cancellable": True, "owner": "SearchOperation"},
        result_schema={"type": "object", "properties": {"sources": {"type": "array"}}},
        artifact_evidence={"records": ["action_proposals", "authorization_decisions", "action_execution_results"]},
        unavailable_explanation=unavailable_explanation,
        metadata_claims=metadata_claims or {},
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
