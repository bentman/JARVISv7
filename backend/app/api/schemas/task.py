from __future__ import annotations

from backend.app.api.schemas.tools import ToolCallSummary
from pydantic import BaseModel


class TextTurnRequest(BaseModel):
    text: str
    session_id: str | None = None


class TextTurnResponse(BaseModel):
    turn_id: str
    session_id: str
    transcript: str | None
    response_text: str | None
    final_state: str
    failure_reason: str | None = None
    tool_calls: list[ToolCallSummary] | None = None
    active_personality_profile_id: str = "unknown"
    profile_epoch: int = 0
