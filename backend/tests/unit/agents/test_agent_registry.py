from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.app.actions.catalog import CapabilityObservation, build_descriptors
from backend.app.agents.registry import AgentRegistry
from backend.app.agents.schema import AgentProfile
from backend.app.extensions.catalog import ExtensionObservation, build_extension_descriptors


def _profile(**overrides: object) -> AgentProfile:
    values: dict = {
        "profile_id": "test-agent",
        "display_name": "Test Agent",
        "purpose": "A test agent for validation",
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


def _valid_yaml_dict(**overrides: object) -> dict:
    values: dict = {
        "profile_id": "yaml-agent",
        "display_name": "YAML Agent",
        "purpose": "Loaded from YAML",
        "instructions": "Test instructions.",
        "invocation_modes": ["direct"],
        "capability_ids": [],
        "memory_scope": "working",
        "approval_class": "standard",
        "timeout_ms": 30000,
        "cancellable": True,
        "output_contract": {"type": "object"},
        "provider_model_policy": {},
    }
    values.update(overrides)
    return values


def _write_yaml(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as stream:
        yaml.dump(data, stream)


def _write_agent(config_dir: Path, profile_id: str, **overrides: object) -> None:
    agents_dir = config_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    data = _valid_yaml_dict(profile_id=profile_id, **overrides)
    _write_yaml(agents_dir / f"{profile_id}.yaml", data)


# --- AgentRegistry loads profiles ---


def test_registry_loads_profiles_from_config_directory(tmp_path: Path) -> None:
    _write_agent(tmp_path, "alpha-agent")
    _write_agent(tmp_path, "beta-agent")

    registry = AgentRegistry(config_dir=tmp_path)
    profiles = registry.profiles()

    assert len(profiles) == 2
    assert profiles[0].profile_id == "alpha-agent"
    assert profiles[1].profile_id == "beta-agent"


def test_registry_returns_empty_list_when_no_profiles_exist(tmp_path: Path) -> None:
    registry = AgentRegistry(config_dir=tmp_path)
    assert registry.profiles() == []


def test_registry_returns_empty_list_with_no_config_dir() -> None:
    registry = AgentRegistry()
    assert registry.profiles() == []


# --- AgentRegistry.get() ---


def test_get_returns_correct_profile_by_id(tmp_path: Path) -> None:
    _write_agent(tmp_path, "alpha-agent")
    _write_agent(tmp_path, "beta-agent")

    registry = AgentRegistry(config_dir=tmp_path)
    profile = registry.get("beta-agent")

    assert profile is not None
    assert profile.profile_id == "beta-agent"


def test_get_returns_none_for_unknown_id(tmp_path: Path) -> None:
    _write_agent(tmp_path, "alpha-agent")

    registry = AgentRegistry(config_dir=tmp_path)
    assert registry.get("nonexistent") is None


# --- to_extension_records() ---


def test_to_extension_records_returns_correct_tuples(tmp_path: Path) -> None:
    _write_agent(tmp_path, "my-agent", display_name="My Agent", purpose="Does things")

    registry = AgentRegistry(config_dir=tmp_path)
    records = registry.to_extension_records()

    assert len(records) == 1
    assert records[0] == (
        "my-agent",
        "My Agent",
        "Does things",
        "config/agents/my-agent.yaml",
    )


# --- to_capability_records() ---


def test_to_capability_records_returns_correct_tuples(tmp_path: Path) -> None:
    _write_agent(
        tmp_path,
        "my-agent",
        display_name="My Agent",
        approval_class="standard",
        timeout_ms=30000,
        cancellable=True,
    )

    registry = AgentRegistry(config_dir=tmp_path)
    records = registry.to_capability_records()

    assert len(records) == 1
    cap_id, profile_id, display_name, effect, auth, timeout, cancellable = records[0]
    assert cap_id == "agent-invoke-my-agent"
    assert profile_id == "my-agent"
    assert display_name == "My Agent"
    assert effect == "local_write"
    assert auth == "requires_approval"
    assert timeout == 30000
    assert cancellable is True


def test_capability_records_map_approval_none_to_local_read_and_allow(tmp_path: Path) -> None:
    _write_agent(tmp_path, "read-only", approval_class="none")

    registry = AgentRegistry(config_dir=tmp_path)
    records = registry.to_capability_records()

    _, _, _, effect, auth, _, _ = records[0]
    assert effect == "local_read"
    assert auth == "allow"


def test_capability_records_map_approval_strict_to_privileged_and_requires_approval(
    tmp_path: Path,
) -> None:
    _write_agent(tmp_path, "strict-agent", approval_class="strict")

    registry = AgentRegistry(config_dir=tmp_path)
    records = registry.to_capability_records()

    _, _, _, effect, auth, _, _ = records[0]
    assert effect == "privileged_execution"
    assert auth == "requires_approval"


# --- refresh() ---


def test_refresh_reloads_profiles(tmp_path: Path) -> None:
    _write_agent(tmp_path, "alpha-agent")

    registry = AgentRegistry(config_dir=tmp_path)
    assert len(registry.profiles()) == 1

    _write_agent(tmp_path, "beta-agent")
    # Still cached
    assert len(registry.profiles()) == 1

    registry.refresh()
    assert len(registry.profiles()) == 2


# --- Integration: agent records in ExtensionObservation ---


def test_agent_records_appear_in_extension_observation(tmp_path: Path) -> None:
    _write_agent(tmp_path, "helper-agent", display_name="Helper", purpose="Helps")

    registry = AgentRegistry(config_dir=tmp_path)
    observation = ExtensionObservation(
        agents=tuple(registry.to_extension_records()),
    )
    descriptors = build_extension_descriptors(observation)

    agent_descriptors = [d for d in descriptors if d.family == "agent"]
    assert len(agent_descriptors) == 1
    assert agent_descriptors[0].local_id == "helper-agent"
    assert agent_descriptors[0].display_name == "Helper"
    assert agent_descriptors[0].provenance == "config/agents"
    assert agent_descriptors[0].trust == "application"
    assert agent_descriptors[0].metadata_claims == {"purpose": {"value": "Helps", "trusted": False}}


# --- Integration: agent capability descriptors in build_descriptors ---


def test_agent_capability_descriptors_appear_in_build_descriptors(tmp_path: Path) -> None:
    _write_agent(
        tmp_path,
        "worker-agent",
        display_name="Worker",
        approval_class="standard",
        timeout_ms=45000,
        cancellable=True,
    )

    registry = AgentRegistry(config_dir=tmp_path)
    observation = CapabilityObservation(
        agents=tuple(registry.to_capability_records()),
    )
    descriptors = build_descriptors(observation)

    agent_caps = [d for d in descriptors if d.capability_id == "agent-invoke-worker-agent"]
    assert len(agent_caps) == 1
    cap = agent_caps[0]
    assert cap.effect_class == "local_write"
    assert cap.authorization_rule == "requires_approval"
    assert cap.readiness == "ready"
    assert cap.availability == "available"
    assert cap.timeout_policy == {"timeout_ms": 45000}
    assert cap.cancellation_policy == {"cancellable": True}
    assert cap.approval_mode == "turn_boundary"
    assert cap.metadata_claims == {"agent_id": {"value": "worker-agent", "trusted": False}}
    assert cap.execution_owner == "backend.app.agents.invocation"
