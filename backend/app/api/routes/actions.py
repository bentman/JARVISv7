from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import TypeVar

from backend.app.api.dependencies import get_capability_service
from backend.app.api.schemas.actions import (
    ActionAuditResponse,
    ActionCancelResponse,
    ActionDecisionRequest,
    ActionProposalRequest,
    ActionProposalResponse,
    CapabilityCatalogResponse,
    PendingApprovalListResponse,
)
from backend.app.services.capability_service import CapabilityService, CapabilityServiceError
from fastapi import APIRouter, Depends, HTTPException, Path, Query

router = APIRouter(prefix="/actions")

MAX_AUDIT_LIMIT = 100

T = TypeVar("T")


def _execute(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except CapabilityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "action operation failed"},
        ) from exc


@router.get("/capabilities", response_model=CapabilityCatalogResponse)
def list_capabilities(
    service: CapabilityService = Depends(get_capability_service),
) -> CapabilityCatalogResponse:
    return CapabilityCatalogResponse.model_validate(asdict(_execute(service.catalog)))


@router.get("/pending", response_model=PendingApprovalListResponse)
def list_pending_approvals(
    service: CapabilityService = Depends(get_capability_service),
) -> PendingApprovalListResponse:
    pending = _execute(service.pending)
    return PendingApprovalListResponse.model_validate(
        {"pending": [asdict(item) for item in pending]}
    )


@router.get("/audit", response_model=ActionAuditResponse)
def read_action_audit(
    limit: int = Query(default=20, ge=1, le=MAX_AUDIT_LIMIT),
    service: CapabilityService = Depends(get_capability_service),
) -> ActionAuditResponse:
    return ActionAuditResponse.model_validate(asdict(_execute(lambda: service.audit(limit=limit))))


@router.post("/propose", response_model=ActionProposalResponse)
def propose_action(
    request: ActionProposalRequest,
    service: CapabilityService = Depends(get_capability_service),
) -> ActionProposalResponse:
    view = _execute(
        lambda: service.propose(
            capability_id=request.capability_id,
            arguments=request.arguments,
            proposed_by=request.proposed_by,
            reason=request.reason,
        )
    )
    return ActionProposalResponse.model_validate(asdict(view))


@router.get("/{proposal_id}", response_model=ActionProposalResponse)
def read_action_status(
    proposal_id: str = Path(min_length=1, max_length=64),
    service: CapabilityService = Depends(get_capability_service),
) -> ActionProposalResponse:
    return ActionProposalResponse.model_validate(asdict(_execute(lambda: service.status(proposal_id))))


@router.post("/{proposal_id}/decision", response_model=ActionProposalResponse)
def decide_action(
    request: ActionDecisionRequest,
    proposal_id: str = Path(min_length=1, max_length=64),
    service: CapabilityService = Depends(get_capability_service),
) -> ActionProposalResponse:
    view = _execute(
        lambda: service.decide(
            proposal_id=proposal_id,
            outcome=request.outcome,
            decided_by="operator",
            reason=request.reason,
        )
    )
    return ActionProposalResponse.model_validate(asdict(view))


@router.post("/{proposal_id}/cancel", response_model=ActionCancelResponse)
def cancel_action(
    proposal_id: str = Path(min_length=1, max_length=64),
    service: CapabilityService = Depends(get_capability_service),
) -> ActionCancelResponse:
    cancelled = _execute(lambda: service.cancel(proposal_id))
    return ActionCancelResponse(proposal_id=proposal_id, cancelled=cancelled)
