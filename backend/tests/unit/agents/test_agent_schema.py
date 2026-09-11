from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from backend.app.agents.loader import load_agent_profile, load_agent_profiles
from backend.app.agents.schema import (
    AgentProfile,
)


def profile(**overrides) -> AgentProfile:
    values = {
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
    return AgentProfile(**values)  # type: ignore[arg-type]


def _valid_yaml_dict(**overrides) -> dict:
    values = {
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


# --- Valid creation ---


def test_valid_agent_profile_with_all_fields() -> None:
    p = profile(
        invocation_modes=("direct", "router_selected", "as_tool", "handoff"),
        capability_ids=("read-file", "web-search"),
        memory_scope="full",
        approval_class="strict",
        timeout_ms=600000,
        cancellable=False,
        provider_model_policy={"preferred": "gpt-4"},
    )
    assert p.profile_id == "test-agent"
    assert p.memory_scope == "full"
    assert p.approval_class == "strict"
    assert p.timeout_ms == 600000
    assert p.cancellable is False
    assert p.provider_model_policy == {"preferred": "gpt-4"}


def test_valid_agent_profile_with_minimal_fields() -> None:
    p = profile()
    assert p.profile_id == "test-agent"
    assert p.capability_ids == ()
    assert p.provider_model_policy == {}


# --- Invalid profile_id ---


def test_profile_id_rejects_uppercase() -> None:
    with pytest.raises(ValueError, match="profile_id must contain only"):
        profile(profile_id="TestAgent")


def test_profile_id_rejects_special_chars() -> None:
    with pytest.raises(ValueError, match="profile_id must contain only"):
        profile(profile_id="test_agent")


def test_profile_id_rejects_underscore() -> None:
    with pytest.raises(ValueError, match="profile_id must contain only"):
        profile(profile_id="test_agent_v2")


def test_profile_id_rejects_too_long() -> None:
    with pytest.raises(ValueError, match="at most 64"):
        profile(profile_id="a" * 65)


def test_profile_id_rejects_empty() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        profile(profile_id="")


def test_profile_id_rejects_leading_hyphen() -> None:
    with pytest.raises(ValueError, match="profile_id must contain only"):
        profile(profile_id="-agent")


# --- Invalid invocation_modes ---


def test_invocation_modes_rejects_empty_tuple() -> None:
    with pytest.raises(ValueError, match="invocation_modes must be a non-empty"):
        profile(invocation_modes=())


def test_invocation_modes_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="invalid invocation_mode"):
        profile(invocation_modes=("direct", "unknown_mode"))


# --- Invalid memory_scope ---


def test_memory_scope_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="invalid memory_scope"):
        profile(memory_scope="global")


# --- Invalid approval_class ---


def test_approval_class_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="invalid approval_class"):
        profile(approval_class="lax")


# --- Invalid timeout_ms ---


def test_timeout_ms_rejects_too_low() -> None:
    with pytest.raises(ValueError, match="timeout_ms must be between"):
        profile(timeout_ms=500)


def test_timeout_ms_rejects_too_high() -> None:
    with pytest.raises(ValueError, match="timeout_ms must be between"):
        profile(timeout_ms=700000)


def test_timeout_ms_rejects_zero() -> None:
    with pytest.raises(ValueError, match="timeout_ms must be between"):
        profile(timeout_ms=0)


# --- Authority field rejection ---


def test_profile_rejects_tool_policy() -> None:
    with pytest.raises(ValueError, match="prohibited authority fields"):
        AgentProfile.from_dict({**_valid_yaml_dict(), "tool_policy": {}})


def test_profile_rejects_routing_policy() -> None:
    with pytest.raises(ValueError, match="prohibited authority fields"):
        AgentProfile.from_dict({**_valid_yaml_dict(), "routing_policy": {}})


def test_profile_rejects_safety_overrides() -> None:
    with pytest.raises(ValueError, match="prohibited authority fields"):
        AgentProfile.from_dict({**_valid_yaml_dict(), "safety_overrides": {}})


def test_profile_rejects_hidden_instructions() -> None:
    with pytest.raises(ValueError, match="prohibited authority fields"):
        AgentProfile.from_dict({**_valid_yaml_dict(), "hidden_instructions": "secret"})


# --- to_dict roundtrip ---


def test_to_dict_roundtrip() -> None:
    p = profile(
        invocation_modes=("direct", "as_tool"),
        capability_ids=("read-file",),
        provider_model_policy={"preferred": "claude"},
    )
    d = p.to_dict()
    assert d["profile_id"] == "test-agent"
    assert d["invocation_modes"] == ("direct", "as_tool")
    assert d["capability_ids"] == ("read-file",)
    assert d["provider_model_policy"] == {"preferred": "claude"}
    # Reconstruct from dict
    restored = AgentProfile.from_dict(d)
    assert restored == p


# --- Loader tests ---


def test_load_agent_profile_from_yaml(tmp_path: Path) -> None:
    data = _valid_yaml_dict()
    yaml_file = tmp_path / "test.yaml"
    _write_yaml(yaml_file, data)
    p = load_agent_profile(yaml_file)
    assert p.profile_id == "yaml-agent"
    assert p.display_name == "YAML Agent"


def test_load_agent_profile_rejects_authority_yaml_keys(tmp_path: Path) -> None:
    data = _valid_yaml_dict(tool_policy={})
    yaml_file = tmp_path / "bad.yaml"
    _write_yaml(yaml_file, data)
    with pytest.raises(ValueError, match="prohibited authority fields"):
        load_agent_profile(yaml_file)


def test_load_agent_profiles_discovers_and_sorts(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    _write_yaml(agents_dir / "beta.yaml", _valid_yaml_dict(profile_id="beta-agent"))
    _write_yaml(agents_dir / "alpha.yaml", _valid_yaml_dict(profile_id="alpha-agent"))

    profiles = load_agent_profiles(tmp_path)
    assert len(profiles) == 2
    assert profiles[0].profile_id == "alpha-agent"
    assert profiles[1].profile_id == "beta-agent"


def test_load_agent_profiles_empty_directory(tmp_path: Path) -> None:
    profiles = load_agent_profiles(tmp_path)
    assert profiles == []
