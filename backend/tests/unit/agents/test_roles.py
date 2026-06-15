from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.agents.roles import load_agent_roles, role_ids, role_payload


def test_load_agent_roles_from_default_config() -> None:
    roles = load_agent_roles()

    assert role_ids(roles) == ["critic", "curator", "executor", "learner", "planner"]
    assert roles["planner"].prompt_path == "config/prompts/agents/planner.md"
    assert role_payload(roles)[0]["role_id"] == "critic"


def test_load_agent_roles_rejects_missing_required_role(tmp_path: Path) -> None:
    path = tmp_path / "roles.yaml"
    path.write_text(
        "roles:\n"
        "  - role_id: planner\n"
        "    display_name: Planner\n"
        "    description: Plans.\n"
        "    prompt_path: config/prompts/agents/planner.md\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing roles"):
        load_agent_roles(path)


def test_load_agent_roles_rejects_duplicate_role(tmp_path: Path) -> None:
    path = tmp_path / "roles.yaml"
    path.write_text(
        "roles:\n"
        "  - role_id: planner\n"
        "    display_name: Planner\n"
        "    description: Plans.\n"
        "    prompt_path: config/prompts/agents/planner.md\n"
        "  - role_id: planner\n"
        "    display_name: Planner Again\n"
        "    description: Duplicate.\n"
        "    prompt_path: config/prompts/agents/planner.md\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate"):
        load_agent_roles(path)
