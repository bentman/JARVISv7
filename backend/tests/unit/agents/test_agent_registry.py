from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from backend.app.actions.catalog import CapabilityObservation, build_descriptors
from backend.app.agents.registry import AgentProfileError, AgentRegistry
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
        "application",
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
    (
        cap_id, profile_id, display_name, effect, auth, timeout, cancellable, unsupported,
        availability, process,
    ) = records[0]
    assert cap_id == "agent-invoke-my-agent"
    assert profile_id == "my-agent"
    assert display_name == "My Agent"
    assert effect == "local_write"
    assert auth == "requires_approval"
    assert timeout == 30000
    assert cancellable is True
    assert unsupported == ""
    assert availability == "available"
    assert process == {}


def test_capability_records_map_approval_none_to_local_read_and_allow(tmp_path: Path) -> None:
    _write_agent(tmp_path, "read-only", approval_class="none")

    registry = AgentRegistry(config_dir=tmp_path)
    records = registry.to_capability_records()

    _, _, _, effect, auth, *_ = records[0]
    assert effect == "local_read"
    assert auth == "allow"


def test_capability_records_map_approval_strict_to_an_approval_gated_local_write(
    tmp_path: Path,
) -> None:
    _write_agent(tmp_path, "strict-agent", approval_class="strict")

    registry = AgentRegistry(config_dir=tmp_path)
    records = registry.to_capability_records()

    _, _, _, effect, auth, *_ = records[0]
    assert effect == "local_write"
    assert auth == "requires_approval"


def test_a_profile_without_an_executable_mode_is_explained_instead_of_offered(
    tmp_path: Path,
) -> None:
    # An ACP-runtime agent runs through run_extension, so it is reachable only directly.
    _write_agent(
        tmp_path, "handoff-only", invocation_modes=["handoff"],
        runtime={"kind": "acp", "adapter_id": "coder"},
    )

    registry = AgentRegistry(config_dir=tmp_path)
    descriptor = next(
        item
        for item in build_descriptors(
            CapabilityObservation(agents=tuple(registry.to_capability_records()))
        )
        if item.capability_id == "agent-invoke-handoff-only"
    )

    assert (descriptor.availability, descriptor.readiness) == ("misconfigured", "unavailable")
    assert "declares no invocation mode" in descriptor.unavailable_explanation


def test_a_profile_that_cannot_be_loaded_is_reported_instead_of_raised(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir(exist_ok=True)
    (tmp_path / "agents" / "broken.yaml").write_text("profile_id: broken\n", encoding="utf-8")
    _write_agent(tmp_path, "healthy")

    registry = AgentRegistry(config_dir=tmp_path)

    assert [p.profile_id for p in registry.profiles()] == ["healthy"]
    assert [capability_id for capability_id, _ in registry.errors()] == ["agent-invoke-broken"]


# --- refresh() ---


def test_profiles_are_reobserved_when_the_directory_changes(tmp_path: Path) -> None:
    # An operator edits these files while the backend runs, so the profile set is an
    # observation. Nothing calls refresh() on the running service.
    _write_agent(tmp_path, "alpha-agent")

    registry = AgentRegistry(config_dir=tmp_path)
    assert len(registry.profiles()) == 1

    _write_agent(tmp_path, "beta-agent")
    assert len(registry.profiles()) == 2

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
    assert cap.approval_mode == "same_turn"
    assert cap.metadata_claims == {"agent_id": {"value": "worker-agent", "trusted": False}}
    assert cap.execution_owner == "backend.app.agents.invocation"


# --- Operator-owned profiles ---


def _overlay(**states: str) -> SimpleNamespace:
    return SimpleNamespace(
        read=lambda extension_id: SimpleNamespace(state=states[extension_id])
        if extension_id in states
        else None
    )


def test_operator_profiles_load_beside_application_profiles_which_keep_their_id(
    tmp_path: Path,
) -> None:
    config, data = tmp_path / "config", tmp_path / "data"
    _write_agent(config, "shared", display_name="Application")
    _write_agent(data, "shared", display_name="Operator")
    _write_agent(data, "mine")

    registry = AgentRegistry(config_dir=config, data_dir=data)

    assert [p.profile_id for p in registry.profiles()] == ["mine", "shared"]
    assert registry.get("shared").display_name == "Application"
    assert registry.source("mine") == ("operator", "data/agents/mine.yaml")
    assert registry.errors() == (
        ("agent-invoke-shared", "an application agent profile owns this id"),
    )


def test_profile_writes_distinguish_create_from_a_fingerprinted_edit(tmp_path: Path) -> None:
    config, data = tmp_path / "config", tmp_path / "data"
    _write_agent(config, "application-owned")
    registry = AgentRegistry(config_dir=config, data_dir=data)

    created = registry.write_profile(_valid_yaml_dict(profile_id="mine"))
    assert registry.get("mine") is not None

    with pytest.raises(AgentProfileError, match="already exists") as duplicate:
        registry.write_profile(_valid_yaml_dict(profile_id="mine"))
    assert duplicate.value.status_code == 409

    edited = registry.write_profile(
        _valid_yaml_dict(profile_id="mine", purpose="Edited"),
        expected_fingerprint=created["fingerprint"],
    )
    assert registry.get("mine").purpose == "Edited"

    with pytest.raises(AgentProfileError, match="changed since it was read"):
        registry.write_profile(
            _valid_yaml_dict(profile_id="mine"), expected_fingerprint=created["fingerprint"]
        )
    with pytest.raises(AgentProfileError, match="application agent profile owns"):
        registry.write_profile(_valid_yaml_dict(profile_id="application-owned"))
    with pytest.raises(AgentProfileError, match="prohibited authority fields") as invalid:
        registry.write_profile(_valid_yaml_dict(profile_id="bad", tool_policy={}))
    assert invalid.value.status_code == 422

    with pytest.raises(AgentProfileError, match="changed since it was read"):
        registry.delete_profile("mine", expected_fingerprint=created["fingerprint"])
    registry.delete_profile("mine", expected_fingerprint=edited["fingerprint"])
    assert registry.get("mine") is None
    with pytest.raises(AgentProfileError, match="application agent profile owns"):
        registry.delete_profile("application-owned")


def test_a_disabled_agent_is_served_as_disabled(tmp_path: Path) -> None:
    _write_agent(tmp_path, "paused")

    registry = AgentRegistry(config_dir=tmp_path, overlay=_overlay(**{"agent:paused": "disabled"}))
    descriptor = next(
        item
        for item in build_descriptors(
            CapabilityObservation(agents=tuple(registry.to_capability_records()))
        )
        if item.capability_id == "agent-invoke-paused"
    )

    assert (descriptor.availability, descriptor.readiness) == ("disabled", "ready")
    assert descriptor.unavailable_explanation == "Agent is disabled."


def _write_acp(root: Path, local_id: str = "coder") -> None:
    directory = root / "extensions" / "acp"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{local_id}.yaml").write_text(
        f"""
id: {local_id}
name: Coder
version: '1'
definition:
  command: [agent-bin, serve]
  process:
    subprocess: true
    argv_allowlist: [agent-bin]
    env_passthrough: []
    working_root: data
""",
        encoding="utf-8",
    )


def test_an_acp_runtime_agent_is_bounded_privileged_execution_and_tracks_its_adapter(
    tmp_path: Path,
) -> None:
    config, data = tmp_path / "config", tmp_path / "data"
    _write_agent(
        config, "external", approval_class="none",
        runtime={"kind": "acp", "adapter_id": "coder"},
    )

    def descriptor(registry: AgentRegistry) -> Any:
        return next(
            item
            for item in build_descriptors(
                CapabilityObservation(agents=tuple(registry.to_capability_records()))
            )
            if item.capability_id == "agent-invoke-external"
        )

    missing = descriptor(AgentRegistry(config_dir=config, data_dir=data))
    assert missing.availability == "misconfigured"
    assert "'coder' is not defined" in missing.unavailable_explanation

    _write_acp(config)
    ready = descriptor(AgentRegistry(config_dir=config, data_dir=data))
    # The approval class cannot lower the effect of running an external agent process.
    assert (ready.effect_class, ready.authorization_rule) == (
        "privileged_execution", "requires_approval",
    )
    assert ready.availability == "available"
    assert ready.boundaries["timeout_ms"] == ready.timeout_policy["timeout_ms"]
    assert ready.boundaries["process"]["argv_allowlist"] == ["agent-bin"]

    disabled = descriptor(
        AgentRegistry(config_dir=config, data_dir=data, overlay=_overlay(**{"acp:coder": "disabled"}))
    )
    assert "'coder' is disabled" in disabled.unavailable_explanation
