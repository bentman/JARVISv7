from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.schemas.agents import AgentsStatusResponse

router = APIRouter()


@router.get("/agents/status", response_model=AgentsStatusResponse)
def agents_status() -> AgentsStatusResponse:
    return AgentsStatusResponse(enabled=False, read_only=True, reason="Group I not implemented")