from __future__ import annotations

from dataclasses import asdict

from backend.app.api.app import ApiState
from backend.app.api.dependencies import get_api_state
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/memory/curation")


@router.post("/drain")
def drain_curation(state: ApiState = Depends(get_api_state)) -> dict[str, object]:
    if state.memory_curation_service is None:
        raise HTTPException(status_code=503, detail="memory curation is unavailable")
    return asdict(state.memory_curation_service.drain(timeout=8.0))
