from __future__ import annotations

from pathlib import Path

import pytest
from backend.app.agents.policy import AgentPolicy, load_agent_policy


def test_default_agent_policy_is_disabled_read_only() -> None:
    policy = AgentPolicy()

    assert policy.enabled is False
    assert policy.read_only is True
    assert policy.allowed_roles == []
    assert policy.allowed_tools == []


def test_load_agent_policy_from_default_config() -> None:
    policy = load_agent_policy()

    assert policy.enabled is False
    assert policy.read_only is True
    assert policy.allowed_roles == ["planner", "executor", "critic", "curator", "learner"]
    assert policy.allowed_tools == []


def test_load_agent_policy_accepts_enabled_test_policy(tmp_path: Path) -> None:
    path = tmp_path / "policies.yaml"
    path.write_text(
        "agents:\n"
        "  enabled: true\n"
        "  read_only: false\n"
        "  reason: test enabled\n"
        "  allowed_roles: [planner]\n"
        "  allowed_tools: [time]\n",
        encoding="utf-8",
    )

    policy = load_agent_policy(path)

    assert policy.enabled is True
    assert policy.read_only is False
    assert policy.reason == "test enabled"
    assert policy.allowed_roles == ["planner"]
    assert policy.allowed_tools == ["time"]


def test_load_agent_policy_rejects_non_mapping_agents_section(tmp_path: Path) -> None:
    path = tmp_path / "policies.yaml"
    path.write_text("agents: false\n", encoding="utf-8")

    with pytest.raises(ValueError, match="agents policy"):
        load_agent_policy(path)
