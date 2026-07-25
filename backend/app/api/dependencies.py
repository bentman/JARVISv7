from __future__ import annotations

from backend.app.api.app import ApiState
from backend.app.services.memory_service import MemoryService
from backend.app.services.session_service import SessionService
from fastapi import HTTPException, Request


def get_api_state(request: Request) -> ApiState:
    return request.app.state.jarvis_state


def get_session_service(request: Request) -> SessionService:
    return get_api_state(request).session_service


def get_memory_service(request: Request) -> MemoryService:
    service = get_api_state(request).memory_service
    if service is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "unavailable",
                "message": "memory service is unavailable",
            },
        )
    return service
