from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictAgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentProfileResponse(StrictAgentModel):
    profile_id: str
    display_name: str
    purpose: str
    instructions: str
    invocation_modes: tuple[str, ...]
    capability_ids: tuple[str, ...]
    memory_scope: str
    approval_class: str
    timeout_ms: int
    cancellable: bool
    output_contract: dict[str, Any]
    provider_model_policy: dict[str, Any]
    runtime: dict[str, Any]
    source: str
    editable: bool
    enabled: bool
    fingerprint: str


class AgentProfileProblem(StrictAgentModel):
    capability_id: str
    reason: str


class AgentListResponse(StrictAgentModel):
    agents: list[AgentProfileResponse]
    problems: list[AgentProfileProblem] = Field(default_factory=list)


class AgentProfileWriteRequest(StrictAgentModel):
    profile: dict[str, Any]
    expected_fingerprint: str | None = Field(default=None, min_length=1)


class AgentProfileWriteResponse(StrictAgentModel):
    profile_id: str
    source: str
    fingerprint: str


class AgentInvokeRequest(StrictAgentModel):
    profile_id: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=4096)


class AgentInvokeResponse(StrictAgentModel):
    agent_id: str
    status: str
    output: dict[str, Any]
    turn_id: str
    session_id: str
    error: str | None = None


class AgentToolChoice(StrictAgentModel):
    capability_id: str
    label: str
    needs_approval: bool
    available: bool


class AgentToolListResponse(StrictAgentModel):
    tools: list[AgentToolChoice]


class AgentRunResponse(StrictAgentModel):
    records: list[dict[str, Any]]
