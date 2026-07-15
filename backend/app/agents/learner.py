from __future__ import annotations

from backend.app.agents.curator import CuratedArtifactCandidate
from backend.app.agents.ledger import AgentLedger, AgentLedgerRecord
from pydantic import BaseModel, Field


class LearnerProposal(BaseModel):
    trace_id: str
    candidate_count: int
    recommended_action: str
    blocked_actions: list[str] = Field(default_factory=lambda: ["train_model", "deploy_adapter", "route_model"])
    dry_run: bool = True


def propose_learning_plan_dry_run(
    trace_id: str,
    candidates: list[CuratedArtifactCandidate],
    *,
    ledger: AgentLedger,
) -> LearnerProposal:
    proposal = LearnerProposal(
        trace_id=trace_id,
        candidate_count=len(candidates),
        recommended_action="collect_more_candidates" if len(candidates) < 3 else "prepare_eval_dataset_proposal",
    )
    ledger.append(
        AgentLedgerRecord(
            trace_id=trace_id,
            role_id="learner",
            record_type="plan",
            payload=proposal.model_dump(),
        )
    )
    return proposal
