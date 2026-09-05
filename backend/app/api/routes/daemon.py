from __future__ import annotations

import os
import signal

from backend.app.api.schemas.daemon import DaemonShutdownResponse, DaemonStatusResponse
from backend.app.services.daemon_registry import DAEMON_SERVICE, DaemonRegistry
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

router = APIRouter(prefix="/daemon")


def _default_shutdown() -> None:
    os.kill(os.getpid(), signal.SIGINT)


def _registry(request: Request) -> DaemonRegistry:
    registry = getattr(request.app.state, "daemon_registry", None)
    if registry is None:
        registry = DaemonRegistry()
        request.app.state.daemon_registry = registry
    return registry


def _request_token(request: Request) -> str | None:
    bearer = request.headers.get("authorization", "")
    if bearer.lower().startswith("bearer "):
        return bearer[7:].strip()
    return request.headers.get("x-jarvis-daemon-token")


@router.get("/status", response_model=DaemonStatusResponse)
def daemon_status(request: Request) -> DaemonStatusResponse:
    return DaemonStatusResponse(**_registry(request).status())


@router.post("/shutdown", response_model=DaemonShutdownResponse)
def daemon_shutdown(request: Request, background_tasks: BackgroundTasks) -> DaemonShutdownResponse:
    registry = _registry(request)
    if not registry.validate_token(_request_token(request)):
        raise HTTPException(status_code=401, detail="invalid daemon token")

    shutdown = getattr(request.app.state, "daemon_shutdown", None)
    if shutdown is None:
        shutdown = _default_shutdown
    background_tasks.add_task(shutdown)
    return DaemonShutdownResponse(accepted=True, service=DAEMON_SERVICE)
