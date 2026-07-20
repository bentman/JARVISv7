from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.agents.specs import JarvisAgentSpec, load_agent_specs


def _spec(spec_id: str = "research_agent") -> JarvisAgentSpec:
    return JarvisAgentSpec(
        spec_id=spec_id,
        display_name="Research Agent",
        description="Researches bounded questions.",
        purpose="Prepare bounded research notes.",
        instructions_summary="Summarize repo-local facts only.",
    )


def test_default_agent_specs_load_from_repo_catalog() -> None:
    specs = load_agent_specs()

    assert sorted(specs) == ["critic", "curator", "executor", "learner", "planner"]
    assert specs["planner"].enabled is False
    assert specs["planner"].created_by == "repo"
    assert all("prompt_path" not in spec.model_dump() for spec in specs.values())


def test_agent_spec_rejects_invalid_id() -> None:
    with pytest.raises(ValidationError, match="spec_id"):
        _spec("ResearchAgent")


def test_load_agent_specs_rejects_duplicate_id(tmp_path: Path) -> None:
    source = Path("config/agents/specs/planner.yaml").read_text(encoding="utf-8")
    (tmp_path / "planner.yaml").write_text(source, encoding="utf-8")
    (tmp_path / "duplicate.yaml").write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate"):
        load_agent_specs(tmp_path)
