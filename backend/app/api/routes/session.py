from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.app import ApiState, build_engine
from backend.app.api.dependencies import get_api_state
from backend.app.api.schemas.session import (
    CloseSessionRequest,
    CloseSessionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
)
from backend.app.conversation.session_manager import SessionManager

router = APIRouter()


@router.post("/session/create", response_model=CreateSessionResponse)
def create_session(
    request: CreateSessionRequest,
    state: ApiState = Depends(get_api_state),
) -> CreateSessionResponse:
    _ = request
    state.session_manager = SessionManager()
    state.engine = build_engine(state, state.session_manager)
    return CreateSessionResponse(
        session_id=state.session_manager.session_id,
        state="IDLE",
        turn_count=len(state.session_manager.turn_artifacts),
    )


@router.post("/session/close", response_model=CloseSessionResponse)
def close_session(
    request: CloseSessionRequest,
    state: ApiState = Depends(get_api_state),
) -> CloseSessionResponse:
    if request.session_id != state.session_manager.session_id:
        raise HTTPException(status_code=404, detail="session_id is not active")
    artifact_path = state.session_manager.close_session(request.final_state)
    return CloseSessionResponse(
        session_id=state.session_manager.session_id,
        closed=True,
        artifact_path=str(artifact_path),
    )