from __future__ import annotations

from backend.app.api.app import ApiState
from backend.app.services.capability_service import CapabilityService
from backend.app.services.extension_service import ExtensionService
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


def get_capability_service(request: Request) -> CapabilityService:
    service = get_optional_capability_service(request)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "unavailable",
                "message": "capability service is unavailable",
            },
        )
    return service


def get_optional_capability_service(request: Request) -> CapabilityService | None:
    # Route tests mount a single router on a bare app, so app state may be absent.
    state = getattr(request.app.state, "jarvis_state", None)
    return getattr(state, "capability_service", None)


def get_extension_service(request: Request) -> ExtensionService:
    state = getattr(request.app.state, "jarvis_state", None)
    service = getattr(state, "extension_service", None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "unavailable",
                "message": "extension service is unavailable",
            },
        )
    return service
