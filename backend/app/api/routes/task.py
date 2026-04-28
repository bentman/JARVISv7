from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.dependencies import get_engine
from backend.app.api.schemas.task import TextTurnRequest, TextTurnResponse
from backend.app.conversation.engine import TurnEngine, TurnResult
from backend.app.services import task_service

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
def text_turn(request: TextTurnRequest, engine: TurnEngine = Depends(get_engine)) -> TextTurnResponse:
    _ = request.session_id
    try:
        result = task_service.submit_text(request.text, engine=engine)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return text_turn_response(result)