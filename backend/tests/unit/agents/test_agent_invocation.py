from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from backend.app.agents.invocation import AgentInvocationResult, AgentInvoker
from backend.app.agents.registry import AgentRegistry
from backend.app.agents.schema import AgentProfile


def _profile(**overrides: Any) -> AgentProfile:
    values: dict[str, Any] = {
        "profile_id": "test-agent",
        "display_name": "Test Agent",
        "purpose": "A test agent",
        "instructions": "Follow test conventions.",
        "invocation_modes": ("direct",),
        "capability_ids": (),
        "memory_scope": "working",
        "approval_class": "standard",
        "timeout_ms": 30000,
        "cancellable": True,
        "output_contract": {"type": "object"},
        "provider_model_policy": {},
    }
    values.update(overrides)
    return AgentProfile(**values)


# --- AgentInvocationResult ---


def test_invocation_result_creation() -> None:
    result = AgentInvocationResult(
        agent_id="test-agent",
        status="success",
        output={"response": "hello"},
        turn_id="turn-1",
        session_id="session-1",
    )
    assert result.agent_id == "test-agent"
    assert result.status == "success"
    assert result.output == {"response": "hello"}
    assert result.turn_id == "turn-1"
    assert result.session_id == "session-1"
    assert result.error is None


def test_invocation_result_to_dict() -> None:
    result = AgentInvocationResult(
        agent_id="test-agent",
        status="failure",
        output={},
        turn_id="turn-1",
        session_id="session-1",
        error="something broke",
    )
    d = result.to_dict()
    assert d == {
        "agent_id": "test-agent",
        "status": "failure",
        "output": {},
        "turn_id": "turn-1",
        "session_id": "session-1",
        "error": "something broke",
    }


def test_invocation_result_with_error() -> None:
    result = AgentInvocationResult(
        agent_id="test-agent",
        status="failure",
        output={},
        turn_id="turn-1",
        session_id="session-1",
        error="timeout",
    )
    assert result.error == "timeout"


# --- AgentInvoker.invoke ---


@pytest.mark.parametrize("mode", ["direct", "as_tool", "router_selected", "handoff"])
def test_invoke_runs_a_declared_mode_on_the_engine(mode: str) -> None:
    profile = _profile(invocation_modes=(mode,))
    registry = AgentRegistry()
    registry._profiles = [profile]
    expected_result = AgentInvocationResult(
        agent_id="test-agent",
        status="success",
        output={"response": "agent output"},
        turn_id="turn-1",
        session_id="session-1",
    )
    mock_engine = MagicMock()
    mock_engine.run_agent.return_value = expected_result

    result = AgentInvoker(registry).invoke("test-agent", "do something", mode, lambda: mock_engine)

    assert result == expected_result
    mock_engine.run_agent.assert_called_once_with(
        profile, "do something", mode=mode, operation=None
    )


def test_invoke_refuses_a_mode_the_profile_does_not_declare() -> None:
    registry = AgentRegistry()
    registry._profiles = [_profile(invocation_modes=("as_tool",))]

    with pytest.raises(ValueError, match="does not support direct invocation"):
        AgentInvoker(registry).invoke("test-agent", "prompt", "direct", lambda: None)


def test_invoke_rejects_unknown_profile_id() -> None:
    registry = AgentRegistry()
    registry._profiles = []

    with pytest.raises(ValueError, match="unknown agent profile"):
        AgentInvoker(registry).invoke("nonexistent", "prompt", "direct", lambda: None)


# --- POST /agents/invoke ---


def _invoke_client(
    result: dict[str, Any],
    modes: tuple[str, ...] = ("direct",),
    runtime: dict[str, Any] | None = None,
):
    from backend.app.actions.catalog import CapabilityObservation
    from backend.app.api.routes.agents import router
    from backend.app.services.capability_service import (
        CapabilityService,
        build_agent_handlers,
    )
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    profile = _profile(
        profile_id="summarizer", approval_class="none", invocation_modes=modes,
        runtime=runtime or {"kind": "internal"},
    )
    registry = AgentRegistry()
    registry._profiles = [profile]
    engine = MagicMock()
    engine.in_turn_mode.return_value = None
    engine.run_agent.return_value = AgentInvocationResult(**result)
    service = CapabilityService(
        observe=lambda: CapabilityObservation(
            agents=(tuple(registry.to_capability_records()[0]),)  # type: ignore[arg-type]
        )
    )
    service.bind_handler_provider(
        lambda: build_agent_handlers(
            agent_registry_provider=lambda: registry, engine_provider=lambda: engine
        )
    )
    app = FastAPI()
    app.include_router(router)
    app.state.jarvis_state = MagicMock(agent_registry=registry, capability_service=service)
    return TestClient(app)


def test_invoke_route_executes_the_bound_agent_capability() -> None:
    client = _invoke_client(
        {
            "agent_id": "summarizer",
            "status": "success",
            "output": {"response": "a summary"},
            "turn_id": "turn-9",
            "session_id": "session-9",
        }
    )

    response = client.post("/agents/invoke", json={"profile_id": "summarizer", "prompt": "notes"})

    assert response.status_code == 200
    assert response.json() == {
        "agent_id": "summarizer",
        "status": "success",
        "output": {"response": "a summary"},
        "turn_id": "turn-9",
        "session_id": "session-9",
        "error": None,
    }


def test_invoke_route_reports_a_failed_agent_run_as_a_failure() -> None:
    # The engine reports a failed run in its result instead of raising, so the capability
    # execution succeeds; the route must not read that as the agent's outcome.
    client = _invoke_client(
        {
            "agent_id": "summarizer",
            "status": "failure",
            "output": {},
            "turn_id": "turn-9",
            "session_id": "session-9",
            "error": "provider unavailable",
        }
    )

    body = client.post("/agents/invoke", json={"profile_id": "summarizer", "prompt": "notes"}).json()

    assert (body["status"], body["error"]) == ("failure", "provider unavailable")


def test_invoke_route_reports_why_a_denied_invocation_never_ran() -> None:
    client = _invoke_client(
        {"agent_id": "summarizer", "status": "success", "output": {}, "turn_id": "t", "session_id": "s"},
        modes=("handoff",),
        runtime={"kind": "acp", "adapter_id": "coder"},
    )

    body = client.post("/agents/invoke", json={"profile_id": "summarizer", "prompt": "notes"}).json()

    assert body["status"] == "denied"
    assert "declares no invocation mode its runtime executes" in body["error"]


def test_tools_route_lists_what_an_agent_may_be_allowed_to_use() -> None:
    from types import SimpleNamespace

    from backend.app.api.routes.agents import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    views = [
        SimpleNamespace(capability_id="ext-read", authorization_rule="allow", availability="available", readiness="ready"),
        SimpleNamespace(capability_id="ext-write", authorization_rule="requires_approval", availability="disabled", readiness="ready"),
        SimpleNamespace(capability_id="ext-blocked", authorization_rule="deny", availability="available", readiness="ready"),
    ]
    catalog = [
        {"capability_id": item.capability_id, "extension_id": "mcp:notes", "name": f"tool:{item.capability_id}"}
        for item in views
    ]
    app = FastAPI()
    app.include_router(router)
    app.state.jarvis_state = SimpleNamespace(
        capability_service=SimpleNamespace(catalog=lambda: SimpleNamespace(capabilities=views)),
        extension_runtime=SimpleNamespace(tool_catalog=lambda: catalog),
    )

    tools = TestClient(app).get("/agents/tools").json()["tools"]

    assert tools == [
        {"capability_id": "ext-read", "label": "mcp:notes tool:ext-read", "needs_approval": False, "available": True},
        {"capability_id": "ext-write", "label": "mcp:notes tool:ext-write", "needs_approval": True, "available": False},
    ]

