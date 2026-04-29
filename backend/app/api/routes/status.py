from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.app import ApiState
from backend.app.api.dependencies import get_api_state
from backend.app.api.schemas.status import WakeStatusResponse

router = APIRouter()


@router.get("/status/wake", response_model=WakeStatusResponse)
def wake_status(state: ApiState = Depends(get_api_state)) -> WakeStatusResponse:
    _device, available, reason = state.readiness["wake"]
    state.session_service.configure_wake_status(provider="openwakeword", available=available, reason=reason)
    status = state.session_service.wake_status()
    return WakeStatusResponse(
        provider=status.provider,
        available=status.available,
        reason=status.reason,
        monitoring=status.monitoring,
        last_detected=status.last_detected,
        detection_count=status.detection_count,
        last_error=status.last_error,
    )