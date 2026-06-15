from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.agents.specs import JarvisAgentSpec, load_agent_specs, spec_ids, write_agent_spec


def _spec(spec_id: str = "research_agent") -> JarvisAgentSpec:
    return JarvisAgentSpec(
        spec_id=spec_id,
        display_name="Research Agent",
        description="Researches bounded questions.",
        prompt_path="config/prompts/agents/planner.md",
        purpose="Prepare bounded research notes.",
        instructions_summary="Summarize repo-local facts only.",
    )


def test_default_agent_specs_load_from_repo_catalog() -> None:
    specs = load_agent_specs()

    assert spec_ids(specs) == ["agent_creator", "critic", "curator", "executor", "learner", "planner"]
    assert specs["planner"].enabled is False
    assert specs["planner"].created_by == "agent_creator"


def test_agent_spec_rejects_invalid_id() -> None:
    with pytest.raises(ValidationError, match="spec_id"):
        _spec("ResearchAgent")


def test_agent_spec_rejects_prompt_path_escape() -> None:
    with pytest.raises(ValidationError, match="config/prompts/agents"):
        JarvisAgentSpec(
            spec_id="research_agent",
            display_name="Research Agent",
            description="Researches bounded questions.",
            prompt_path="config/prompts/../app/policies.yaml",
            purpose="Prepare bounded research notes.",
            instructions_summary="Summarize repo-local facts only.",
        )


def test_write_and_load_agent_spec(tmp_path: Path) -> None:
    path = write_agent_spec(_spec(), tmp_path)
    specs = load_agent_specs(tmp_path)

    assert path == tmp_path / "research_agent.yaml"
    assert specs["research_agent"].enabled is False


def test_load_agent_specs_rejects_duplicate_id(tmp_path: Path) -> None:
    write_agent_spec(_spec("research_agent"), tmp_path)
    (tmp_path / "duplicate.yaml").write_text((tmp_path / "research_agent.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate"):
        load_agent_specs(tmp_path)
