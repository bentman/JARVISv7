from __future__ import annotations

from typing import Any

from backend.app.actions import catalog
from backend.app.agents.registry import AgentProfileError, AgentRegistry, profile_fingerprint
from backend.app.api.schemas.agents import (
    AgentInvokeRequest,
    AgentInvokeResponse,
    AgentListResponse,
    AgentProfileResponse,
    AgentProfileWriteRequest,
    AgentProfileWriteResponse,
    AgentRunResponse,
    AgentToolChoice,
    AgentToolListResponse,
)
from backend.app.services.capability_service import (
    CapabilityService,
    CapabilityServiceError,
    execute_operator_action,
)
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


def _profile_to_response(registry: AgentRegistry, profile: Any) -> AgentProfileResponse:
    trust, source = registry.source(profile.profile_id)
    return AgentProfileResponse(
        **profile.to_dict(),
        source=source,
        editable=trust == "operator",
        enabled=registry.enabled(profile.profile_id),
        fingerprint=profile_fingerprint(profile),
    )


def _manage(service: CapabilityService, capability_id: str, arguments: dict[str, Any], operation: Any) -> Any:
    try:
        return execute_operator_action(service, capability_id, arguments, operation)
    except AgentProfileError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"error": exc.error, "message": str(exc)}
        ) from exc
    except CapabilityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc


@router.get("", response_model=AgentListResponse)
def list_agents(
    registry: AgentRegistry = Depends(_get_agent_registry),
) -> AgentListResponse:
    agents = [_profile_to_response(registry, p) for p in registry.profiles()]
    problems = [
        {"capability_id": capability_id, "reason": reason}
        for capability_id, reason in registry.errors()
    ]
    return AgentListResponse(agents=agents, problems=problems)


@router.post("", response_model=AgentProfileWriteResponse, status_code=201)
def create_agent(
    request: AgentProfileWriteRequest,
    registry: AgentRegistry = Depends(_get_agent_registry),
    service: CapabilityService = Depends(_get_capability_service),
) -> AgentProfileWriteResponse:
    if request.expected_fingerprint is not None:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid", "message": "a create cannot name an expected fingerprint"},
        )
    result = _manage(
        service, catalog.AGENT_PROFILE_WRITE, {"profile": request.profile},
        lambda: registry.write_profile(request.profile),
    )
    return AgentProfileWriteResponse(**result)


@router.put("/{profile_id}", response_model=AgentProfileWriteResponse)
def update_agent(
    request: AgentProfileWriteRequest,
    profile_id: str = Path(min_length=1, max_length=64),
    registry: AgentRegistry = Depends(_get_agent_registry),
    service: CapabilityService = Depends(_get_capability_service),
) -> AgentProfileWriteResponse:
    if request.profile.get("profile_id") != profile_id:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid", "message": "profile_id cannot change on update"},
        )
    if request.expected_fingerprint is None:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid", "message": "an update requires expected_fingerprint"},
        )
    arguments = {"profile": request.profile, "expected_fingerprint": request.expected_fingerprint}
    result = _manage(
        service, catalog.AGENT_PROFILE_WRITE, arguments,
        lambda: registry.write_profile(
            request.profile, expected_fingerprint=request.expected_fingerprint
        ),
    )
    return AgentProfileWriteResponse(**result)


@router.delete("/{profile_id}")
def delete_agent(
    profile_id: str = Path(min_length=1, max_length=64),
    expected_fingerprint: str | None = Query(default=None, min_length=1),
    registry: AgentRegistry = Depends(_get_agent_registry),
    service: CapabilityService = Depends(_get_capability_service),
) -> dict[str, Any]:
    arguments: dict[str, Any] = {"profile_id": profile_id}
    if expected_fingerprint is not None:
        arguments["expected_fingerprint"] = expected_fingerprint
    return _manage(
        service, catalog.AGENT_PROFILE_DELETE, arguments,
        lambda: registry.delete_profile(profile_id, expected_fingerprint=expected_fingerprint),
    )


@router.get("/tools", response_model=AgentToolListResponse)
def list_agent_tools(
    request: Request,
    service: CapabilityService = Depends(_get_capability_service),
) -> AgentToolListResponse:
    """Capabilities an agent profile may allow: the ones the assistant's model may use."""
    runtime = getattr(request.app.state.jarvis_state, "extension_runtime", None)
    entries = runtime.tool_catalog() if runtime is not None else []
    views = {view.capability_id: view for view in service.catalog().capabilities}
    tools = []
    for entry in entries:
        view = views.get(entry["capability_id"])
        if view is None or view.authorization_rule == "deny":
            continue
        tools.append(AgentToolChoice(
            capability_id=entry["capability_id"],
            label=f"{entry['extension_id']} {entry['name']}".strip(),
            needs_approval=view.authorization_rule == "requires_approval",
            available=view.availability == "available" and view.readiness != "unavailable",
        ))
    return AgentToolListResponse(tools=tools)


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
    return _profile_to_response(registry, profile)


@router.post("/invoke", response_model=AgentInvokeResponse)
def invoke_agent(
    request: AgentInvokeRequest,
    service: CapabilityService = Depends(_get_capability_service),
) -> AgentInvokeResponse:
    try:
        view = service.invoke_operator_capability(
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
