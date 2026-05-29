from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.app import ApiState
from backend.app.api.dependencies import get_api_state, get_session_service
from backend.app.api.schemas.session import (
    CloseSessionRequest,
    CloseSessionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    SessionStatusResponse,
)
from backend.app.services.session_service import SessionService

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
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="session_id is not active")
    return CloseSessionResponse(
        session_id=result.session_id,
        closed=result.closed,
        artifact_path=str(result.artifact_path),
    )


@router.get("/session/status", response_model=SessionStatusResponse)
def session_status(session_service: SessionService = Depends(get_session_service)) -> SessionStatusResponse:
    status = session_service.status()
    return _session_status_response(status)


@router.post("/session/ptt", response_model=SessionStatusResponse)
def invoke_ptt(state: ApiState = Depends(get_api_state)) -> SessionStatusResponse:
    if state.resident_voice is None:
        raise HTTPException(status_code=503, detail="resident voice invocation is unavailable")
    return _session_status_response(state.resident_voice.ptt())


def _session_status_response(status) -> SessionStatusResponse:
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
    )
