from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.app import ApiState
from backend.app.api.dependencies import get_api_state
from backend.app.api.schemas.readiness import FamilyReadiness, PreflightSummary, ReadinessResponse

router = APIRouter()

_RUNTIME_NAMES = {"stt": "onnx-whisper", "tts": "kokoro-onnx", "llm": "ollama", "wake": "openwakeword"}


def _family_readiness(name: str, readiness: tuple[str, bool, str]) -> FamilyReadiness:
    device, ready, reason = readiness
    return FamilyReadiness(
        family=name,
        runtime=_RUNTIME_NAMES[name],
        device=device,
        model="selected-by-runtime",
        ready=ready,
        reason=reason,
    )


def build_readiness_response(state: ApiState) -> ReadinessResponse:
    status = "ready" if not state.preflight.probe_errors else "degraded"
    return ReadinessResponse(
        status=status,
        profile_id=state.profile.profile_id,
        arch=state.profile.arch,
        active_personality_profile_id=state.personality.profile_id,
        active_llm_runtime=state.llm.runtime_name(),
        requires_degraded_mode=state.report.flags.requires_degraded_mode,
        families={name: _family_readiness(name, value) for name, value in state.readiness.items()},
        preflight=PreflightSummary(
            tokens_count=len(state.preflight.tokens),
            probe_error_count=len(state.preflight.probe_errors),
        ),
    )


@router.get("/readiness", response_model=ReadinessResponse)
def readiness(state: ApiState = Depends(get_api_state)) -> ReadinessResponse:
    return build_readiness_response(state)