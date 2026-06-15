from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from backend.app.agents.ledger import AgentLedger, AgentLedgerRecord
from backend.app.agents.specs import DEFAULT_SPECS_DIR, JarvisAgentSpec, write_agent_spec


class AgentSpecSeed(BaseModel):
    spec_id: str
    display_name: str
    description: str
    prompt_path: str
    purpose: str
    instructions_summary: str
    allowed_message_types: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)


class AgentSpecCreationResult(BaseModel):
    spec: JarvisAgentSpec
    path: Path
    ledger_record_ids: list[str] = Field(default_factory=list)


PROJECTVISION_AGENT_SEEDS: tuple[AgentSpecSeed, ...] = (
    AgentSpecSeed(
        spec_id="planner",
        display_name="Planner",
        description="Creates role-separated task decomposition and proposed plan records.",
        prompt_path="config/prompts/agents/planner.md",
        purpose="Propose bounded plans for agent-governed work without executing them.",
        instructions_summary="Decompose approved objectives into explicit dry-run plan records.",
        allowed_message_types=["request", "plan", "policy_decision"],
    ),
    AgentSpecSeed(
        spec_id="executor",
        display_name="Executor",
        description="Evaluates execution boundaries against policy and allowed tools.",
        prompt_path="config/prompts/agents/executor.md",
        purpose="Assess whether requested tool actions are policy-allowed without invoking tools.",
        instructions_summary="Produce dry-run execution decisions from policy and registry facts.",
        allowed_message_types=["request", "policy_decision", "outcome"],
    ),
    AgentSpecSeed(
        spec_id="critic",
        display_name="Critic",
        description="Reviews plans, outcomes, and policy risks.",
        prompt_path="config/prompts/agents/critic.md",
        purpose="Validate agent traces and surface risks without altering execution.",
        instructions_summary="Review recorded agent artifacts and produce read-only critique.",
        allowed_message_types=["request", "event", "policy_decision"],
    ),
    AgentSpecSeed(
        spec_id="curator",
        display_name="Curator",
        description="Curates training-data and artifact candidates from successful traces.",
        prompt_path="config/prompts/agents/curator.md",
        purpose="Identify deterministic artifact candidates from completed trace data.",
        instructions_summary="Score and deduplicate successful trace artifacts for later review.",
        allowed_message_types=["request", "event", "outcome"],
    ),
    AgentSpecSeed(
        spec_id="learner",
        display_name="Learner",
        description="Proposes training-cycle and regression-gated learning plans.",
        prompt_path="config/prompts/agents/learner.md",
        purpose="Recommend learning-plan candidates without training or deployment actions.",
        instructions_summary="Summarize curated candidates into regression-gated learning proposals.",
        allowed_message_types=["request", "plan", "outcome"],
    ),
)


def create_agent_spec(
    seed: AgentSpecSeed,
    *,
    directory: Path = DEFAULT_SPECS_DIR,
    ledger: AgentLedger | None = None,
    trace_id: str = "agent-spec-catalog",
    created_by: str = "agent_creator",
) -> AgentSpecCreationResult:
    requested = _append_event(ledger, trace_id, seed.spec_id, "spec_design_requested", seed.model_dump())
    spec = JarvisAgentSpec(
        spec_id=seed.spec_id,
        display_name=seed.display_name,
        description=seed.description,
        kind="default",
        enabled=False,
        created_by=created_by,
        prompt_path=seed.prompt_path,
        purpose=seed.purpose,
        instructions_summary=seed.instructions_summary,
        allowed_message_types=seed.allowed_message_types,
        allowed_tools=seed.allowed_tools,
        memory_policy={"session_memory": "none"},
        handoff_policy={"handoffs_enabled": False},
        output_contract={"format": "structured_record"},
        guardrails={"execution_enabled": False, "tools_enabled": False, "model_calls_enabled": False},
    )
    path = write_agent_spec(spec, directory)
    created = _append_event(ledger, trace_id, spec.spec_id, "spec_created", {"path": str(path), **spec.model_dump()})
    validated = _append_event(ledger, trace_id, spec.spec_id, "spec_validated", {"path": str(path)})
    return AgentSpecCreationResult(
        spec=spec,
        path=path,
        ledger_record_ids=[record_id for record_id in (requested, created, validated) if record_id is not None],
    )


def create_projectvision_agent_specs(
    *,
    directory: Path = DEFAULT_SPECS_DIR,
    ledger: AgentLedger | None = None,
    trace_id: str = "projectvision-agent-specs",
) -> list[AgentSpecCreationResult]:
    return [
        create_agent_spec(seed, directory=directory, ledger=ledger, trace_id=trace_id)
        for seed in PROJECTVISION_AGENT_SEEDS
    ]


def _append_event(
    ledger: AgentLedger | None,
    trace_id: str,
    spec_id: str,
    record_type: str,
    payload: dict[str, object],
) -> str | None:
    if ledger is None:
        return None
    record = ledger.append(
        AgentLedgerRecord(
            trace_id=trace_id,
            role_id="agent_creator",
            record_type=record_type,
            payload={"spec_id": spec_id, **payload},
        )
    )
    return record.record_id
