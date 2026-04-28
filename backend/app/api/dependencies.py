from __future__ import annotations

from fastapi import Request

from backend.app.api.app import ApiState
from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.core.capabilities import FullCapabilityReport, HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.personality.schema import PersonalityProfile


def get_api_state(request: Request) -> ApiState:
    return request.app.state.jarvis_state


def get_engine(request: Request) -> TurnEngine:
    return get_api_state(request).engine


def get_session_manager(request: Request) -> SessionManager:
    return get_api_state(request).session_manager


def get_personality(request: Request) -> PersonalityProfile:
    return get_api_state(request).personality


def get_preflight(request: Request) -> PreflightResult:
    return get_api_state(request).preflight


def get_profile(request: Request) -> HardwareProfile:
    return get_api_state(request).profile


def get_capability_report(request: Request) -> FullCapabilityReport:
    return get_api_state(request).report