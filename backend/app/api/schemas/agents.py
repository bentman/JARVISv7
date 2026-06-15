from __future__ import annotations

from pydantic import BaseModel


class AgentsStatusResponse(BaseModel):
    enabled: bool
    read_only: bool
    reason: str
    allowed_roles: list[str]
    allowed_tools: list[str]


class AgentTraceRecordResponse(BaseModel):
    record_id: str
    trace_id: str
    record_type: str
    payload: dict[str, object]
    role_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    parent_record_id: str | None = None
    created_at: str


class AgentTraceResponse(BaseModel):
    trace_id: str
    read_only: bool
    records: list[AgentTraceRecordResponse]
