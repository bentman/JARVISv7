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
