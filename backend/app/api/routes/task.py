from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.dependencies import get_session_service
from backend.app.api.schemas.task import TextTurnRequest, TextTurnResponse
from backend.app.api.schemas.tools import ToolCallSummary
from backend.app.conversation.engine import TurnResult
from backend.app.services import turn_service
from backend.app.services.session_service import SessionService

router = APIRouter()


def text_turn_response(result: TurnResult) -> TextTurnResponse:
    tool_calls = None
    if result.tool_results:
        tool_calls = [
            ToolCallSummary(
                tool_name=str(item.get("tool_name", "")),
                tool_input=cast(dict[str, object], item.get("tool_input", {}))
                if isinstance(item.get("tool_input"), dict)
                else {},
                tool_output_summary=str(item.get("tool_output", ""))[:200],
                success=bool(item.get("success", False)),
            )
            for item in result.tool_results
        ]
    return TextTurnResponse(
        turn_id=result.turn_id,
        session_id=result.session_id,
        transcript=result.transcript,
        response_text=result.response_text,
        final_state=result.final_state.value,
        failure_reason=result.failure_reason,
        tool_calls=tool_calls,
        active_personality_profile_id=result.active_personality_profile_id,
        profile_epoch=result.profile_epoch,
    )


@router.post("/task/text", response_model=TextTurnResponse)
def text_turn(request: TextTurnRequest, session_service: SessionService = Depends(get_session_service)) -> TextTurnResponse:
    try:
        session_service.assert_active_session(request.session_id)
        result = turn_service.run_text_turn(request.text, engine=session_service.engine())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return text_turn_response(result)
