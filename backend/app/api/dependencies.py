from __future__ import annotations

from fastapi import Request

from backend.app.api.app import ApiState
from backend.app.services.session_service import SessionService


def get_api_state(request: Request) -> ApiState:
    return request.app.state.jarvis_state


def get_session_service(request: Request) -> SessionService:
    return get_api_state(request).session_service
