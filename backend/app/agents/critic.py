from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.agents.ledger import AgentLedger, AgentLedgerRecord
from backend.app.agents.policy import AgentPolicy


class AgentCriticReview(BaseModel):
    trace_id: str
    approved: bool
    warnings: list[str] = Field(default_factory=list)
    reviewed_record_ids: list[str] = Field(default_factory=list)
    dry_run: bool = True


def review_trace_dry_run(
    trace_id: str,
    *,
    policy: AgentPolicy,
    ledger: AgentLedger,
) -> AgentCriticReview:
    records = ledger.list_by_trace(trace_id)
    warnings: list[str] = []
    if not policy.allows_role("critic"):
        warnings.append("critic role is not allowed by policy")
    if not records:
        warnings.append("no trace records found")

    review = AgentCriticReview(
        trace_id=trace_id,
        approved=not warnings,
        warnings=warnings,
        reviewed_record_ids=[record.record_id for record in records],
    )
    ledger.append(
        AgentLedgerRecord(
            trace_id=trace_id,
            role_id="critic",
            record_type="outcome",
            payload=review.model_dump(),
        )
    )
    return review
