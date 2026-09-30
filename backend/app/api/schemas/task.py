from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TextTurnRequest(BaseModel):
    text: str
    session_id: str | None = None
    # The client submitting the turn; recorded so every interface can tell where a turn came from.
    origin: Literal["desktop", "api"] = "api"


class TextTurnResponse(BaseModel):
    turn_id: str
    session_id: str
    transcript: str | None
    response_text: str | None
    final_state: str
    failure_reason: str | None = None
    active_personality_profile_id: str = "unknown"
    profile_epoch: int = 0
    search: dict[str, object] | None = None
    origin: str = "api"
    agent: dict[str, str] | None = None
