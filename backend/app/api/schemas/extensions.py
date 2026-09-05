from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictExtensionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtensionResponse(StrictExtensionModel):
    extension_id: str
    family: str
    local_id: str
    version: str
    display_name: str
    source: str
    provenance: str
    trust: str
    state: str
    readiness: str
    availability: str
    unavailable_explanation: str
    dependencies: list[str]
    collisions: list[str]
    metadata_claims: dict[str, Any]
    revision: int | None = None
    body_available: bool = False


class ExtensionCatalogResponse(StrictExtensionModel):
    extensions: list[ExtensionResponse]
    families: dict[str, int]


class ExtensionLoadErrorResponse(StrictExtensionModel):
    family: str
    source: str
    reason: str


class ExtensionErrorListResponse(StrictExtensionModel):
    errors: list[ExtensionLoadErrorResponse]


class ExtensionStateRequest(StrictExtensionModel):
    state: Literal["enabled", "disabled", "retired"]
    expected_revision: int | None = Field(default=None, ge=1)
    reason: str | None = Field(default=None, max_length=256)


class ExtensionBodyResponse(StrictExtensionModel):
    extension_id: str
    body: str
