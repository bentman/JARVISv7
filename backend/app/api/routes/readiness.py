from __future__ import annotations

import re

from fastapi import APIRouter, Depends

from backend.app.api.app import ApiState
from backend.app.api.dependencies import get_api_state
from backend.app.api.schemas.readiness import FamilyReadiness, PreflightSummary, ReadinessResponse, ServiceReadiness
from backend.app.api.service_status import collect_service_statuses

router = APIRouter()


def _runtime_label(runtime: object) -> str:
    runtime_name = getattr(runtime, "runtime_name", None)
    if callable(runtime_name):
        return str(runtime_name())
    class_name = runtime.__class__.__name__
    for suffix in ("Runtime", "LLM"):
        if class_name.endswith(suffix):
            class_name = class_name[: -len(suffix)]
            break
    first_pass = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", class_name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", first_pass).lower()


def _runtime_labels(state: ApiState) -> dict[str, str]:
    return {
        "stt": _runtime_label(state.stt),
        "tts": _runtime_label(state.tts),
        "llm": state.llm.runtime_name(),
        "wake": state.session_service.wake_status().provider,
    }


def _family_readiness(name: str, readiness: tuple[str, bool, str], runtime_label: str) -> FamilyReadiness:
    device, ready, reason = readiness
    return FamilyReadiness(
        family=name,
        runtime=runtime_label,
        device=device,
        model="selected-by-runtime",
        ready=ready,
        reason=reason,
    )


def build_readiness_response(state: ApiState) -> ReadinessResponse:
    status = "ready" if not state.preflight.probe_errors else "degraded"
    services = collect_service_statuses()
    runtime_labels = _runtime_labels(state)
    return ReadinessResponse(
        status=status,
        profile_id=state.profile.profile_id,
        arch=state.profile.arch,
        active_personality_profile_id=state.personality.profile_id,
        active_llm_runtime=state.llm.runtime_name(),
        requires_degraded_mode=state.report.flags.requires_degraded_mode,
        families={
            name: _family_readiness(name, value, runtime_labels.get(name, "unknown"))
            for name, value in state.readiness.items()
        },
        preflight=PreflightSummary(
            tokens_count=len(state.preflight.tokens),
            probe_error_count=len(state.preflight.probe_errors),
        ),
        services={
            name: ServiceReadiness(reachable=value.reachable, reason=value.reason)
            for name, value in services.items()
        },
    )


@router.get("/readiness", response_model=ReadinessResponse)
def readiness(state: ApiState = Depends(get_api_state)) -> ReadinessResponse:
    return build_readiness_response(state)
