from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.dependencies import get_session_service
from backend.app.api.schemas.task import TextTurnRequest, TextTurnResponse
from backend.app.conversation.engine import TurnResult
from backend.app.services import task_service
from backend.app.services.session_service import SessionService

router = APIRouter()


def text_turn_response(result: TurnResult) -> TextTurnResponse:
    return TextTurnResponse(
        turn_id=result.turn_id,
        session_id=result.session_id,
        transcript=result.transcript,
        response_text=result.response_text,
        final_state=result.final_state.value,
        failure_reason=result.failure_reason,
    )


@router.post("/task/text", response_model=TextTurnResponse)
def text_turn(request: TextTurnRequest, session_service: SessionService = Depends(get_session_service)) -> TextTurnResponse:
    try:
        session_service.assert_active_session(request.session_id)
        result = task_service.submit_text(request.text, engine=session_service.engine())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return text_turn_response(result)