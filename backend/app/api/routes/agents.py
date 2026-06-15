from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.schemas.agents import AgentsStatusResponse
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
