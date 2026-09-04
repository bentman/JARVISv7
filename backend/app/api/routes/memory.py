from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import TypeVar

from backend.app.actions import catalog
from backend.app.api.dependencies import (
    get_memory_service,
    get_optional_capability_service,
)
from backend.app.api.schemas.memory import (
    ArtifactRetentionPolicyResponse,
    MemoryCorrectionRequest,
    MemoryCorrectionResponse,
    MemoryCurationStatusResponse,
    MemoryDetailResponse,
    MemoryLayerCatalogResponse,
    MemoryLifecycleRequest,
    MemoryPolicyResponse,
    MemoryPolicyUpdateRequest,
    MemoryRecordPageResponse,
    MemoryRecordResponse,
)
from backend.app.memory.curation import LifecycleState
from backend.app.memory.curation_contract import GovernedMemoryKind
from backend.app.services.capability_service import CapabilityService, execute_operator_action
from backend.app.services.memory_service import (
    DEFAULT_DETAIL_ITEMS,
    MAX_DETAIL_ITEMS,
    MAX_PAGE_LIMIT,
    MAX_PAGE_OFFSET,
    MemoryService,
    MemoryServiceError,
)
from fastapi import APIRouter, Depends, HTTPException, Path, Query

router = APIRouter(prefix="/memory")
T = TypeVar("T")


def _execute(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except MemoryServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "memory operation failed",
            },
        ) from exc


@router.get("/policy", response_model=MemoryPolicyResponse)
def read_memory_policy(
    service: MemoryService = Depends(get_memory_service),
) -> MemoryPolicyResponse:
    return MemoryPolicyResponse.model_validate(asdict(_execute(service.read_policy)))


@router.get("/layers", response_model=MemoryLayerCatalogResponse)
def read_memory_layers(
    service: MemoryService = Depends(get_memory_service),
) -> MemoryLayerCatalogResponse:
    return MemoryLayerCatalogResponse.model_validate(asdict(_execute(service.read_layer_catalog)))


@router.get("/retention/policy", response_model=ArtifactRetentionPolicyResponse)
def read_artifact_retention_policy(
    service: MemoryService = Depends(get_memory_service),
) -> ArtifactRetentionPolicyResponse:
    return ArtifactRetentionPolicyResponse.model_validate(
        asdict(_execute(service.read_artifact_retention_policy))
    )


@router.put("/policy", response_model=MemoryPolicyResponse)
def update_memory_policy(
    request: MemoryPolicyUpdateRequest,
    service: MemoryService = Depends(get_memory_service),
    actions: CapabilityService | None = Depends(get_optional_capability_service),
) -> MemoryPolicyResponse:
    result = _execute(
        lambda: execute_operator_action(
            actions,
            catalog.MEMORY_POLICY_UPDATE,
            {
                "automatic_curation_enabled": request.automatic_curation_enabled,
                "expected_revision": request.expected_revision,
            },
            lambda: service.update_policy(
                automatic_curation_enabled=request.automatic_curation_enabled,
                expected_revision=request.expected_revision,
            ),
        )
    )
    return MemoryPolicyResponse.model_validate(asdict(result))


@router.get("/curation/status", response_model=MemoryCurationStatusResponse)
def read_memory_curation_status(
    service: MemoryService = Depends(get_memory_service),
) -> MemoryCurationStatusResponse:
    return MemoryCurationStatusResponse.model_validate(asdict(_execute(service.curation_status)))


@router.get("", response_model=MemoryRecordPageResponse)
def list_memory(
    state: LifecycleState | None = Query(default=None),
    kind: GovernedMemoryKind | None = Query(default=None),
    query: str | None = Query(default=None, min_length=1, max_length=240),
    offset: int = Query(default=0, ge=0, le=MAX_PAGE_OFFSET),
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_LIMIT),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryRecordPageResponse:
    result = _execute(
        lambda: service.list_records(
            state=state,
            kind=kind,
            query=query,
            offset=offset,
            limit=limit,
        )
    )
    return MemoryRecordPageResponse.model_validate(asdict(result))


@router.get("/{fact_id}", response_model=MemoryDetailResponse)
def read_memory(
    fact_id: str = Path(min_length=1, max_length=128),
    evidence_limit: int = Query(
        default=DEFAULT_DETAIL_ITEMS,
        ge=1,
        le=MAX_DETAIL_ITEMS,
    ),
    events_limit: int = Query(
        default=DEFAULT_DETAIL_ITEMS,
        ge=1,
        le=MAX_DETAIL_ITEMS,
    ),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryDetailResponse:
    result = _execute(
        lambda: service.read_record(
            fact_id,
            evidence_limit=evidence_limit,
            events_limit=events_limit,
        )
    )
    return MemoryDetailResponse.model_validate(asdict(result))


@router.post("/{fact_id}/confirm", response_model=MemoryRecordResponse)
def confirm_memory(
    request: MemoryLifecycleRequest,
    fact_id: str = Path(min_length=1, max_length=128),
    service: MemoryService = Depends(get_memory_service),
    actions: CapabilityService | None = Depends(get_optional_capability_service),
) -> MemoryRecordResponse:
    result = _execute(
        lambda: execute_operator_action(
            actions,
            catalog.MEMORY_RECORD_CONFIRM,
            {"fact_id": fact_id, "expected_revision": request.expected_revision},
            lambda: service.confirm(
                fact_id,
                expected_revision=request.expected_revision,
                reason=request.reason,
            ),
        )
    )
    return MemoryRecordResponse.model_validate(asdict(result))


@router.post("/{fact_id}/correct", response_model=MemoryCorrectionResponse)
def correct_memory(
    request: MemoryCorrectionRequest,
    fact_id: str = Path(min_length=1, max_length=128),
    service: MemoryService = Depends(get_memory_service),
    actions: CapabilityService | None = Depends(get_optional_capability_service),
) -> MemoryCorrectionResponse:
    result = _execute(
        lambda: execute_operator_action(
            actions,
            catalog.MEMORY_RECORD_CORRECT,
            {"fact_id": fact_id, "expected_revision": request.expected_revision},
            lambda: service.correct(
                fact_id,
                expected_revision=request.expected_revision,
                replacement_text=request.replacement_text,
                replacement_value=request.replacement_value,
                reason=request.reason,
            ),
        )
    )
    return MemoryCorrectionResponse.model_validate(asdict(result))


@router.post("/{fact_id}/dispute", response_model=MemoryRecordResponse)
def dispute_memory(
    request: MemoryLifecycleRequest,
    fact_id: str = Path(min_length=1, max_length=128),
    service: MemoryService = Depends(get_memory_service),
    actions: CapabilityService | None = Depends(get_optional_capability_service),
) -> MemoryRecordResponse:
    result = _execute(
        lambda: execute_operator_action(
            actions,
            catalog.MEMORY_RECORD_DISPUTE,
            {"fact_id": fact_id, "expected_revision": request.expected_revision},
            lambda: service.dispute(
                fact_id,
                expected_revision=request.expected_revision,
                reason=request.reason,
            ),
        )
    )
    return MemoryRecordResponse.model_validate(asdict(result))


@router.delete("/{fact_id}", response_model=MemoryDetailResponse)
def forget_memory(
    fact_id: str = Path(min_length=1, max_length=128),
    expected_revision: int = Query(ge=1),
    reason: str | None = Query(default=None, min_length=1, max_length=256),
    service: MemoryService = Depends(get_memory_service),
    actions: CapabilityService | None = Depends(get_optional_capability_service),
) -> MemoryDetailResponse:
    result = _execute(
        lambda: execute_operator_action(
            actions,
            catalog.MEMORY_RECORD_FORGET,
            {"fact_id": fact_id, "expected_revision": expected_revision},
            lambda: service.forget(
                fact_id,
                expected_revision=expected_revision,
                reason=reason,
            ),
        )
    )
    return MemoryDetailResponse.model_validate(asdict(result))
