from __future__ import annotations

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    client_id: str | None = None


class CreateSessionResponse(BaseModel):
    session_id: str
    state: str
    turn_count: int


class LatestTurnSummary(BaseModel):
    turn_id: str
    session_id: str
    input_modality: str
    final_state: str
    failure_reason: str | None = None
    degraded_reason: str | None = None
    tts_output_device: str | None = None
    raw_audio_path: str | None = None
    artifact_path: str | None = None
    runtime_context: dict[str, object] | None = None
    phase_durations_ms: dict[str, float] | None = None
    failure_phase: str | None = None


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
    latest_turn: LatestTurnSummary | None = None
    voice_capture_diagnostics: dict[str, object] | None = None
    failure_phase: str | None = None


class CloseSessionRequest(BaseModel):
    session_id: str
    final_state: str = "IDLE"


class CloseSessionResponse(BaseModel):
    session_id: str
    closed: bool
    artifact_path: str
