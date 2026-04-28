from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.app import ApiState
from backend.app.api.dependencies import get_api_state
from backend.app.api.schemas.status import WakeStatusResponse

router = APIRouter()


@router.get("/status/wake", response_model=WakeStatusResponse)
def wake_status(state: ApiState = Depends(get_api_state)) -> WakeStatusResponse:
    _device, available, reason = state.readiness["wake"]
    return WakeStatusResponse(provider="openwakeword", available=available, reason=reason)