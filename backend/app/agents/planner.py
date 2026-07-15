from __future__ import annotations

from typing import Any

from backend.app.agents.ledger import AgentLedger, AgentLedgerRecord
from backend.app.agents.messages import AgentRequest, AgentResponse
from backend.app.agents.policy import AgentPolicy
from pydantic import BaseModel, Field


class AgentPlanStep(BaseModel):
    step_id: str
    description: str
    requested_tool: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)


class AgentPlan(BaseModel):
    trace_id: str
    objective: str
    steps: list[AgentPlanStep]
    dry_run: bool = True


def create_planner_dry_run(
    request: AgentRequest,
    *,
    policy: AgentPolicy,
    ledger: AgentLedger,
    steps: list[AgentPlanStep] | None = None,
) -> AgentResponse:
    if request.requested_role != "planner":
        return _record_policy_rejection(
            request,
            policy=policy,
            ledger=ledger,
            reason="request role is not planner",
        )
    if not policy.allows_role("planner"):
        return _record_policy_rejection(
            request,
            policy=policy,
            ledger=ledger,
            reason="planner role is not allowed by policy",
        )

    plan = AgentPlan(
        trace_id=request.trace_id,
        objective=request.objective,
        steps=steps or [AgentPlanStep(step_id="step-1", description=request.objective)],
    )
    record = AgentLedgerRecord(
        trace_id=request.trace_id,
        role_id="planner",
        record_type="plan",
        payload=plan.model_dump(),
    )
    ledger.append(record)
    return AgentResponse(
        trace_id=request.trace_id,
        responding_role="planner",
        status="recorded",
        payload={"record_id": record.record_id, "plan": plan.model_dump()},
        run_mode="dry_run",
    )


def _record_policy_rejection(
    request: AgentRequest,
    *,
    policy: AgentPolicy,
    ledger: AgentLedger,
    reason: str,
) -> AgentResponse:
    record = AgentLedgerRecord(
        trace_id=request.trace_id,
        role_id="planner",
        record_type="policy_decision",
        payload={
            "allowed": False,
            "reason": reason,
            "policy_enabled": policy.enabled,
            "allowed_roles": policy.allowed_roles,
        },
    )
    ledger.append(record)
    return AgentResponse(
        trace_id=request.trace_id,
        responding_role="planner",
        status="rejected",
        payload={"record_id": record.record_id, "reason": reason},
        run_mode="dry_run",
    )
