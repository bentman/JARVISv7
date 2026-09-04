from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CapabilityResponse(StrictActionModel):
    capability_id: str
    effect_class: str
    readiness: str
    availability: str
    authorization_rule: str
    approval_mode: str
    execution_owner: str
    unavailable_explanation: str
    input_schema: dict[str, Any]
    result_schema: dict[str, Any]
    timeout_policy: dict[str, Any]
    cancellation_policy: dict[str, Any]
    executable: bool


class CapabilityCatalogResponse(StrictActionModel):
    capabilities: list[CapabilityResponse]


class ActionProposalRequest(StrictActionModel):
    capability_id: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=256)
    proposed_by: Literal["operator", "model"] = "operator"


class ActionDecisionRequest(StrictActionModel):
    outcome: Literal["approved", "denied"]
    reason: str | None = Field(default=None, max_length=256)


class ActionProposalResponse(StrictActionModel):
    proposal_id: str
    capability_id: str
    status: str
    outcome: str
    reason: str
    arguments: dict[str, Any]
    approval_id: str | None = None
    expires_at: str | None = None
    execution: dict[str, Any] | None = None


class PendingApprovalResponse(StrictActionModel):
    proposal_id: str
    capability_id: str
    approval_id: str
    arguments: dict[str, Any]
    reason: str
    expires_at: str


class PendingApprovalListResponse(StrictActionModel):
    pending: list[PendingApprovalResponse]


class ActionCancelResponse(StrictActionModel):
    proposal_id: str
    cancelled: bool


class ActionAuditResponse(StrictActionModel):
    records: list[dict[str, Any]]
