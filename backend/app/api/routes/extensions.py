from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any, TypeVar

from backend.app.actions import catalog
from backend.app.api.dependencies import (
    get_extension_service,
    get_optional_capability_service,
)
from backend.app.api.schemas.extensions import (
    ExtensionBodyResponse,
    ExtensionCatalogResponse,
    ExtensionErrorListResponse,
    ExtensionResponse,
    ExtensionStateRequest,
)
from backend.app.services.capability_service import CapabilityService, execute_operator_action
from backend.app.services.extension_service import ExtensionService, ExtensionServiceError
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/extensions")

T = TypeVar("T")


class ExtensionInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability_id: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ExtensionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=64)
    answer: dict[str, Any]


class ExtensionCredential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64)
    secret: str = Field(min_length=1, max_length=8000)


def get_runtime(request: Request):
    service = getattr(request.app.state.jarvis_state, "extension_runtime", None)
    if service is None:
        raise HTTPException(503, "extension runtime unavailable")
    return service


@router.get("/runs")
def list_extension_runs(service=Depends(get_runtime)):
    return {"runs": service.list_runs()}


@router.post("/runs/{run_id}/input")
def answer_extension_input(run_id: str, payload: ExtensionInput, service=Depends(get_runtime)):
    try:
        service.answer(run_id, payload.request_id, payload.answer)
        return {"accepted": True}
    except ValueError as exc:
        raise HTTPException(409, "extension input is no longer valid") from exc


@router.get("/{extension_id}/runtime")
def read_extension_runtime(extension_id: str, service=Depends(get_runtime)):
    return service.detail(extension_id)


@router.post("/{extension_id}/invoke")
def invoke_extension(extension_id: str, payload: ExtensionInvocation, service=Depends(get_runtime)):
    try:
        return asdict(service.invoke(extension_id, payload.capability_id, payload.arguments))
    except ValueError as exc:
        raise HTTPException(422, "invalid extension operation") from exc


@router.post("/{extension_id}/credentials")
def write_extension_credential(extension_id: str, payload: ExtensionCredential, service=Depends(get_runtime)):
    try:
        service.credential(extension_id, payload.name, payload.secret)
        return {"stored": True}
    except ValueError as exc:
        raise HTTPException(422, "invalid extension credential") from exc


def _execute(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except ExtensionServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "extension operation failed"},
        ) from exc


@router.get("", response_model=ExtensionCatalogResponse)
def list_extensions(
    service: ExtensionService = Depends(get_extension_service),
) -> ExtensionCatalogResponse:
    return ExtensionCatalogResponse.model_validate(asdict(_execute(service.catalog)))


@router.get("/errors", response_model=ExtensionErrorListResponse)
def list_extension_errors(
    service: ExtensionService = Depends(get_extension_service),
) -> ExtensionErrorListResponse:
    return ExtensionErrorListResponse.model_validate(asdict(_execute(service.errors)))


@router.get("/{extension_id}", response_model=ExtensionResponse)
def read_extension(
    extension_id: str = Path(min_length=1, max_length=128),
    service: ExtensionService = Depends(get_extension_service),
) -> ExtensionResponse:
    return ExtensionResponse.model_validate(asdict(_execute(lambda: service.read(extension_id))))


@router.get("/{extension_id}/body", response_model=ExtensionBodyResponse)
def read_extension_body(
    extension_id: str = Path(min_length=1, max_length=128),
    service: ExtensionService = Depends(get_extension_service),
) -> ExtensionBodyResponse:
    return ExtensionBodyResponse.model_validate(asdict(_execute(lambda: service.body(extension_id))))


@router.post("/{extension_id}/state", response_model=ExtensionResponse)
def set_extension_state(
    request: ExtensionStateRequest,
    extension_id: str = Path(min_length=1, max_length=128),
    service: ExtensionService = Depends(get_extension_service),
    actions: CapabilityService | None = Depends(get_optional_capability_service),
) -> ExtensionResponse:
    view = _execute(
        lambda: execute_operator_action(
            actions,
            catalog.EXTENSION_STATE_UPDATE,
            {"extension_id": extension_id, "state": request.state},
            lambda: service.set_state(
                extension_id=extension_id,
                state=request.state,
                expected_revision=request.expected_revision,
                reason=request.reason,
            ),
        )
    )
    return ExtensionResponse.model_validate(asdict(view))
