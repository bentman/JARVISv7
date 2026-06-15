from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

AgentRole = Literal["planner", "executor", "critic", "curator", "learner"]
AgentMessageType = Literal["request", "response", "event", "plan", "outcome", "policy_decision"]
AgentRunMode = Literal["boundary", "dry_run"]


class AgentMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: uuid4().hex)
    trace_id: str
    role: AgentRole
    message_type: AgentMessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    parent_message_id: str | None = None


class AgentRequest(BaseModel):
    trace_id: str
    requested_role: AgentRole
    objective: str
    context: dict[str, Any] = Field(default_factory=dict)
    run_mode: AgentRunMode = "boundary"


class AgentResponse(BaseModel):
    trace_id: str
    responding_role: AgentRole
    status: Literal["accepted", "rejected", "recorded"]
    payload: dict[str, Any] = Field(default_factory=dict)
    run_mode: AgentRunMode = "boundary"
