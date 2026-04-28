from __future__ import annotations

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    client_id: str | None = None


class CreateSessionResponse(BaseModel):
    session_id: str
    state: str
    turn_count: int


class CloseSessionRequest(BaseModel):
    session_id: str
    final_state: str = "IDLE"


class CloseSessionResponse(BaseModel):
    session_id: str
    closed: bool
    artifact_path: str