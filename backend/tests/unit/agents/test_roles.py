from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.agents.roles import load_agent_roles, role_ids, role_payload


def test_load_agent_roles_from_default_config() -> None:
    roles = load_agent_roles()

    assert role_ids(roles) == ["agent_creator", "critic", "curator", "executor", "learner", "planner"]
    assert roles["planner"].prompt_path == "config/prompts/agents/planner.md"
    assert role_payload(roles)[0]["role_id"] == "agent_creator"


def test_load_agent_roles_custom_file_has_no_fixed_role_requirement(tmp_path: Path) -> None:
    path = tmp_path / "roles.yaml"
    path.write_text(
        "roles:\n"
        "  - role_id: research_agent\n"
        "    display_name: Research Agent\n"
        "    description: Researches bounded questions.\n"
        "    prompt_path: config/prompts/agents/planner.md\n",
        encoding="utf-8",
    )

    roles = load_agent_roles(path)

    assert role_ids(roles) == ["research_agent"]


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
