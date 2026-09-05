from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import TypeVar

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
from fastapi import APIRouter, Depends, HTTPException, Path

router = APIRouter(prefix="/extensions")

T = TypeVar("T")


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
