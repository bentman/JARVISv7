from __future__ import annotations

from pydantic import BaseModel


class AgentSpecStatusResponse(BaseModel):
    spec_id: str
    display_name: str
    kind: str
    enabled: bool
    policy_allowed: bool
    allowed_tools: list[str]


class AgentsStatusResponse(BaseModel):
    enabled: bool
    read_only: bool
    reason: str
    allowed_roles: list[str]
    allowed_tools: list[str]
    known_specs: list[AgentSpecStatusResponse]


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
