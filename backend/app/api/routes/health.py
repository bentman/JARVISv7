from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="jarvisv7-backend")