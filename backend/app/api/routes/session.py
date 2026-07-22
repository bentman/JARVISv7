from __future__ import annotations

from backend.app.api.app import ApiState
from backend.app.api.dependencies import get_api_state, get_session_service
from backend.app.api.schemas.session import (
    CloseSessionRequest,
    CloseSessionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    LatestTurnSummary,
    SessionStatusResponse,
)
from backend.app.api.routes.task import search_summary_payload
from backend.app.services.session_service import SessionService
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.post("/session/create", response_model=CreateSessionResponse)
def create_session(
    request: CreateSessionRequest,
    session_service: SessionService = Depends(get_session_service),
) -> CreateSessionResponse:
    status = session_service.start_session(request.client_id)
    return CreateSessionResponse(
        session_id=status.session_id or "",
        state=status.state,
        turn_count=status.turn_count,
    )


@router.post("/session/close", response_model=CloseSessionResponse)
def close_session(
    request: CloseSessionRequest,
    session_service: SessionService = Depends(get_session_service),
) -> CloseSessionResponse:
    try:
        result = session_service.end_session(request.session_id, request.final_state)
    except ValueError:
        raise HTTPException(status_code=404, detail="session_id is not active") from None
    return CloseSessionResponse(
        session_id=result.session_id,
        closed=result.closed,
        artifact_path=str(result.artifact_path),
    )


@router.get("/session/status", response_model=SessionStatusResponse)
def session_status(session_service: SessionService = Depends(get_session_service)) -> SessionStatusResponse:
    status = session_service.status()
    return build_session_status_response(status)


@router.post("/session/ptt", response_model=SessionStatusResponse)
def invoke_ptt(state: ApiState = Depends(get_api_state)) -> SessionStatusResponse:
    if state.resident_voice is None:
        raise HTTPException(status_code=503, detail="resident voice invocation is unavailable")
    return build_session_status_response(state.resident_voice.ptt())


def build_session_status_response(status) -> SessionStatusResponse:
    latest_turn = None
    if status.latest_turn is not None:
        latest_turn = LatestTurnSummary(
            turn_id=status.latest_turn.turn_id,
            session_id=status.latest_turn.session_id,
            input_modality=status.latest_turn.input_modality,
            final_state=status.latest_turn.final_state,
            failure_reason=status.latest_turn.failure_reason,
            degraded_reason=status.latest_turn.degraded_reason,
            tts_output_device=status.latest_turn.tts_output_device,
            raw_audio_path=status.latest_turn.raw_audio_path,
            artifact_path=status.latest_turn.artifact_path,
            runtime_context=status.latest_turn.runtime_context,
            phase_durations_ms=status.latest_turn.phase_durations_ms,
            failure_phase=status.latest_turn.failure_phase,
        )
    return SessionStatusResponse(
        session_id=status.session_id,
        active=status.active,
        state=status.state,
        turn_count=status.turn_count,
        last_transcript=status.last_transcript,
        last_response=status.last_response,
        failure_reason=status.failure_reason,
        invocation_source=status.invocation_source,
        tts_output_device=status.tts_output_device,
        latest_turn=latest_turn,
        voice_capture_diagnostics=status.voice_capture_diagnostics,
        failure_phase=status.failure_phase,
        search=search_summary_payload(status.search),
    )
