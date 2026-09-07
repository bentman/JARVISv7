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


class AgentListResponse(StrictAgentModel):
    agents: list[AgentProfileResponse]


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


class AgentRunResponse(StrictAgentModel):
    records: list[dict[str, Any]]
