from __future__ import annotations

from pydantic import BaseModel


class VoiceTurnResponse(BaseModel):
    turn_id: str
    session_id: str
    transcript: str | None
    response_text: str | None
    final_state: str
    failure_reason: str | None = None
    tts_degraded: bool = False
    tts_degraded_reason: str | None = None
    interrupted: bool = False
    interruption_events: list[dict[str, object]]