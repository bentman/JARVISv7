from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_api_state
from backend.app.api.app import ApiState
from backend.app.api.schemas.diagnostics import DiagnosticsAudioIngressResponse, DiagnosticsPreflightResponse, DiagnosticsProfileResponse
from backend.app.services.voice_service import diagnose_audio_ingress

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


@router.post("/diagnostics/audio-ingress", response_model=DiagnosticsAudioIngressResponse)
def diagnostics_audio_ingress(duration_s: float = 1.0) -> DiagnosticsAudioIngressResponse:
    result = diagnose_audio_ingress(duration_s=duration_s)
    return DiagnosticsAudioIngressResponse(
        usable=result.usable,
        sample_rate=result.sample_rate,
        sample_count=result.sample_count,
        dtype=result.dtype,
        duration=result.duration,
        input_device=result.input_device,
        rms=result.rms,
        peak=result.peak,
        reason=result.reason,
    )
