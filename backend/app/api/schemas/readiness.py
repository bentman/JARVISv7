from __future__ import annotations

from pydantic import BaseModel



class FamilyReadiness(BaseModel):
    family: str
    runtime: str
    device: str
    model: str
    ready: bool
    reason: str
    route: str | None = None
    serve_profile_id: str | None = None
    accelerator: str | None = None
    base_url: str | None = None
    selected_reason: str | None = None
    degraded_reason: str | None = None


class PreflightSummary(BaseModel):
    tokens_count: int
    probe_error_count: int


class ServiceReadiness(BaseModel):
    reachable: bool
    reason: str


class ReadinessResponse(BaseModel):
    status: str
    profile_id: str
    arch: str
    active_personality_profile_id: str
    active_llm_runtime: str
    requires_degraded_mode: bool
    families: dict[str, FamilyReadiness]
    preflight: PreflightSummary
    services: dict[str, ServiceReadiness]
