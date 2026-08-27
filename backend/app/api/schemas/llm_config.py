from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class LLMProviderProfileWrite(BaseModel):
    name: str
    kind: str
    endpoint: str | None = None
    model: str | None = None
    context_window: int = 8192
    timeout_seconds: float = 60.0
    api_key: str | None = None
    clear_api_key: bool = False

    @model_validator(mode="after")
    def validate_secret_action(self) -> LLMProviderProfileWrite:
        if self.api_key and self.clear_api_key:
            raise ValueError("credential replace and delete cannot be requested together")
        return self


class LLMProviderProfileResponse(BaseModel):
    profile_id: str
    name: str
    kind: str
    endpoint: str | None
    model: str | None
    context_window: int
    timeout_seconds: float
    has_secret: bool
    builtin: bool
    cloud_eligible: bool
    readiness_state: str
    updated_at: str | None
    secret_updated_at: str | None


class LLMProviderSelectionWrite(BaseModel):
    primary_profile_id: str
    local_fallback_profile_id: str | None = None
    cloud_escalation_enabled: bool = False
    cloud_profile_id: str | None = None


class LLMProviderSelectionResponse(LLMProviderSelectionWrite):
    persisted: bool


class LLMProviderConfigResponse(BaseModel):
    profiles: list[LLMProviderProfileResponse]
    selection: LLMProviderSelectionResponse
    restart_required: bool = True


class LLMDiscoveredModel(BaseModel):
    id: str
    display_name: str | None = None
    context_window: int | None = None


class LLMProviderTestResponse(BaseModel):
    status: str
    reason: str
    models: list[LLMDiscoveredModel] = Field(default_factory=list)


class SecretRotationResponse(BaseModel):
    rotated: bool
