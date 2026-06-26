from __future__ import annotations

from pydantic import BaseModel


class WakeStatusResponse(BaseModel):
    provider: str
    available: bool
    reason: str
    active: bool = False
    enabled: bool = False
    monitoring: bool = False
    last_detected: str | None = None
    detection_count: int = 0
    last_error: str | None = None
    last_score: float | None = None
    threshold: float | None = None


class ResidentVoiceStreamStatus(BaseModel):
    present: bool
    running: bool
    subscribers: int
    buffer_chunks: int
    dropped_chunks: int
    last_error: str | None = None


class ResidentVoiceModeRequest(BaseModel):
    mode: str


class ResidentVoiceStatusResponse(BaseModel):
    mode: str
    available: bool
    degraded_reasons: list[str]
    stream: ResidentVoiceStreamStatus
    stream_present: bool
    stream_running: bool
    stream_subscribers: int
    stream_buffer_chunks: int
    stream_dropped_chunks: int
    stream_last_error: str | None = None
    vad_configured: bool
    ptt_supported: bool
    wake_supported: bool
    wake_active: bool
    wake_monitoring: bool
    barge_in_supported: bool
    barge_in_wired: bool
    follow_up_listening: bool = False
    follow_up_source: str | None = None
    continuous_active: bool = False
