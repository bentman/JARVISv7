from __future__ import annotations

from typing import Any

from backend.app.agents.registry import AgentRegistry
from backend.app.api.schemas.agents import (
    AgentInvokeRequest,
    AgentInvokeResponse,
    AgentListResponse,
    AgentProfileResponse,
    AgentRunResponse,
)
from backend.app.services.capability_service import CapabilityService, CapabilityServiceError
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

router = APIRouter(prefix="/agents")

MAX_AUDIT_LIMIT = 100


def _get_agent_registry(request: Request) -> AgentRegistry:
    state = getattr(request.app.state, "jarvis_state", None)
    registry = getattr(state, "agent_registry", None)
    if registry is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "unavailable",
                "message": "agent registry is unavailable",
            },
        )
    return registry


def _get_capability_service(request: Request) -> CapabilityService:
    state = getattr(request.app.state, "jarvis_state", None)
    service = getattr(state, "capability_service", None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "unavailable",
                "message": "capability service is unavailable",
            },
        )
    return service


def _profile_to_response(profile: Any) -> AgentProfileResponse:
    return AgentProfileResponse(**profile.to_dict())


@router.get("", response_model=AgentListResponse)
def list_agents(
    registry: AgentRegistry = Depends(_get_agent_registry),
) -> AgentListResponse:
    agents = [_profile_to_response(p) for p in registry.profiles()]
    return AgentListResponse(agents=agents)


@router.get("/runs", response_model=AgentRunResponse)
def list_agent_runs(
    limit: int = Query(default=20, ge=1, le=MAX_AUDIT_LIMIT),
    service: CapabilityService = Depends(_get_capability_service),
) -> AgentRunResponse:
    try:
        audit = service.audit(limit=limit)
    except CapabilityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
    agent_records = [
        record
        for record in audit.records
        if str(record.get("capability_id", "")).startswith("agent-invoke-")
    ]
    return AgentRunResponse(records=agent_records)


@router.get("/{profile_id}", response_model=AgentProfileResponse)
def get_agent(
    profile_id: str = Path(min_length=1, max_length=64),
    registry: AgentRegistry = Depends(_get_agent_registry),
) -> AgentProfileResponse:
    profile = registry.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "agent not found"})
    return _profile_to_response(profile)


@router.post("/invoke", response_model=AgentInvokeResponse)
def invoke_agent(
    request: AgentInvokeRequest,
    service: CapabilityService = Depends(_get_capability_service),
) -> AgentInvokeResponse:
    try:
        view = service.propose(
            capability_id=f"agent-invoke-{request.profile_id}",
            arguments={"prompt": request.prompt},
            proposed_by="operator",
            reason="agent invocation request",
        )
    except CapabilityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
    execution = view.execution if isinstance(view.execution, dict) else {}
    result = execution.get("result") if isinstance(execution.get("result"), dict) else {}
    # A failed agent run is reported in the invocation result rather than raised, so the
    # capability execution status is not the agent's outcome.
    return AgentInvokeResponse(
        agent_id=request.profile_id,
        status=result.get("status", view.status),
        output=result.get("output", result),
        turn_id=result.get("turn_id") or execution.get("proposal_id") or view.proposal_id,
        session_id=result.get("session_id", "api"),
        # A denial has no execution record, so the authorization reason is the only account
        # of why nothing ran.
        error=result.get("error") or execution.get("error") or (
            view.reason if view.outcome == "denied" else None
        ),
    )


@router.post("/{profile_id}/cancel")
def cancel_agent(
    profile_id: str = Path(min_length=1, max_length=64),
    service: CapabilityService = Depends(_get_capability_service),
) -> dict[str, Any]:
    try:
        audit = service.audit(limit=50)
    except CapabilityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
    capability_id = f"agent-invoke-{profile_id}"
    for record in audit.records:
        if record.get("capability_id") == capability_id and record.get("kind") == "action_proposal":
            proposal_id = record.get("proposal_id")
            if proposal_id:
                try:
                    cancelled = service.cancel(proposal_id)
                except CapabilityServiceError as exc:
                    raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
                return {"profile_id": profile_id, "cancelled": cancelled}
    return {"profile_id": profile_id, "cancelled": False}
