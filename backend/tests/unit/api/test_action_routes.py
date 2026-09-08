from __future__ import annotations

import pytest
from backend.app.actions.boundaries import ActionOperation
from backend.app.actions.catalog import (
    MEMORY_RECORD_CONFIRM,
    MEMORY_RECORD_FORGET,
    OPERATOR_CONFIG_WRITE,
    PROVIDER_CONNECTIVITY_TEST,
    PROVIDER_PROFILE_WRITE,
    SEARCH_PUBLIC_WEB,
    CapabilityObservation,
)
from backend.app.api.dependencies import get_capability_service
from backend.app.api.routes.actions import router
from backend.app.services.capability_service import CapabilityService
from fastapi import FastAPI
from fastapi.testclient import TestClient

READY = CapabilityObservation(
    search_providers=(("ddgs", True), ("searxng", True)),
    memory_service_present=True,
    memory_curation_present=True,
    provider_store_present=True,
    operator_config_present=True,
    operator_config_keys=("USE_DDGS",),
)


def _client(service: object) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_capability_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def _service(observation: CapabilityObservation = READY, **handlers) -> CapabilityService:
    return CapabilityService(observe=lambda: observation, handlers=handlers)


def _forget_payload(**overrides) -> dict:
    payload = {
        "capability_id": MEMORY_RECORD_FORGET,
        "arguments": {"fact_id": "fact-1", "expected_revision": 1},
        "reason": "the model proposed forgetting a fact",
    }
    payload.update(overrides)
    return payload


def test_capability_catalog_reports_live_availability_and_never_privileged_execution() -> None:
    client = _client(_service())

    response = client.get("/actions/capabilities")

    assert response.status_code == 200
    capabilities = response.json()["capabilities"]
    assert capabilities
    assert not any(item["effect_class"] == "privileged_execution" for item in capabilities)
    assert {item["effect_class"] for item in capabilities} == {
        "external_read",
        "local_write",
        "destructive_action",
    }
    search = next(item for item in capabilities if item["capability_id"] == SEARCH_PUBLIC_WEB)
    assert (search["availability"], search["approval_mode"]) == ("available", "turn_boundary")
    # Local config and health-check reads run directly; the catalog serves no registration problems.
    rules = {item["capability_id"]: item["authorization_rule"] for item in capabilities}
    assert rules[OPERATOR_CONFIG_WRITE] == "allow"
    assert rules[PROVIDER_CONNECTIVITY_TEST] == "allow"
    assert rules[MEMORY_RECORD_FORGET] == "requires_approval"
    assert response.json()["problems"] == []


def test_catalog_explains_a_disabled_capability_instead_of_hiding_it() -> None:
    client = _client(_service(CapabilityObservation()))

    capabilities = client.get("/actions/capabilities").json()["capabilities"]

    search = next(item for item in capabilities if item["capability_id"] == SEARCH_PUBLIC_WEB)
    assert search["availability"] == "disabled"
    assert "Enable DDGS, SearXNG, or Tavily" in search["unavailable_explanation"]


def test_turn_boundary_capabilities_cannot_be_proposed_through_the_api() -> None:
    client = _client(_service())

    response = client.post(
        "/actions/propose",
        json={
            "capability_id": SEARCH_PUBLIC_WEB,
            "arguments": {"mode": "search", "topic": "weather", "queries": ["weather"]},
            "reason": "operator asked for a search",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "turn_boundary_capability"


def test_an_approval_required_proposal_parks_without_executing() -> None:
    calls: list[dict] = []
    client = _client(
        _service(**{MEMORY_RECORD_FORGET: lambda args, op: calls.append(args) or {"ok": True}})
    )

    response = client.post("/actions/propose", json=_forget_payload(proposed_by="model"))

    assert response.status_code == 200
    body = response.json()
    assert (body["outcome"], body["status"]) == ("approval_required", "awaiting_approval")
    assert body["execution"] is None
    assert body["approval_id"] and body["expires_at"]
    assert calls == []

    pending = client.get("/actions/pending").json()["pending"]
    assert [item["proposal_id"] for item in pending] == [body["proposal_id"]]


def test_approval_executes_once_and_a_second_decision_is_refused() -> None:
    calls: list[dict] = []
    client = _client(
        _service(**{MEMORY_RECORD_FORGET: lambda args, op: calls.append(args) or {"ok": True}})
    )
    proposal_id = client.post("/actions/propose", json=_forget_payload()).json()["proposal_id"]

    approved = client.post(f"/actions/{proposal_id}/decision", json={"outcome": "approved"})

    assert approved.status_code == 200
    assert approved.json()["status"] == "success"
    assert approved.json()["execution"]["result"] == {"ok": True}
    assert len(calls) == 1

    repeated = client.post(f"/actions/{proposal_id}/decision", json={"outcome": "approved"})
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["error"] in {"already_decided", "unknown_proposal"}
    assert len(calls) == 1


def test_a_denied_decision_never_executes() -> None:
    calls: list[dict] = []
    client = _client(
        _service(**{MEMORY_RECORD_FORGET: lambda args, op: calls.append(args) or {"ok": True}})
    )
    proposal_id = client.post("/actions/propose", json=_forget_payload()).json()["proposal_id"]

    response = client.post(
        f"/actions/{proposal_id}/decision", json={"outcome": "denied", "reason": "not now"}
    )

    assert response.json()["status"] == "denied"
    assert calls == []
    assert client.get("/actions/pending").json()["pending"] == []


def test_an_unavailable_capability_is_denied_with_the_operator_facing_explanation() -> None:
    calls: list[dict] = []
    client = _client(
        _service(
            CapabilityObservation(memory_service_present=False),
            **{MEMORY_RECORD_FORGET: lambda args, op: calls.append(args) or {"ok": True}},
        )
    )

    body = client.post("/actions/propose", json=_forget_payload()).json()

    assert body["outcome"] == "denied"
    assert "Memory service is unavailable" in body["reason"]
    assert calls == []


def test_a_cancelled_proposal_reports_cancellation_once() -> None:
    client = _client(_service(**{MEMORY_RECORD_FORGET: lambda args, op: {"ok": True}}))
    proposal_id = client.post("/actions/propose", json=_forget_payload()).json()["proposal_id"]

    first = client.post(f"/actions/{proposal_id}/cancel")
    second = client.post(f"/actions/{proposal_id}/cancel")

    assert first.json() == {"proposal_id": proposal_id, "cancelled": True}
    assert second.json()["cancelled"] is False


def test_unknown_proposals_and_capabilities_are_reported_not_guessed() -> None:
    client = _client(_service())

    assert client.get("/actions/does-not-exist").status_code == 404
    assert (
        client.post(
            "/actions/propose",
            json={"capability_id": "no-such-capability", "arguments": {}, "reason": "why not"},
        ).status_code
        == 404
    )


def test_action_requests_reject_unknown_fields() -> None:
    client = _client(_service())

    response = client.post("/actions/propose", json=_forget_payload(unexpected="value"))

    assert response.status_code == 422


def test_secret_arguments_never_appear_in_responses_or_the_audit() -> None:
    client = _client(_service(**{PROVIDER_PROFILE_WRITE: lambda args, op: {"ok": True}}))

    parked = client.post(
        "/actions/propose",
        json={
            "capability_id": PROVIDER_PROFILE_WRITE,
            "arguments": {
                "name": "cloud",
                "kind": "openai",
                "endpoint": "https://api.openai.com/v1",
                "model": "gpt-4",
                "context_window": 8192,
                "timeout_seconds": 30,
                "api_key": "sk-do-not-leak-this-value",
            },
            "reason": "operator added a provider profile",
        },
    )

    assert "sk-do-not-leak-this-value" not in parked.text
    assert parked.json()["arguments"]["api_key"] == "***"
    assert "sk-do-not-leak-this-value" not in client.get("/actions/pending").text
    assert "sk-do-not-leak-this-value" not in client.get("/actions/audit").text


def test_handler_failures_return_a_recorded_result_without_leaking_internals() -> None:
    def handler(args: dict, op: ActionOperation) -> dict:
        raise OSError("C:/private/memory.sqlite is locked by internal-vectorizer")

    client = _client(_service(**{MEMORY_RECORD_CONFIRM: handler}))

    response = client.post(
        "/actions/propose",
        json={
            "capability_id": MEMORY_RECORD_CONFIRM,
            "arguments": {"fact_id": "fact-1", "expected_revision": 1},
            "reason": "operator confirmed the fact",
        },
    )

    assert response.status_code == 200
    assert response.json()["execution"]["error"] == "capability execution failed"
    for prohibited in ("C:/private", "internal-vectorizer", "sqlite", "Traceback"):
        assert prohibited not in response.text


def test_unexpected_service_failures_return_a_sanitized_500() -> None:
    class _ExplodingService:
        def catalog(self):
            raise RuntimeError("C:/private/state.sqlite exploded")

    response = _client(_ExplodingService()).get("/actions/capabilities")

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "error": "internal_error",
        "message": "action operation failed",
    }
    assert "C:/private" not in response.text


def test_the_audit_limit_is_bounded() -> None:
    client = _client(_service())

    assert client.get("/actions/audit", params={"limit": 0}).status_code == 422
    assert client.get("/actions/audit", params={"limit": 1000}).status_code == 422
    assert client.get("/actions/audit", params={"limit": 5}).status_code == 200


@pytest.mark.parametrize("path", ["/actions/capabilities", "/actions/pending", "/actions/audit"])
def test_routes_report_unavailability_rather_than_failing_opaquely(path: str) -> None:
    from backend.app.api.app import ApiState  # noqa: F401

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(path)

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "error": "unavailable",
        "message": "capability service is unavailable",
    }
