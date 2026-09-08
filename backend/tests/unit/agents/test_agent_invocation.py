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


# --- AgentInvoker.invoke_direct ---


def test_invoke_direct_with_valid_profile() -> None:
    profile = _profile(invocation_modes=("direct",))
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

    invoker = AgentInvoker(registry)
    result = invoker.invoke_direct("test-agent", "do something", lambda: mock_engine)

    assert result == expected_result
    mock_engine.run_agent.assert_called_once_with(profile, "do something", mode="direct")


def test_invoke_direct_rejects_unknown_profile_id() -> None:
    registry = AgentRegistry()
    registry._profiles = []

    invoker = AgentInvoker(registry)
    with pytest.raises(ValueError, match="unknown agent profile"):
        invoker.invoke_direct("nonexistent", "prompt", lambda: None)


def test_invoke_direct_rejects_profile_without_direct_mode() -> None:
    profile = _profile(invocation_modes=("as_tool",))
    registry = AgentRegistry()
    registry._profiles = [profile]

    invoker = AgentInvoker(registry)
    with pytest.raises(ValueError, match="does not support direct invocation"):
        invoker.invoke_direct("test-agent", "prompt", lambda: None)


# --- AgentInvoker.invoke_as_tool ---


def test_invoke_as_tool_with_valid_profile() -> None:
    profile = _profile(invocation_modes=("as_tool",))
    registry = AgentRegistry()
    registry._profiles = [profile]

    expected_result = AgentInvocationResult(
        agent_id="test-agent",
        status="success",
        output={"response": "tool output"},
        turn_id="turn-2",
        session_id="session-1",
    )
    mock_engine = MagicMock()
    mock_engine.run_agent.return_value = expected_result

    invoker = AgentInvoker(registry)
    result = invoker.invoke_as_tool("test-agent", "analyze this", lambda: mock_engine)

    assert result == expected_result
    mock_engine.run_agent.assert_called_once_with(profile, "analyze this", mode="as_tool")


def test_invoke_as_tool_rejects_profile_without_as_tool_mode() -> None:
    profile = _profile(invocation_modes=("direct",))
    registry = AgentRegistry()
    registry._profiles = [profile]

    invoker = AgentInvoker(registry)
    with pytest.raises(ValueError, match="does not support as_tool invocation"):
        invoker.invoke_as_tool("test-agent", "prompt", lambda: None)


def test_invoke_as_tool_rejects_unknown_profile_id() -> None:
    registry = AgentRegistry()
    registry._profiles = []

    invoker = AgentInvoker(registry)
    with pytest.raises(ValueError, match="unknown agent profile"):
        invoker.invoke_as_tool("nonexistent", "prompt", lambda: None)


# --- POST /agents/invoke ---


def _invoke_client(result: dict[str, Any], modes: tuple[str, ...] = ("direct",)):
    from backend.app.actions.catalog import CapabilityObservation
    from backend.app.api.routes.agents import router
    from backend.app.services.capability_service import (
        CapabilityService,
        build_agent_handlers,
    )
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    profile = _profile(profile_id="summarizer", approval_class="none", invocation_modes=modes)
    registry = AgentRegistry()
    registry._profiles = [profile]
    engine = MagicMock()
    engine.run_agent.return_value = AgentInvocationResult(**result)
    service = CapabilityService(
        observe=lambda: CapabilityObservation(
            agents=(tuple(registry.to_capability_records()[0]),)
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
        modes=("as_tool",),
    )

    body = client.post("/agents/invoke", json={"profile_id": "summarizer", "prompt": "notes"}).json()

    assert body["status"] == "denied"
    assert "'direct' invocation mode" in body["error"]
