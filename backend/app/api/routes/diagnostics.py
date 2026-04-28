from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_api_state
from backend.app.api.app import ApiState
from backend.app.api.schemas.diagnostics import DiagnosticsPreflightResponse, DiagnosticsProfileResponse

router = APIRouter()


@router.get("/diagnostics/profile", response_model=DiagnosticsProfileResponse)
def diagnostics_profile(state: ApiState = Depends(get_api_state)) -> DiagnosticsProfileResponse:
    return DiagnosticsProfileResponse(profile=asdict(state.report.profile), flags=asdict(state.report.flags))


@router.get("/diagnostics/preflight", response_model=DiagnosticsPreflightResponse)
def diagnostics_preflight(state: ApiState = Depends(get_api_state)) -> DiagnosticsPreflightResponse:
    return DiagnosticsPreflightResponse(
        tokens=state.preflight.tokens,
        dll_discovery_log=state.preflight.dll_discovery_log,
        probe_errors=state.preflight.probe_errors,
    )