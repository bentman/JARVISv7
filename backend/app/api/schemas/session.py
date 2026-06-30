from __future__ import annotations

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    client_id: str | None = None


class CreateSessionResponse(BaseModel):
    session_id: str
    state: str
    turn_count: int


class SessionStatusResponse(BaseModel):
    session_id: str | None
    active: bool
    state: str
    turn_count: int
    last_transcript: str | None = None
    last_response: str | None = None
    failure_reason: str | None = None
    invocation_source: str | None = None
    tts_output_device: str | None = None
    voice_capture_diagnostics: dict[str, object] | None = None


class CloseSessionRequest(BaseModel):
    session_id: str
    final_state: str = "IDLE"


class CloseSessionResponse(BaseModel):
    session_id: str
    closed: bool
    artifact_path: str
