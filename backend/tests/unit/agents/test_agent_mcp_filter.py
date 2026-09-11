"""Tests for backend.app.agents.mcp_filter."""

from __future__ import annotations

import pytest
from backend.app.agents.mcp_filter import AgentMcpPolicy, build_agent_mcp_policy
from backend.app.agents.schema import AgentProfile
from backend.app.extensions.mcp import McpConnectionDefinition


def _profile(**overrides) -> AgentProfile:
    values = {
        "profile_id": "test-agent",
        "display_name": "Test Agent",
        "purpose": "Testing",
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
    return AgentProfile(**values)  # type: ignore[arg-type]


def _stdio_connection(connection_id: str, **overrides) -> McpConnectionDefinition:
    values = {
        "connection_id": connection_id,
        "transport": "stdio",
        "command": ("node", "server.js"),
        "process": {
            "subprocess": True,
            "working_root": "data",
            "argv_allowlist": ["node"],
            "env_passthrough": ["PATH"],
        },
    }
    values.update(overrides)
    return McpConnectionDefinition(**values)  # type: ignore[arg-type]


# --- AgentMcpPolicy creation ---


def test_policy_creation_valid() -> None:
    policy = AgentMcpPolicy(
        agent_id="agent-1",
        allowed_connections=("conn-1", "conn-2"),
        allowed_tools=("tool-a",),
    )
    assert policy.agent_id == "agent-1"
    assert policy.allowed_connections == ("conn-1", "conn-2")
    assert policy.allowed_tools == ("tool-a",)


def test_policy_rejects_empty_agent_id() -> None:
    with pytest.raises(ValueError, match="agent_id must be a non-empty"):
        AgentMcpPolicy(agent_id="", allowed_connections=("conn-1",))


def test_policy_rejects_empty_string_in_connections() -> None:
    with pytest.raises(ValueError, match="allowed_connections entries must be non-empty"):
        AgentMcpPolicy(agent_id="a", allowed_connections=("conn-1", ""))


def test_policy_rejects_empty_string_in_tools() -> None:
    with pytest.raises(ValueError, match="allowed_tools entries must be non-empty"):
        AgentMcpPolicy(agent_id="a", allowed_connections=("c",), allowed_tools=("",))


def test_policy_rejects_empty_string_in_resources() -> None:
    with pytest.raises(ValueError, match="allowed_resources entries must be non-empty"):
        AgentMcpPolicy(agent_id="a", allowed_connections=("c",), allowed_resources=("",))


def test_policy_rejects_empty_string_in_prompts() -> None:
    with pytest.raises(ValueError, match="allowed_prompts entries must be non-empty"):
        AgentMcpPolicy(agent_id="a", allowed_connections=("c",), allowed_prompts=("",))


# --- can_access ---


def test_can_access_allowed_connection() -> None:
    policy = AgentMcpPolicy(agent_id="a", allowed_connections=("conn-1", "conn-2"))
    assert policy.can_access("conn-1") is True


def test_can_access_disallowed_connection() -> None:
    policy = AgentMcpPolicy(agent_id="a", allowed_connections=("conn-1",))
    assert policy.can_access("conn-2") is False


def test_can_access_empty_connections() -> None:
    policy = AgentMcpPolicy(agent_id="a", allowed_connections=())
    assert policy.can_access("anything") is False


# --- filter_tools ---


def test_filter_tools_returns_empty_when_connection_not_allowed() -> None:
    policy = AgentMcpPolicy(agent_id="a", allowed_connections=("conn-1",))
    tools = [{"name": "tool-a"}, {"name": "tool-b"}]

    result = policy.filter_tools("conn-2", tools)

    assert result == []


def test_filter_tools_intersects_with_allowed_tools() -> None:
    policy = AgentMcpPolicy(
        agent_id="a",
        allowed_connections=("conn-1",),
        allowed_tools=("tool-a",),
    )
    tools = [{"name": "tool-a"}, {"name": "tool-b"}, {"name": "tool-c"}]

    result = policy.filter_tools("conn-1", tools)

    assert result == [{"name": "tool-a"}]


def test_filter_tools_passes_through_when_allowed_tools_empty() -> None:
    policy = AgentMcpPolicy(agent_id="a", allowed_connections=("conn-1",))
    tools = [{"name": "tool-a"}, {"name": "tool-b"}]

    result = policy.filter_tools("conn-1", tools)

    assert result == [{"name": "tool-a"}, {"name": "tool-b"}]


def test_filter_tools_returns_new_list() -> None:
    policy = AgentMcpPolicy(agent_id="a", allowed_connections=("conn-1",))
    tools = [{"name": "tool-a"}]

    result = policy.filter_tools("conn-1", tools)

    assert result is not tools


# --- filter_resources ---


def test_filter_resources_returns_empty_when_connection_not_allowed() -> None:
    policy = AgentMcpPolicy(agent_id="a", allowed_connections=("conn-1",))
    resources = [{"uri": "file:///a.txt"}]

    assert policy.filter_resources("conn-2", resources) == []


def test_filter_resources_intersects_with_allowed_resources() -> None:
    policy = AgentMcpPolicy(
        agent_id="a",
        allowed_connections=("conn-1",),
        allowed_resources=("file:///a.txt",),
    )
    resources = [{"uri": "file:///a.txt"}, {"uri": "file:///b.txt"}]

    result = policy.filter_resources("conn-1", resources)

    assert result == [{"uri": "file:///a.txt"}]


def test_filter_resources_passes_through_when_allowed_resources_empty() -> None:
    policy = AgentMcpPolicy(agent_id="a", allowed_connections=("conn-1",))
    resources = [{"uri": "file:///a.txt"}, {"uri": "file:///b.txt"}]

    result = policy.filter_resources("conn-1", resources)

    assert result == resources


# --- filter_prompts ---


def test_filter_prompts_returns_empty_when_connection_not_allowed() -> None:
    policy = AgentMcpPolicy(agent_id="a", allowed_connections=("conn-1",))
    prompts = [{"name": "prompt-a"}]

    assert policy.filter_prompts("conn-2", prompts) == []


def test_filter_prompts_intersects_with_allowed_prompts() -> None:
    policy = AgentMcpPolicy(
        agent_id="a",
        allowed_connections=("conn-1",),
        allowed_prompts=("prompt-a",),
    )
    prompts = [{"name": "prompt-a"}, {"name": "prompt-b"}]

    result = policy.filter_prompts("conn-1", prompts)

    assert result == [{"name": "prompt-a"}]


def test_filter_prompts_passes_through_when_allowed_prompts_empty() -> None:
    policy = AgentMcpPolicy(agent_id="a", allowed_connections=("conn-1",))
    prompts = [{"name": "prompt-a"}, {"name": "prompt-b"}]

    result = policy.filter_prompts("conn-1", prompts)

    assert result == prompts


# --- build_agent_mcp_policy ---


def test_build_policy_extracts_mcp_connection_ids() -> None:
    profile = _profile(capability_ids=("read-file", "mcp-search", "mcp-weather"))

    policy = build_agent_mcp_policy(profile)

    assert policy is not None
    assert policy.agent_id == "test-agent"
    assert policy.allowed_connections == ("search", "weather")


def test_build_policy_returns_none_when_no_mcp_capabilities() -> None:
    profile = _profile(capability_ids=("read-file", "web-search"))

    assert build_agent_mcp_policy(profile) is None


def test_build_policy_returns_none_for_empty_capabilities() -> None:
    profile = _profile(capability_ids=())

    assert build_agent_mcp_policy(profile) is None


def test_build_policy_filters_by_available_connections() -> None:
    profile = _profile(capability_ids=("mcp-search", "mcp-missing"))
    connections = [_stdio_connection("search")]

    policy = build_agent_mcp_policy(profile, connections)

    assert policy is not None
    assert policy.allowed_connections == ("search",)


def test_build_policy_returns_none_when_no_connections_match() -> None:
    profile = _profile(capability_ids=("mcp-search",))
    connections = [_stdio_connection("other")]

    assert build_agent_mcp_policy(profile, connections) is None


def test_build_policy_with_no_connections_arg_uses_all_capability_ids() -> None:
    profile = _profile(capability_ids=("mcp-search", "mcp-tools"))

    policy = build_agent_mcp_policy(profile, None)

    assert policy is not None
    assert policy.allowed_connections == ("search", "tools")
