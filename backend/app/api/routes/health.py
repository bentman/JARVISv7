from __future__ import annotations

from backend.app.api.schemas.common import HealthResponse
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="jarvisv7-backend")
