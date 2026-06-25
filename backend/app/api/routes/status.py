from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.app import ApiState
from backend.app.api.dependencies import get_api_state
from backend.app.api.schemas.status import ResidentVoiceStatusResponse, WakeStatusResponse

router = APIRouter()


@router.get("/status/wake", response_model=WakeStatusResponse)
def wake_status(state: ApiState = Depends(get_api_state)) -> WakeStatusResponse:
    _device, available, reason = state.readiness["wake"]
    state.session_service.configure_wake_status(provider="openwakeword", available=available, reason=reason)
    status = state.session_service.wake_status()
    return _wake_response(status)


@router.post("/status/wake/start", response_model=WakeStatusResponse)
def start_wake_monitor(state: ApiState = Depends(get_api_state)) -> WakeStatusResponse:
    return _wake_response(state.wake_monitor.start())


@router.post("/status/wake/stop", response_model=WakeStatusResponse)
def stop_wake_monitor(state: ApiState = Depends(get_api_state)) -> WakeStatusResponse:
    return _wake_response(state.wake_monitor.stop())


@router.post("/status/wake/toggle", response_model=WakeStatusResponse)
def toggle_wake_monitor(state: ApiState = Depends(get_api_state)) -> WakeStatusResponse:
    return _wake_response(state.wake_monitor.toggle())


@router.get("/status/resident-voice", response_model=ResidentVoiceStatusResponse)
def resident_voice_status(state: ApiState = Depends(get_api_state)) -> ResidentVoiceStatusResponse:
    return build_resident_voice_status(state)


def build_resident_voice_status(state: ApiState) -> ResidentVoiceStatusResponse:
    stream = state.resident_audio_stream
    stream_status = stream.status() if stream is not None else None
    wake = state.session_service.wake_status()
    vad_configured = state.utterance_segmenter is not None
    degraded_reasons: list[str] = []
    if state.resident_voice is None:
        degraded_reasons.append("resident voice invocation service is unavailable")
    if stream is None:
        degraded_reasons.append("resident audio stream is not configured")
    elif stream_status is not None and stream_status.last_error:
        degraded_reasons.append(f"resident audio stream error: {stream_status.last_error}")
    if not vad_configured:
        degraded_reasons.append("utterance segmenter is not configured")

    stream_running = bool(stream_status.running) if stream_status is not None else False
    return ResidentVoiceStatusResponse(
        mode="ptt+wake",
        available=state.resident_voice is not None and stream is not None and vad_configured and not degraded_reasons,
        degraded_reasons=degraded_reasons,
        stream_present=stream is not None,
        stream_running=stream_running,
        stream_subscribers=stream_status.subscribers if stream_status is not None else 0,
        stream_buffer_chunks=stream_status.buffer_chunks if stream_status is not None else 0,
        stream_dropped_chunks=stream_status.dropped_chunks if stream_status is not None else 0,
        stream_last_error=stream_status.last_error if stream_status is not None else None,
        vad_configured=vad_configured,
        ptt_supported=state.resident_voice is not None,
        wake_supported=state.wake_monitor is not None,
        wake_active=wake.active,
        wake_monitoring=wake.monitoring,
        barge_in_supported=stream is not None and vad_configured,
    )


def _wake_response(status) -> WakeStatusResponse:
    return WakeStatusResponse(
        provider=status.provider,
        available=status.available,
        reason=status.reason,
        active=status.active,
        enabled=status.enabled,
        monitoring=status.monitoring,
        last_detected=status.last_detected,
        detection_count=status.detection_count,
        last_error=status.last_error,
        last_score=status.last_score,
        threshold=status.threshold,
    )
