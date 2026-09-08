from __future__ import annotations

import logging
from typing import Any

from backend.app.api.app import ApiState
from backend.app.api.dependencies import get_api_state
from backend.app.api.schemas.acp_server import (
    AcpServerStartRequest,
    AcpServerStartResponse,
    AcpServerStatusResponse,
    AcpServerStopResponse,
    AcpSessionInfo,
    AcpSessionListResponse,
)
from backend.app.extensions.acp_server import AcpServer, AcpServerConfig
from fastapi import APIRouter, Depends, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/acp/server")

_SERVER_KEY = "_acp_server"


def _get_server(request: Request) -> AcpServer | None:
    return getattr(request.app.state, _SERVER_KEY, None)


def _get_or_create_server(request: Request, state: ApiState) -> AcpServer:
    server = _get_server(request)
    if server is not None:
        return server
    server = AcpServer(
        config=AcpServerConfig(),
        turn_engine_getter=lambda: getattr(request.app.state.jarvis_state, "engine", None),
    )
    setattr(request.app.state, _SERVER_KEY, server)
    return server


@router.get("/status", response_model=AcpServerStatusResponse)
def acp_server_status(
    request: Request,
    state: ApiState = Depends(get_api_state),
) -> AcpServerStatusResponse:
    server = _get_server(request)
    if server is None:
        return AcpServerStatusResponse(
            running=False,
            port=None,
            host=None,
            active_sessions=0,
            max_sessions=0,
            allowed_tools=[],
        )
    info = server.status()
    return AcpServerStatusResponse.model_validate(info)


@router.post("/start", response_model=AcpServerStartResponse)
def acp_server_start(
    body: AcpServerStartRequest,
    request: Request,
    state: ApiState = Depends(get_api_state),
) -> AcpServerStartResponse:
    server = _get_server(request)
    if server is not None and server.status()["running"]:
        raise HTTPException(status_code=409, detail={"error": "already_running", "message": "ACP server is already running"})

    config = AcpServerConfig(
        host=body.host,
        port=body.port,
        max_sessions=body.max_sessions,
        session_timeout_ms=body.session_timeout_ms,
        allowed_tools=tuple(body.allowed_tools),
    )
    def engine_getter() -> Any:
        return getattr(request.app.state.jarvis_state, "engine", None)

    server = AcpServer(config=config, turn_engine_getter=engine_getter)
    setattr(request.app.state, _SERVER_KEY, server)
    try:
        port = server.start()
    except RuntimeError as exc:
        setattr(request.app.state, _SERVER_KEY, None)
        raise HTTPException(status_code=500, detail={"error": "start_failed", "message": str(exc)}) from exc

    return AcpServerStartResponse(running=True, port=port, host=body.host)


@router.post("/stop", response_model=AcpServerStopResponse)
def acp_server_stop(
    request: Request,
    state: ApiState = Depends(get_api_state),
) -> AcpServerStopResponse:
    server = _get_server(request)
    if server is None:
        return AcpServerStopResponse(running=False, closed_sessions=0)
    closed = server.stop()
    setattr(request.app.state, _SERVER_KEY, None)
    return AcpServerStopResponse(running=False, closed_sessions=closed)


@router.get("/sessions", response_model=AcpSessionListResponse)
def acp_server_sessions(
    request: Request,
    state: ApiState = Depends(get_api_state),
) -> AcpSessionListResponse:
    server = _get_server(request)
    if server is None:
        return AcpSessionListResponse(sessions=[])
    raw = server.list_sessions()
    return AcpSessionListResponse(
        sessions=[AcpSessionInfo.model_validate(s) for s in raw]
    )
