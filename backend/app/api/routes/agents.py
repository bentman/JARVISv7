from __future__ import annotations

from backend.app.agents.ledger import AgentLedger
from backend.app.agents.policy import load_agent_policy
from backend.app.agents.specs import load_agent_specs
from backend.app.api.schemas.agents import (
    AgentSpecStatusResponse,
    AgentsStatusResponse,
    AgentTraceRecordResponse,
    AgentTraceResponse,
)
from fastapi import APIRouter

router = APIRouter()


@router.get("/agents/status", response_model=AgentsStatusResponse)
def agents_status() -> AgentsStatusResponse:
    policy = load_agent_policy()
    specs = load_agent_specs()
    return AgentsStatusResponse(
        enabled=policy.enabled,
        read_only=policy.read_only,
        reason=policy.reason,
        allowed_roles=policy.allowed_roles,
        allowed_tools=policy.allowed_tools,
        known_specs=[
            AgentSpecStatusResponse(
                spec_id=spec.spec_id,
                display_name=spec.display_name,
                kind=spec.kind,
                enabled=spec.enabled and policy.allows_role(spec.spec_id),
                policy_allowed=policy.allows_role(spec.spec_id),
                allowed_tools=spec.allowed_tools,
            )
            for spec in sorted(specs.values(), key=lambda item: item.spec_id)
        ],
    )


@router.get("/agents/traces/{trace_id}", response_model=AgentTraceResponse)
def agent_trace(trace_id: str) -> AgentTraceResponse:
    records = AgentLedger().list_by_trace(trace_id)
    return AgentTraceResponse(
        trace_id=trace_id,
        read_only=True,
        records=[AgentTraceRecordResponse(**record.model_dump()) for record in records],
    )
