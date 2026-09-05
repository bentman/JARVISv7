from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import acp
from acp.schema import AllowedOutcome, DeniedOutcome, Implementation, RequestPermissionResponse
from backend.app.actions.boundaries import ActionOperation, BoundaryViolationError, ProcessBoundary
from backend.app.actions.process import _stop_process_tree

ACP_PROTOCOL_VERSION = acp.PROTOCOL_VERSION
_DEFINITION_KEYS = {"command", "process"}

EventCallback = Callable[[dict[str, Any]], None]
PermissionCallback = Callable[[dict[str, Any]], dict[str, str] | None]


@dataclass(frozen=True, slots=True)
class AcpDefinition:
    agent_id: str
    argv: tuple[str, ...]
    process_boundary: ProcessBoundary

    @classmethod
    def from_mapping(cls, local_id: str, mapping: Mapping[str, Any]) -> AcpDefinition:
        unknown = sorted(set(mapping) - _DEFINITION_KEYS)
        if unknown:
            raise ValueError(f"ACP definition contains unknown fields: {', '.join(unknown)}")
        argv = mapping.get("command")
        if not isinstance(argv, list) or not argv or any(not isinstance(item, str) or not item for item in argv):
            raise ValueError("ACP definition command must be a non-empty list of strings")
        process = mapping.get("process")
        if not isinstance(process, dict):
            raise ValueError("ACP definition process must be a mapping")
        return cls(local_id, tuple(argv), ProcessBoundary.from_mapping(process))


def run_acp(
    definition: AcpDefinition,
    prompt: str,
    operation: ActionOperation,
    *,
    on_event: EventCallback,
    request_permission: PermissionCallback,
) -> dict[str, Any]:
    """Run one outbound ACP session under an approved action operation."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("ACP prompt must be a non-empty string")
    if not definition.process_boundary.subprocess:
        raise BoundaryViolationError("ACP sessions require a subprocess process boundary")
    definition.process_boundary.validate_argv(definition.argv)
    async def bounded_session() -> dict[str, Any]:
        task = asyncio.create_task(_run_session(definition, prompt, operation, on_event, request_permission))
        try:
            while not task.done():
                operation.check()
                await asyncio.sleep(0.02)
            return await task
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
    return asyncio.run(bounded_session())


async def _run_session(
    definition: AcpDefinition,
    prompt: str,
    operation: ActionOperation,
    on_event: EventCallback,
    request_permission: PermissionCallback,
) -> dict[str, Any]:
    operation.check()
    environment = definition.process_boundary.scrub_environment(os.environ)
    working_directory = definition.process_boundary.resolve_working_directory()
    _require_existing_root(working_directory)
    client = _JarvisAcpClient(on_event, request_permission)
    command, *arguments = definition.argv
    async with acp.spawn_agent_process(
        client,
        command,
        *arguments,
        env=environment,
        cwd=working_directory,
        transport_kwargs={"limit": operation.boundary.max_result_bytes},
    ) as (connection, process):
        initialized = await connection.initialize(
            ACP_PROTOCOL_VERSION,
            client_info=Implementation(name="jarvisv7", version="7"),
        )
        _emit(on_event, "initialized", {"agent_id": definition.agent_id})
        session = await connection.new_session(str(working_directory), mcp_servers=[])
        session_id = session.session_id
        try:
            operation.check()
            response = await connection.prompt(session_id, [acp.text_block(prompt)])
            operation.check()
            stop_reason = getattr(response, "stop_reason", None)
            return {
                "agent_id": definition.agent_id,
                "session_id": session_id,
                "stop_reason": stop_reason,
                "output": _model_value(response),
                "agent_capabilities": _model_value(getattr(initialized, "agent_capabilities", None)),
                "pid": process.pid,
            }
        except BaseException:
            with suppress(Exception):
                await asyncio.wait_for(connection.cancel(session_id), timeout=1)
            raise
        finally:
            await asyncio.to_thread(_stop_process_tree, process.pid)


class _JarvisAcpClient:
    def __init__(self, on_event: EventCallback, request_permission: PermissionCallback) -> None:
        self._on_event = on_event
        self._request_permission = request_permission

    async def request_permission(
        self, session_id: str, tool_call: Any, options: list[Any], **_kwargs: Any
    ) -> RequestPermissionResponse:
        option_ids = [getattr(option, "option_id", None) for option in options]
        response = await asyncio.to_thread(self._request_permission,
            {
                "kind": "permission_request",
                "session_id": session_id,
                "tool_call": _model_value(tool_call),
                "options": [_model_value(option) for option in options],
            }
        )
        selected = (
            response.get("option_id")
            if isinstance(response, dict) and response.get("action") == "accept"
            else None
        )
        if selected in option_ids:
            _emit(self._on_event, "permission_selected", {"session_id": session_id, "option_id": selected})
            return RequestPermissionResponse(outcome=AllowedOutcome(option_id=selected))
        _emit(self._on_event, "permission_denied", {"session_id": session_id})
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def session_update(self, session_id: str, update: Any, **_kwargs: Any) -> None:
        _emit(self._on_event, "session_update", {"session_id": session_id, "update": _model_value(update)})


def _require_existing_root(working_directory: Path) -> None:
    if not working_directory.is_dir():
        raise BoundaryViolationError(f"ACP process working root is unavailable: {working_directory}")


def _emit(callback: EventCallback, kind: str, payload: dict[str, Any]) -> None:
    callback({"kind": kind, **payload})


def _model_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return value


__all__ = ["ACP_PROTOCOL_VERSION", "AcpDefinition", "run_acp"]
