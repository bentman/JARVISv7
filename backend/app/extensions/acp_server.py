from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_TURN_ENGINE_TIMEOUT_S = 30.0


@dataclass(frozen=True, slots=True)
class AcpServerConfig:
    host: str = "127.0.0.1"
    port: int = 0
    max_sessions: int = 5
    session_timeout_ms: int = 300_000
    allowed_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("host must be a non-empty string")
        if not (0 <= self.port <= 65535):
            raise ValueError(f"port must be between 0 and 65535, got {self.port}")
        if self.max_sessions < 1:
            raise ValueError(f"max_sessions must be >= 1, got {self.max_sessions}")
        if self.session_timeout_ms < 1:
            raise ValueError(f"session_timeout_ms must be >= 1, got {self.session_timeout_ms}")


@dataclass(slots=True)
class AcpServerSession:
    session_id: str
    client_info: dict[str, Any]
    status: str = "active"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    turn_ids: list[str] = field(default_factory=list)


class AcpServer:
    """Minimal inbound ACP server that accepts JSON-RPC-style messages over TCP."""

    def __init__(
        self,
        config: AcpServerConfig,
        turn_engine_getter: Callable[[], Any],
    ) -> None:
        self._config = config
        self._turn_engine_getter = turn_engine_getter
        self._sessions: dict[str, AcpServerSession] = {}
        self._server: asyncio.AbstractServer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._bound_port: int | None = None

    # -- lifecycle --

    def start(self) -> int:
        """Start the server in a daemon thread and return the bound port."""
        with self._lock:
            if self._server is not None:
                raise RuntimeError("ACP server is already running")
            ready = threading.Event()
            port_holder: list[int] = []
            error_holder: list[BaseException] = []

            def _run_loop() -> None:
                loop = asyncio.new_event_loop()
                self._loop = loop
                try:
                    loop.run_until_complete(self._start_and_wait(ready, port_holder, error_holder))
                except BaseException as exc:
                    error_holder.append(exc)
                    ready.set()
                finally:
                    with suppress(Exception):
                        loop.run_until_complete(loop.shutdown_asyncgens())
                    loop.close()

            thread = threading.Thread(target=_run_loop, name="acp-server", daemon=True)
            self._thread = thread
            thread.start()
            ready.wait(timeout=5.0)
            if error_holder:
                self._thread = None
                self._loop = None
                raise RuntimeError(f"ACP server failed to start: {error_holder[0]}") from error_holder[0]
            if not port_holder:
                self._thread = None
                self._loop = None
                raise RuntimeError("ACP server failed to bind within timeout")
            self._bound_port = port_holder[0]
            return self._bound_port

    def stop(self) -> int:
        """Stop the server and close all sessions. Return the number of closed sessions."""
        with self._lock:
            if self._server is None:
                return 0
            server = self._server
            loop = self._loop
            self._server = None

        closed = 0
        if loop is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._shutdown_server(server), loop)
            try:
                closed = future.result(timeout=5.0)
            except Exception:
                logger.exception("ACP server shutdown error")

        with self._lock:
            closed = max(closed, len(self._sessions))
            self._sessions.clear()
            self._bound_port = None
        return closed

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self._server is not None
            active = sum(1 for s in self._sessions.values() if s.status == "active")
            return {
                "running": running,
                "port": self._bound_port,
                "host": self._config.host if running else None,
                "active_sessions": active,
                "max_sessions": self._config.max_sessions,
                "allowed_tools": list(self._config.allowed_tools),
            }

    def list_sessions(self) -> list[dict[str, Any]]:
        self._cleanup_expired()
        with self._lock:
            return [
                {
                    "session_id": s.session_id,
                    "client_info": s.client_info,
                    "status": s.status,
                    "created_at": s.created_at,
                    "turn_ids": list(s.turn_ids),
                }
                for s in self._sessions.values()
            ]

    # -- request handling --

    def _handle_session(self, client_info: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        self._cleanup_expired()
        with self._lock:
            active = sum(1 for s in self._sessions.values() if s.status == "active")
            if active >= self._config.max_sessions:
                return {
                    "error": {
                        "code": -32000,
                        "message": "max sessions reached",
                    }
                }
            session_id = str(uuid.uuid4())
            session = AcpServerSession(
                session_id=session_id,
                client_info=client_info if isinstance(client_info, dict) else {},
            )
            self._sessions[session_id] = session
        return {"result": {"session_id": session_id}}

    def _handle_message(self, session_id: str, message: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.status != "active":
                return {
                    "error": {
                        "code": -32001,
                        "message": "session not found or not active",
                    }
                }

        text = message.get("text", "") if isinstance(message, dict) else ""
        if not isinstance(text, str) or not text.strip():
            return {
                "error": {
                    "code": -32602,
                    "message": "message must contain a non-empty 'text' field",
                }
            }

        engine = self._turn_engine_getter()
        if engine is None:
            return {
                "error": {
                    "code": -32002,
                    "message": "turn engine is not available",
                }
            }

        try:
            turn_result = engine.run_text_turn(text)
        except Exception as exc:
            logger.exception("ACP server turn error")
            return {
                "error": {
                    "code": -32603,
                    "message": f"turn engine error: {exc}",
                }
            }

        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.turn_ids.append(turn_result.turn_id)

        return {
            "result": {
                "turn_id": turn_result.turn_id,
                "response": turn_result.response_text,
                "state": turn_result.final_state,
            }
        }

    def _cleanup_expired(self) -> None:
        now = datetime.now(UTC)
        timeout_s = self._config.session_timeout_ms / 1000.0
        with self._lock:
            for session in list(self._sessions.values()):
                if session.status != "active":
                    continue
                try:
                    created = datetime.fromisoformat(session.created_at)
                except (ValueError, TypeError):
                    continue
                elapsed = (now - created).total_seconds()
                if elapsed >= timeout_s:
                    session.status = "timed_out"

    # -- internal asyncio plumbing --

    async def _start_and_wait(
        self,
        ready: threading.Event,
        port_holder: list[int],
        error_holder: list[BaseException],
    ) -> None:
        server = await asyncio.start_server(
            self._handle_connection,
            host=self._config.host,
            port=self._config.port,
        )
        self._server = server
        sockets = server.sockets or []
        if sockets:
            port_holder.append(sockets[0].getsockname()[1])
        ready.set()
        async with server:
            await server.serve_forever()

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    request = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    response = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32700, "message": "parse error"},
                        "id": None,
                    }
                    writer.write((json.dumps(response) + "\n").encode("utf-8"))
                    await writer.drain()
                    continue

                response_body = self._dispatch(request)
                response_body["jsonrpc"] = "2.0"
                response_body["id"] = request.get("id")
                writer.write((json.dumps(response_body) + "\n").encode("utf-8"))
                await writer.drain()
        except (asyncio.CancelledError, ConnectionError):
            pass
        finally:
            writer.close()

    def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        method = request.get("method", "")
        params = request.get("params", {}) if isinstance(request.get("params"), dict) else {}

        if method == "initialize":
            client_info = params.get("client_info", {})
            return self._handle_session(client_info, request)
        elif method == "prompt":
            session_id = params.get("session_id", "")
            message = params.get("message", {})
            if not session_id:
                return {"error": {"code": -32602, "message": "session_id is required"}}
            return self._handle_message(session_id, message)
        elif method == "close_session":
            session_id = params.get("session_id", "")
            return self._close_session(session_id)
        else:
            return {"error": {"code": -32601, "message": f"unknown method: {method}"}}

    def _close_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return {"error": {"code": -32001, "message": "session not found"}}
            session.status = "closed"
        return {"result": {"closed": True}}

    async def _shutdown_server(self, server: asyncio.AbstractServer) -> int:
        server.close()
        await server.wait_closed()
        with self._lock:
            count = len(self._sessions)
            for session in self._sessions.values():
                if session.status == "active":
                    session.status = "closed"
        return count


__all__ = ["AcpServer", "AcpServerConfig", "AcpServerSession"]
