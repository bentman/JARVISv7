from __future__ import annotations

import threading

import pytest
from backend.app.actions.boundaries import ActionOperation
from backend.app.actions.catalog import (
    MEMORY_RECORD_CONFIRM,
    MEMORY_RECORD_FORGET,
    OPERATOR_CONFIG_WRITE,
    PROVIDER_PROFILE_WRITE,
    PROVIDER_SECRET_ROTATE,
    SEARCH_PUBLIC_WEB,
    CapabilityObservation,
    ProviderObservation,
)
from backend.app.services.capability_service import (
    CapabilityService,
    CapabilityServiceError,
    execute_operator_action,
    mask_arguments,
)

READY = CapabilityObservation(
    search_providers=(("ddgs", True), ("searxng", True), ("tavily", False)),
    memory_service_present=True,
    memory_curation_present=True,
    provider_store_present=True,
    providers=(ProviderObservation("p1", "openai", "configured", True, False),),
    operator_config_present=True,
    operator_config_keys=("USE_DDGS", "TAVILY_API_KEY"),
)


def service(observation: CapabilityObservation = READY, **handlers) -> CapabilityService:
    state = {"observation": observation}
    instance = CapabilityService(observe=lambda: state["observation"], handlers=handlers)
    instance.observed = state  # type: ignore[attr-defined]
    return instance


def capability(catalog, capability_id: str):
    return next(item for item in catalog.capabilities if item.capability_id == capability_id)


def confirm_arguments() -> dict:
    return {"fact_id": "fact-1", "expected_revision": 1}


def test_catalog_reports_search_unavailable_once_every_provider_is_disabled() -> None:
    instance = service()
    assert capability(instance.catalog(), SEARCH_PUBLIC_WEB).availability == "available"

    instance.observed["observation"] = CapabilityObservation(
        search_providers=(("ddgs", False), ("searxng", False), ("tavily", False))
    )
    entry = capability(instance.catalog(), SEARCH_PUBLIC_WEB)

    assert entry.availability == "disabled"
    assert entry.readiness == "unavailable"
    assert "Enable DDGS, SearXNG, or Tavily" in entry.unavailable_explanation


def test_catalog_degrades_search_readiness_with_a_single_provider() -> None:
    instance = service(
        CapabilityObservation(search_providers=(("ddgs", True), ("searxng", False)))
    )

    entry = capability(instance.catalog(), SEARCH_PUBLIC_WEB)

    assert (entry.availability, entry.readiness) == ("available", "degraded")


def test_catalog_reports_provider_capabilities_misconfigured_when_the_secret_store_is_locked() -> None:
    instance = service(
        CapabilityObservation(provider_store_present=True, provider_store_locked=True)
    )

    entry = capability(instance.catalog(), PROVIDER_PROFILE_WRITE)

    assert entry.availability == "misconfigured"
    assert "secret store is locked" in entry.unavailable_explanation


def test_catalog_reports_operator_config_misconfigured_without_an_env_file() -> None:
    instance = service(CapabilityObservation(operator_config_present=False))

    entry = capability(instance.catalog(), OPERATOR_CONFIG_WRITE)

    assert entry.availability == "misconfigured"
    assert ".env file is missing" in entry.unavailable_explanation


def test_catalog_marks_capabilities_without_a_handler_as_not_executable() -> None:
    instance = service(**{MEMORY_RECORD_CONFIRM: lambda args, op: {"ok": True}})
    catalog = instance.catalog()

    assert capability(catalog, MEMORY_RECORD_CONFIRM).executable is True
    assert capability(catalog, PROVIDER_SECRET_ROTATE).executable is False


def test_turn_boundary_capabilities_are_refused_at_the_api_edge() -> None:
    instance = service()

    with pytest.raises(CapabilityServiceError) as excinfo:
        instance.propose(
            capability_id=SEARCH_PUBLIC_WEB,
            arguments={"mode": "search", "topic": "weather", "queries": ["weather"]},
            proposed_by="operator",
            reason="operator asked",
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.error == "turn_boundary_capability"


def test_an_allowed_capability_executes_immediately() -> None:
    calls: list[dict] = []
    instance = service(**{MEMORY_RECORD_CONFIRM: lambda args, op: calls.append(args) or {"ok": True}})

    view = instance.propose(
        capability_id=MEMORY_RECORD_CONFIRM,
        arguments=confirm_arguments(),
        proposed_by="operator",
        reason="operator confirmed the fact",
    )

    assert (view.outcome, view.status) == ("allowed", "success")
    assert view.execution["result"] == {"ok": True}
    assert calls == [confirm_arguments()]


def test_an_approval_required_capability_parks_without_executing() -> None:
    calls: list[dict] = []
    instance = service(**{MEMORY_RECORD_FORGET: lambda args, op: calls.append(args) or {"ok": True}})

    view = instance.propose(
        capability_id=MEMORY_RECORD_FORGET,
        arguments=confirm_arguments(),
        proposed_by="model",
        reason="model proposed forgetting",
    )

    assert (view.outcome, view.status) == ("approval_required", "awaiting_approval")
    assert view.execution is None
    assert calls == []
    assert [item.proposal_id for item in instance.pending()] == [view.proposal_id]


def test_approval_executes_exactly_once_and_a_second_decision_is_refused() -> None:
    calls: list[dict] = []
    instance = service(**{MEMORY_RECORD_FORGET: lambda args, op: calls.append(args) or {"ok": True}})
    parked = instance.propose(
        capability_id=MEMORY_RECORD_FORGET,
        arguments=confirm_arguments(),
        proposed_by="model",
        reason="model proposed forgetting",
    )

    executed = instance.decide(
        proposal_id=parked.proposal_id, outcome="approved", decided_by="operator"
    )

    assert (executed.outcome, executed.status) == ("allowed", "success")
    assert len(calls) == 1
    assert instance.pending() == []

    with pytest.raises(CapabilityServiceError) as excinfo:
        instance.decide(proposal_id=parked.proposal_id, outcome="approved", decided_by="operator")
    assert excinfo.value.error in {"already_decided", "unknown_proposal"}
    assert len(calls) == 1


def test_a_denied_decision_never_executes() -> None:
    calls: list[dict] = []
    instance = service(**{MEMORY_RECORD_FORGET: lambda args, op: calls.append(args) or {"ok": True}})
    parked = instance.propose(
        capability_id=MEMORY_RECORD_FORGET,
        arguments=confirm_arguments(),
        proposed_by="model",
        reason="model proposed forgetting",
    )

    view = instance.decide(
        proposal_id=parked.proposal_id, outcome="denied", decided_by="operator", reason="no"
    )

    assert view.status == "denied"
    assert calls == []
    assert instance.pending() == []


def test_approval_reauthorizes_against_state_that_changed_while_parked() -> None:
    calls: list[dict] = []
    instance = service(**{MEMORY_RECORD_FORGET: lambda args, op: calls.append(args) or {"ok": True}})
    parked = instance.propose(
        capability_id=MEMORY_RECORD_FORGET,
        arguments=confirm_arguments(),
        proposed_by="model",
        reason="model proposed forgetting",
    )

    instance.observed["observation"] = CapabilityObservation(memory_service_present=False)
    view = instance.decide(
        proposal_id=parked.proposal_id, outcome="approved", decided_by="operator"
    )

    assert view.status == "denied"
    assert calls == []


def test_cancellation_of_a_parked_proposal_prevents_execution() -> None:
    calls: list[dict] = []
    instance = service(**{MEMORY_RECORD_FORGET: lambda args, op: calls.append(args) or {"ok": True}})
    parked = instance.propose(
        capability_id=MEMORY_RECORD_FORGET,
        arguments=confirm_arguments(),
        proposed_by="model",
        reason="model proposed forgetting",
    )

    assert instance.cancel(parked.proposal_id) is True
    assert instance.cancel(parked.proposal_id) is False
    assert calls == []
    assert any(record["kind"] == "action_cancellation" for record in instance.audit().records)


def test_a_cancelled_handler_records_a_cancelled_execution() -> None:
    def handler(args: dict, op: ActionOperation) -> dict:
        op.cancel.set()
        return {"ok": True}

    instance = service(**{MEMORY_RECORD_CONFIRM: handler})

    view = instance.propose(
        capability_id=MEMORY_RECORD_CONFIRM,
        arguments=confirm_arguments(),
        proposed_by="operator",
        reason="operator confirmed the fact",
    )

    assert view.status == "cancelled"
    assert view.execution["status"] == "cancelled"


def test_handler_failures_are_sanitized_before_they_reach_the_audit() -> None:
    def handler(args: dict, op: ActionOperation) -> dict:
        raise OSError("C:/private/memory.sqlite is locked by internal-vectorizer")

    instance = service(**{MEMORY_RECORD_CONFIRM: handler})

    view = instance.propose(
        capability_id=MEMORY_RECORD_CONFIRM,
        arguments=confirm_arguments(),
        proposed_by="operator",
        reason="operator confirmed the fact",
    )

    assert view.status == "failure"
    assert view.execution["error"] == "capability execution failed"
    for prohibited in ("C:/private", "internal-vectorizer", "sqlite"):
        assert prohibited not in str(instance.audit().records)


def test_a_capability_without_a_handler_fails_instead_of_silently_succeeding() -> None:
    instance = service()

    view = instance.propose(
        capability_id=MEMORY_RECORD_CONFIRM,
        arguments=confirm_arguments(),
        proposed_by="operator",
        reason="operator confirmed the fact",
    )

    assert view.status == "failure"
    assert view.execution["error"] == "capability has no application-owned execution handler"


def test_invalid_arguments_are_denied_before_any_handler_runs() -> None:
    calls: list[dict] = []
    instance = service(**{MEMORY_RECORD_CONFIRM: lambda args, op: calls.append(args) or {"ok": True}})

    view = instance.propose(
        capability_id=MEMORY_RECORD_CONFIRM,
        arguments={"fact_id": "fact-1"},
        proposed_by="operator",
        reason="operator confirmed the fact",
    )

    assert view.outcome == "denied"
    assert "missing required field expected_revision" in view.reason
    assert calls == []


def test_secret_arguments_are_masked_in_views_and_audit() -> None:
    instance = service(**{PROVIDER_PROFILE_WRITE: lambda args, op: {"ok": True}})
    parked = instance.propose(
        capability_id=PROVIDER_PROFILE_WRITE,
        arguments={
            "name": "cloud",
            "kind": "openai",
            "endpoint": "https://api.openai.com/v1",
            "model": "gpt-4",
            "context_window": 8192,
            "timeout_seconds": 30,
            "api_key": "sk-do-not-leak-this-value",
        },
        proposed_by="operator",
        reason="operator added a provider",
    )

    assert parked.arguments["api_key"] == "***"
    assert "sk-do-not-leak-this-value" not in str(instance.audit().records)
    assert "sk-do-not-leak-this-value" not in str(instance.pending())


def test_operator_config_secret_fields_are_masked() -> None:
    masked = mask_arguments(
        OPERATOR_CONFIG_WRITE, {"fields": {"USE_DDGS": "true", "TAVILY_API_KEY": "tvly-secret"}}
    )

    assert masked["fields"] == {"USE_DDGS": "true", "TAVILY_API_KEY": "***"}


def test_the_pending_store_is_bounded() -> None:
    instance = service(**{MEMORY_RECORD_FORGET: lambda args, op: {"ok": True}})

    for index in range(12):
        instance.propose(
            capability_id=MEMORY_RECORD_FORGET,
            arguments={"fact_id": f"fact-{index}", "expected_revision": 1},
            proposed_by="model",
            reason="model proposed forgetting",
        )

    assert len(instance.pending()) == 8


def test_operator_action_authorizes_executes_and_records_on_one_path() -> None:
    instance = service()

    result = instance.execute_operator_action(
        MEMORY_RECORD_FORGET, confirm_arguments(), lambda: {"forgotten": True}
    )

    assert result == {"forgotten": True}
    kinds = [record["kind"] for record in instance.audit(limit=100).records]
    assert kinds.count("action_proposal") == 1
    assert kinds.count("authorization_decision") == 1
    assert kinds.count("approval_record") == 1
    assert kinds.count("execution_result") == 1
    approval = next(r for r in instance.audit().records if r["kind"] == "approval_record")
    assert approval["record"]["decided_by"] == "operator_api"
    execution = next(r for r in instance.audit().records if r["kind"] == "execution_result")
    assert execution["record"]["result"] == {"forgotten": True}


def test_operator_action_records_a_failure_then_reraises_the_owning_error() -> None:
    instance = service()

    def explode() -> dict:
        raise ValueError("stale fact revision")

    with pytest.raises(ValueError, match="stale fact revision"):
        instance.execute_operator_action(MEMORY_RECORD_FORGET, confirm_arguments(), explode)

    execution = next(r for r in instance.audit().records if r["kind"] == "execution_result")
    assert execution["record"]["status"] == "failure"
    assert execution["record"]["error"] == "stale fact revision"


def test_operator_action_is_a_pass_through_when_no_capability_service_exists() -> None:
    calls: list[str] = []

    result = execute_operator_action(
        None, MEMORY_RECORD_FORGET, confirm_arguments(), lambda: calls.append("ran") or {"ok": True}
    )

    assert result == {"ok": True}
    assert calls == ["ran"]


def test_operator_action_does_not_gate_on_availability() -> None:
    # The owning service reports an unavailable dependency with more fidelity than a
    # descriptor explanation, so availability is recorded but never blocks.
    instance = service(CapabilityObservation(memory_service_present=False))

    result = instance.execute_operator_action(
        MEMORY_RECORD_FORGET, confirm_arguments(), lambda: {"forgotten": True}
    )

    assert result == {"forgotten": True}
    decision = next(
        r for r in instance.audit().records if r["kind"] == "authorization_decision"
    )
    assert decision["record"]["outcome"] == "denied"


def test_operator_action_still_refuses_an_unregistered_capability() -> None:
    instance = service()

    with pytest.raises(CapabilityServiceError) as excinfo:
        instance.execute_operator_action("no-such-capability", {}, lambda: {"ok": True})

    assert excinfo.value.status_code == 403


def test_concurrent_proposals_do_not_corrupt_the_audit() -> None:
    instance = service(**{MEMORY_RECORD_CONFIRM: lambda args, op: {"ok": True}})

    def propose(index: int) -> None:
        instance.propose(
            capability_id=MEMORY_RECORD_CONFIRM,
            arguments={"fact_id": f"fact-{index}", "expected_revision": 1},
            proposed_by="operator",
            reason="operator confirmed the fact",
        )

    threads = [threading.Thread(target=propose, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    executions = [r for r in instance.audit(limit=100).records if r["kind"] == "execution_result"]
    assert len(executions) == 8


def test_operator_config_keys_are_surfaced_for_discovery_but_never_gate_a_write() -> None:
    # The route reports unknown keys per-field in `rejected`; a schema refusal would
    # replace that richer contract with a blanket denial.
    instance = service(
        CapabilityObservation(operator_config_present=True, operator_config_keys=("USE_DDGS",))
    )

    entry = capability(instance.catalog(), OPERATOR_CONFIG_WRITE)
    assert "propertyNames" not in str(entry.input_schema)

    result = instance.execute_operator_action(
        OPERATOR_CONFIG_WRITE,
        {"fields": {"REDIS_HOST": "localhost"}},
        lambda: {"written": [], "rejected": [{"key": "REDIS_HOST", "reason": "not_allowlisted"}]},
    )

    assert result["rejected"][0]["reason"] == "not_allowlisted"
