from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictAcpServerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AcpServerStartRequest(StrictAcpServerModel):
    host: str = Field(default="127.0.0.1", min_length=1, max_length=256)
    port: int = Field(default=0, ge=0, le=65535)
    max_sessions: int = Field(default=5, ge=1, le=100)
    session_timeout_ms: int = Field(default=300000, ge=1000, le=3600000)
    allowed_tools: list[str] = Field(default_factory=list)


class AcpServerStatusResponse(StrictAcpServerModel):
    running: bool
    port: int | None = None
    host: str | None = None
    active_sessions: int = 0
    max_sessions: int = 0
    allowed_tools: list[str] = Field(default_factory=list)


class AcpServerStartResponse(StrictAcpServerModel):
    running: bool
    port: int
    host: str


class AcpServerStopResponse(StrictAcpServerModel):
    running: bool
    closed_sessions: int


class AcpSessionInfo(StrictAcpServerModel):
    session_id: str
    client_info: dict[str, Any]
    status: str
    created_at: str
    turn_ids: list[str]


class AcpSessionListResponse(StrictAcpServerModel):
    sessions: list[AcpSessionInfo]
