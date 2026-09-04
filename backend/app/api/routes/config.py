from __future__ import annotations

from dataclasses import asdict

from backend.app.actions import catalog
from backend.app.api.dependencies import get_optional_capability_service
from backend.app.api.schemas.config import (
    OperatorConfigResponse,
    OperatorConfigWriteRequest,
    OperatorConfigWriteResponse,
)
from backend.app.services.capability_service import CapabilityService, record_operator_action
from backend.app.services.operator_config_service import (
    ENV_FILE,
    OPERATOR_FIELD_SPECS,
    OperatorConfigError,
    OperatorConfigService,
    OperatorFieldSpec,
)
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()

__all__ = ["ENV_FILE", "OPERATOR_FIELD_SPECS", "OperatorFieldSpec", "router"]

_service = OperatorConfigService()


def _execute(operation):
    try:
        return operation()
    except OperatorConfigError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": exc.error}) from exc


@router.get("/config/operator", response_model=OperatorConfigResponse)
def get_operator_config() -> OperatorConfigResponse:
    view = _execute(lambda: _service.read(env_file=ENV_FILE))
    return OperatorConfigResponse.model_validate(asdict(view))


@router.post("/config/operator", response_model=OperatorConfigWriteResponse)
def write_operator_config(
    request: OperatorConfigWriteRequest,
    actions: CapabilityService | None = Depends(get_optional_capability_service),
) -> OperatorConfigWriteResponse:
    with record_operator_action(actions, catalog.OPERATOR_CONFIG_WRITE, {"fields": request.fields}):
        view = _execute(lambda: _service.write(request.fields, env_file=ENV_FILE))
    return OperatorConfigWriteResponse.model_validate(asdict(view))
