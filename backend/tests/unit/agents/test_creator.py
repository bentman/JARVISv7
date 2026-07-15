from __future__ import annotations

from pathlib import Path

from backend.app.agents.creator import (
    AgentSpecSeed,
    create_agent_spec,
    create_projectvision_agent_specs,
)
from backend.app.agents.ledger import AgentLedger
from backend.app.agents.specs import load_agent_specs


def test_agent_creator_writes_valid_disabled_spec_file(tmp_path: Path) -> None:
    ledger = AgentLedger(tmp_path / "ledger.sqlite3")
    result = create_agent_spec(
        AgentSpecSeed(
            spec_id="research_agent",
            display_name="Research Agent",
            description="Researches bounded questions.",
            prompt_path="config/prompts/agents/planner.md",
            purpose="Prepare bounded research notes.",
            instructions_summary="Summarize repo-local facts only.",
        ),
        directory=tmp_path / "specs",
        ledger=ledger,
        trace_id="trace-spec",
    )

    specs = load_agent_specs(tmp_path / "specs")
    records = ledger.list_by_trace("trace-spec")

    assert result.path == tmp_path / "specs" / "research_agent.yaml"
    assert result.path.exists()
    assert specs["research_agent"].enabled is False
    assert specs["research_agent"].created_by == "agent_creator"
    assert [record.record_type for record in records] == [
        "spec_design_requested",
        "spec_created",
        "spec_validated",
    ]


def test_agent_creator_populates_projectvision_specs_as_catalog_files(tmp_path: Path) -> None:
    ledger = AgentLedger(tmp_path / "ledger.sqlite3")
    results = create_projectvision_agent_specs(
        directory=tmp_path / "specs",
        ledger=ledger,
        trace_id="trace-projectvision",
    )
    specs = load_agent_specs(tmp_path / "specs")

    assert sorted(result.spec.spec_id for result in results) == ["critic", "curator", "executor", "learner", "planner"]
    assert sorted(specs) == ["critic", "curator", "executor", "learner", "planner"]
    assert all(not spec.enabled for spec in specs.values())
    assert all(spec.guardrails["execution_enabled"] is False for spec in specs.values())
    assert all(spec.allowed_tools == [] for spec in specs.values())
    assert all((tmp_path / "specs" / f"{spec_id}.yaml").exists() for spec_id in specs)
    assert [record.record_type for record in ledger.list_by_trace("trace-projectvision")].count("spec_created") == 5
