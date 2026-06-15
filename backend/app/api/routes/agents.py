from __future__ import annotations

from fastapi import APIRouter

from backend.app.agents.ledger import AgentLedger
from backend.app.api.schemas.agents import AgentTraceRecordResponse, AgentTraceResponse, AgentsStatusResponse
from backend.app.agents.policy import load_agent_policy

router = APIRouter()


@router.get("/agents/status", response_model=AgentsStatusResponse)
def agents_status() -> AgentsStatusResponse:
    policy = load_agent_policy()
    return AgentsStatusResponse(
        enabled=policy.enabled,
        read_only=policy.read_only,
        reason=policy.reason,
        allowed_roles=policy.allowed_roles,
        allowed_tools=policy.allowed_tools,
    )


@router.get("/agents/traces/{trace_id}", response_model=AgentTraceResponse)
def agent_trace(trace_id: str) -> AgentTraceResponse:
    records = AgentLedger().list_by_trace(trace_id)
    return AgentTraceResponse(
        trace_id=trace_id,
        read_only=True,
        records=[AgentTraceRecordResponse(**record.model_dump()) for record in records],
    )
