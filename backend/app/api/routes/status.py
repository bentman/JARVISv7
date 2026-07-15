from __future__ import annotations

from dataclasses import replace

from backend.app.api.app import ApiState, bind_session
from backend.app.api.dependencies import get_api_state
from backend.app.api.routes.session import build_session_status_response
from backend.app.api.schemas.status import (
    DesktopStatusSnapshotResponse,
    ResidentVoiceModeRequest,
    ResidentVoiceStatusResponse,
    ResidentVoiceStreamStatus,
    ResidentVoiceTTSVoiceRequest,
    WakeStatusResponse,
)
from backend.app.runtimes.tts.tts_runtime import tts_voice_config, validate_tts_voice
from backend.app.services.wake_status import WakeMonitorStatus
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.get("/status/wake", response_model=WakeStatusResponse)
def wake_status(state: ApiState = Depends(get_api_state)) -> WakeStatusResponse:
    return _wake_response(_configured_wake_status(state))


@router.get("/status/desktop", response_model=DesktopStatusSnapshotResponse)
def desktop_status(state: ApiState = Depends(get_api_state)) -> DesktopStatusSnapshotResponse:
    mode = state.resident_voice.mode() if state.resident_voice is not None else "ptt-only"
    wake = _reconcile_resident_wake(state, _configured_wake_status(state), mode=mode)
    return DesktopStatusSnapshotResponse(
        session=build_session_status_response(state.session_service.status()),
        resident_voice=build_resident_voice_status(state, wake=wake, mode=mode),
        wake=_wake_response(wake),
    )


@router.post("/status/wake/start", response_model=WakeStatusResponse)
def start_wake_monitor(state: ApiState = Depends(get_api_state)) -> WakeStatusResponse:
    mode = state.resident_voice.mode() if state.resident_voice is not None else "ptt-only"
    if mode == "ptt-only":
        raise HTTPException(
            status_code=409,
            detail="wake monitor cannot start while resident voice mode is ptt-only",
        )
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


@router.post("/status/resident-voice/start", response_model=ResidentVoiceStatusResponse)
def start_resident_voice_stream(state: ApiState = Depends(get_api_state)) -> ResidentVoiceStatusResponse:
    if state.resident_audio_stream is None:
        raise HTTPException(status_code=409, detail="resident audio stream is not configured")
    state.resident_audio_stream.start()
    bind_session(state, state.session_manager)
    state.session_service.replace_engine(state.engine)
    return build_resident_voice_status(state)


@router.post("/status/resident-voice/stop", response_model=ResidentVoiceStatusResponse)
def stop_resident_voice_stream(state: ApiState = Depends(get_api_state)) -> ResidentVoiceStatusResponse:
    if state.resident_audio_stream is None:
        raise HTTPException(status_code=409, detail="resident audio stream is not configured")
    state.resident_audio_stream.stop()
    bind_session(state, state.session_manager)
    state.session_service.replace_engine(state.engine)
    return build_resident_voice_status(state)


@router.put("/status/resident-voice/mode", response_model=ResidentVoiceStatusResponse)
def set_resident_voice_mode(
    request: ResidentVoiceModeRequest,
    state: ApiState = Depends(get_api_state),
) -> ResidentVoiceStatusResponse:
    if state.resident_voice is None:
        raise HTTPException(status_code=409, detail="resident voice invocation service is unavailable")
    try:
        mode = state.resident_voice.set_mode(request.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if mode == "ptt-only":
        state.wake_monitor.stop()
    return build_resident_voice_status(state)


@router.put("/status/resident-voice/tts-voice", response_model=ResidentVoiceStatusResponse)
def set_resident_voice_tts_voice(
    request: ResidentVoiceTTSVoiceRequest,
    state: ApiState = Depends(get_api_state),
) -> ResidentVoiceStatusResponse:
    try:
        voice = validate_tts_voice(request.voice)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _apply_tts_voice(state, voice)
    return build_resident_voice_status(state)


def build_resident_voice_status(
    state: ApiState,
    *,
    wake: WakeMonitorStatus | None = None,
    mode: str | None = None,
) -> ResidentVoiceStatusResponse:
    stream = state.resident_audio_stream
    stream_status = stream.status() if stream is not None else None
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
    if stream is not None and not stream_running:
        degraded_reasons.append("resident audio stream is stopped")
    mode = mode or (state.resident_voice.mode() if state.resident_voice is not None else "ptt-only")
    wake = _reconcile_resident_wake(state, wake or state.session_service.wake_status(), mode=mode)
    follow_up = state.resident_voice.follow_up_status() if state.resident_voice is not None else None
    barge_in_wired = bool(
        stream_running
        and vad_configured
        and getattr(state.engine, "barge_in_detector", None) is not None
        and getattr(state.engine, "interruption_audio_chunks", None) is not None
    )
    barge_in_supported = barge_in_wired and mode in {"hands-free", "continuous"}
    tts_voice = _tts_voice_response(state)
    supported_voices = tts_voice.get("supported_voices")
    return ResidentVoiceStatusResponse(
        mode=mode,
        available=state.resident_voice is not None
        and stream is not None
        and stream_running
        and vad_configured
        and not degraded_reasons,
        degraded_reasons=degraded_reasons,
        stream=ResidentVoiceStreamStatus(
            present=stream is not None,
            running=stream_running,
            subscribers=stream_status.subscribers if stream_status is not None else 0,
            buffer_chunks=stream_status.buffer_chunks if stream_status is not None else 0,
            dropped_chunks=stream_status.dropped_chunks if stream_status is not None else 0,
            last_error=stream_status.last_error if stream_status is not None else None,
        ),
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
        barge_in_supported=barge_in_supported,
        barge_in_wired=barge_in_wired,
        follow_up_listening=follow_up.listening if follow_up is not None else False,
        follow_up_source=follow_up.source if follow_up is not None else None,
        continuous_active=follow_up.continuous_active if follow_up is not None else False,
        tts_voice=str(tts_voice.get("voice") or "") or None,
        tts_supported_voices=[str(voice) for voice in supported_voices] if isinstance(supported_voices, list) else [],
        tts_voice_restart_required=bool(tts_voice.get("restart_required", True)),
        tts_voice_model=str(tts_voice.get("model") or "") or None,
    )


def _configured_wake_status(state: ApiState) -> WakeMonitorStatus:
    _device, available, reason = state.readiness["wake"]
    return state.session_service.configure_wake_status(provider="openwakeword", available=available, reason=reason)


def _reconcile_resident_wake(
    state: ApiState,
    wake: WakeMonitorStatus,
    *,
    mode: str | None = None,
) -> WakeMonitorStatus:
    resident_mode = mode or (state.resident_voice.mode() if state.resident_voice is not None else "ptt-only")
    if resident_mode == "ptt-only" and (wake.active or wake.monitoring):
        return replace(wake, reason="wake monitor is active while resident voice mode is ptt-only")
    return wake


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


def _apply_tts_voice(state: ApiState, voice: str) -> None:
    runtimes = [state.tts, getattr(state.engine, "tts", None), getattr(state.session_service.engine(), "tts", None)]
    seen: set[int] = set()
    for runtime in runtimes:
        if runtime is None or id(runtime) in seen:
            continue
        seen.add(id(runtime))
        # Kokoro runtimes expose a settable voice; other TTSBase runtimes
        # simply gain the attribute without effect.
        runtime.voice = voice


def _tts_voice_response(state: ApiState) -> dict[str, object]:
    try:
        return tts_voice_config(active_voice=getattr(state.tts, "voice", None))
    except Exception:
        return {"voice": None, "supported_voices": [], "restart_required": False, "model": None}
