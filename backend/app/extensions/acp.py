from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import acp
from acp.schema import AllowedOutcome, DeniedOutcome, Implementation, RequestPermissionResponse
from backend.app.actions.boundaries import ActionOperation, BoundaryViolationError, ProcessBoundary
from backend.app.actions.process import _stop_process_tree
from backend.app.actions.sessions import SessionHandlers, SessionManager, SessionResourceDied

ACP_PROTOCOL_VERSION = acp.PROTOCOL_VERSION
_DEFINITION_KEYS = {"command", "process"}

EventCallback = Callable[[dict[str, Any]], None]
PermissionCallback = Callable[[dict[str, Any]], dict[str, str] | None]
ResumableSessionLookup = Callable[[], str | None]
RememberSessionId = Callable[[str], None]


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


@dataclass(slots=True)
class _AcpSession:
    """One open ACP connection: a spawned agent process with an initialized session."""

    stack: AsyncExitStack
    connection: Any
    process: Any
    session_id: str
    agent_capabilities: Any
    client: "_JarvisAcpClient"


def run_acp(
    session_manager: SessionManager,
    definition: AcpDefinition,
    prompt: str,
    operation: ActionOperation,
    *,
    on_event: EventCallback,
    request_permission: PermissionCallback,
    get_resumable_session_id: ResumableSessionLookup = lambda: None,
    remember_session_id: RememberSessionId = lambda _session_id: None,
) -> dict[str, Any]:
    """Run one ACP prompt against a connection ADR 0005's shared session-lifecycle
    mechanism keeps open across separate calls, instead of spawning a fresh agent
    process and session for every prompt - the same `session/prompt` reuse `protocol-
    v2.md` describes, opt-in the first time this agent is prompted and reused after.

    `get_resumable_session_id`/`remember_session_id` are what let a connection recover
    conversation continuity after the mechanism evicts and reopens it (a crashed agent
    process, an explicit Disconnect that closed but did not forget the last session):
    each call to `open_session` looks up the last session id it remembered for this
    connection and attempts `session/resume` against the freshly spawned process before
    falling back to `session/new`, but only if the agent itself advertises
    `sessionCapabilities.resume` at `initialize` - resume is a negotiated capability, not
    one this adapter can assume. The caller (`ExtensionRuntimeService._acp`) owns
    persisting the session id across separate `run_acp` calls; this function only reads
    and writes it through the two callables, the same way `on_event`/`request_permission`
    are threaded through rather than owned here.
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("ACP prompt must be a non-empty string")
    if not definition.process_boundary.subprocess:
        raise BoundaryViolationError("ACP sessions require a subprocess process boundary")
    definition.process_boundary.validate_argv(definition.argv)
    # Namespaced by host conversation (operation.session_id), not just the agent's own
    # identity: an ACP session is stateful conversation context on the agent's own side,
    # and two different host conversations sharing one connection_id would share that
    # context too - confirmed with a real agent process returning the first
    # conversation's content in response to the second's prompt before this was fixed.
    # `close_prefix` is what lets a definition edit/delete still close every connection
    # for this agent despite the id no longer being just `acp:{agent_id}`.
    connection_id = f"acp:{definition.agent_id}:{operation.session_id}"

    async def open_session() -> _AcpSession:
        operation.check()
        environment = definition.process_boundary.scrub_environment(os.environ)
        working_directory = definition.process_boundary.resolve_working_directory()
        _require_existing_root(working_directory)
        command, *arguments = definition.argv
        stack = AsyncExitStack()
        # The client is a connection-level object the SDK holds for the process's whole
        # lifetime, but its callbacks must reflect whichever call is currently in flight.
        # Bound here immediately (to this call's own on_event/request_permission, since
        # this call is the one running open_session) rather than only inside send_prompt
        # below: initialize/resume_session/new_session can themselves trigger a
        # session_update or permission request before send_prompt ever runs, and an
        # unbound client raises TypeError on the agent's first such message instead of
        # delivering it. send_prompt's own client.bind(...) still rebinds on every
        # subsequent call against a connection this open only ran once for.
        client = _JarvisAcpClient()
        client.bind(on_event, request_permission)
        try:
            connection, process = await stack.enter_async_context(
                acp.spawn_agent_process(
                    client, command, *arguments, env=environment, cwd=working_directory,
                    transport_kwargs={"limit": operation.boundary.max_result_bytes},
                )
            )
            initialized = await connection.initialize(
                ACP_PROTOCOL_VERSION, client_info=Implementation(name="jarvisv7", version="7"),
            )
            _emit(on_event, "initialized", {"agent_id": definition.agent_id})
            agent_capabilities = _model_value(getattr(initialized, "agent_capabilities", None))
            session_id = await _open_session_id(
                connection, working_directory, agent_capabilities,
                get_resumable_session_id, on_event, definition.agent_id,
            )
            remember_session_id(session_id)
            return _AcpSession(
                stack=stack, connection=connection, process=process,
                session_id=session_id, agent_capabilities=agent_capabilities, client=client,
            )
        except BaseException:
            await stack.aclose()
            raise

    async def close_session(session: _AcpSession) -> None:
        # Exit the SDK's own context manager first for whatever graceful shutdown it
        # performs, then fall back to the same terminate/bounded-wait/kill escalation
        # `_stop_process_tree` already provides for the tool family, in case the SDK's
        # own exit does not itself end the process.
        await session.stack.aclose()
        await asyncio.to_thread(_stop_process_tree, session.process.pid)

    async def terminate_session(session: _AcpSession) -> None:
        # Reached two ways: a call did not finish draining (the process may still be
        # alive, possibly hung), or the session-lifecycle mechanism is evicting a
        # connection a call already reported dead (SessionResourceDied - the process is
        # already gone). Either way, the SDK's own in-memory connection object (its
        # sender/receiver background tasks) still needs closing, or those tasks leak as
        # pending work - a bounded, best-effort attempt first, since a graceful exit
        # against an already-hung or already-dead connection may itself hang or error.
        # Killing the process afterward is unconditional and safe even if it is already
        # dead, unlike the SDK-level close.
        with suppress(Exception):
            await asyncio.wait_for(session.stack.aclose(), timeout=1)
        await asyncio.to_thread(_stop_process_tree, session.process.pid)

    handlers: SessionHandlers[_AcpSession] = SessionHandlers(
        open=open_session, close=close_session, terminate=terminate_session,
    )

    async def send_prompt(session: _AcpSession) -> dict[str, Any]:
        # The client object is shared with whichever call opened the connection; rebind
        # its callbacks to this call's on_event/request_permission before using it, since
        # a permission request or session update the agent sends while handling this
        # prompt must reach this call's caller, not the call that happened to open it.
        session.client.bind(on_event, request_permission)
        operation.check()
        try:
            response = await session.connection.prompt(session.session_id, [acp.text_block(prompt)])
            operation.check()
            return {
                "agent_id": definition.agent_id,
                "session_id": session.session_id,
                "stop_reason": getattr(response, "stop_reason", None),
                "output": _model_value(response),
                "agent_capabilities": session.agent_capabilities,
                "pid": session.process.pid,
            }
        except ConnectionError as exc:
            # Confirmed empirically, not assumed: killing the spawned agent process
            # externally and then prompting the same (reused) session raises a plain
            # `ConnectionError("Connection closed")` from the ACP SDK's own transport -
            # distinct from an application-level prompt failure, which is whatever
            # exception the agent's own handler raises instead. Only this means the
            # connection itself is gone and the next call must reopen rather than retry
            # against the same now-unusable connection.
            with suppress(Exception):
                await asyncio.wait_for(session.connection.cancel(session.session_id), timeout=1)
            raise SessionResourceDied(f"ACP connection died during prompt: {exc}") from exc
        except BaseException:
            with suppress(Exception):
                await asyncio.wait_for(session.connection.cancel(session.session_id), timeout=1)
            raise

    async def bounded_work(session: _AcpSession) -> dict[str, Any]:
        # A cross-thread ActionOperation.cancel()/deadline is not itself an asyncio
        # signal, so this polls it the same way the pre-attachment code did, cancelling
        # only this prompt's task - not the session - on a cooperative cancel or timeout.
        task = asyncio.ensure_future(send_prompt(session))
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

    return session_manager.call(
        connection_id, handlers, bounded_work, timeout_s=operation.boundary.timeout_ms / 1000,
    )


async def _open_session_id(
    connection: Any,
    working_directory: Path,
    agent_capabilities: Any,
    get_resumable_session_id: ResumableSessionLookup,
    on_event: EventCallback,
    agent_id: str,
) -> str:
    """Resumes the last known session against a freshly (re)spawned process if the agent
    supports it and one is on record, otherwise starts a fresh session.

    `sessionCapabilities.resume` is a negotiated capability the agent advertises at
    `initialize`, not something this adapter assumes - a client that never needs to
    resume simply never has anything to look up here, and an agent that never
    advertises support is never asked. A resume attempt that fails (the agent no longer
    has that session, or refuses it for its own reasons) falls back to starting a fresh
    session rather than failing the whole call - the mechanism only guarantees a fresh
    connection is reachable, not that a specific prior session is recoverable from it.
    """
    supports_resume = bool(((agent_capabilities or {}).get("sessionCapabilities") or {}).get("resume"))
    prior_session_id = get_resumable_session_id() if supports_resume else None
    if prior_session_id:
        try:
            await connection.resume_session(prior_session_id, str(working_directory), mcp_servers=[])
        except Exception as exc:
            _emit(on_event, "resume_failed", {
                "agent_id": agent_id, "session_id": prior_session_id, "error": str(exc),
            })
        else:
            _emit(on_event, "resumed", {"agent_id": agent_id, "session_id": prior_session_id})
            return prior_session_id
    session = await connection.new_session(str(working_directory), mcp_servers=[])
    return session.session_id


class _JarvisAcpClient:
    """Connection-level object the ACP SDK holds for the spawned process's whole
    lifetime. Its callbacks are rebound per call (see send_prompt's `bind` call) rather
    than fixed at construction, since the connection outlives any single call once the
    session-lifecycle mechanism reuses it.
    """

    def __init__(self) -> None:
        self._on_event: EventCallback | None = None
        self._request_permission: PermissionCallback | None = None

    def bind(self, on_event: EventCallback, request_permission: PermissionCallback) -> None:
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
