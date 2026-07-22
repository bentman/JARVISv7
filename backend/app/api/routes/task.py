from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.dependencies import get_session_service
from backend.app.api.schemas.task import (
    SearchSource,
    TextTurnRequest,
    TextTurnResponse,
    TurnSearchSummaryPayload,
)
from backend.app.conversation.engine import TurnResult
from backend.app.services import turn_service
from backend.app.services.internet_search_service import TurnSearchSummary
from backend.app.services.session_service import SessionService

router = APIRouter()


def search_summary_payload(summary: TurnSearchSummary | None) -> TurnSearchSummaryPayload | None:
    if summary is None:
        return None
    return TurnSearchSummaryPayload(
        requested=summary.requested,
        status=summary.status,
        provider=summary.provider,
        sources=[SearchSource(title=item.title, url=item.url, provider=item.source) for item in summary.sources],
        reason=summary.reason,
    )


def text_turn_response(result: TurnResult) -> TextTurnResponse:
    return TextTurnResponse(
        turn_id=result.turn_id,
        session_id=result.session_id,
        transcript=result.transcript,
        response_text=result.response_text,
        final_state=result.final_state.value,
        failure_reason=result.failure_reason,
        active_personality_profile_id=result.active_personality_profile_id,
        profile_epoch=result.profile_epoch,
        search=search_summary_payload(result.search_summary),
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
