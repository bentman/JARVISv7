"""Host-governed MCP client adapter.

This module owns protocol transport and opaque MCP records.  It deliberately does
not register capabilities, persist credentials, or decide approvals: the owning
extension/runtime service supplies those policies through :class:`McpHostCallbacks`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, suppress
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from backend.app.actions import ActionCancelledError, ActionOperation
from backend.app.actions.boundaries import ProcessBoundary
from backend.app.extensions.contracts import SAFE_LOCAL_ID

McpTransport = Literal["stdio", "streamable_http"]
MCP_TRANSPORTS = frozenset({"stdio", "streamable_http"})


class McpError(RuntimeError):
    """A connection or host-policy failure at the MCP boundary."""


@dataclass(frozen=True, slots=True)
class McpConnectionDefinition:
    connection_id: str
    transport: McpTransport
    command: tuple[str, ...] = ()
    url: str | None = None
    credential_ref: str | None = None
    process: dict[str, Any] | None = None
    enabled: bool = True
    oauth: dict[str, Any] | None = None
    tool_allowlist: tuple[str, ...] = ()
    resource_allowlist: tuple[str, ...] = ()
    prompt_allowlist: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not SAFE_LOCAL_ID.match(self.connection_id):
            raise ValueError(f"connection_id must match {SAFE_LOCAL_ID.pattern}")
        if self.transport not in MCP_TRANSPORTS:
            raise ValueError("transport must be stdio or streamable_http")
        if self.transport == "stdio":
            if not self.command:
                raise ValueError("stdio connections require command")
            if self.url is not None:
                raise ValueError("stdio connections cannot declare url")
            if not isinstance(self.process, dict):
                raise ValueError("stdio connections require process boundaries")
            boundary = ProcessBoundary.from_mapping(self.process)
            boundary.validate_argv(self.command)
        else:
            if self.command:
                raise ValueError("streamable_http connections cannot declare command")
            if self.process is not None:
                raise ValueError("streamable_http connections cannot declare process boundaries")
            parsed = urlsplit(self.url or "")
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("streamable_http connections require an HTTP(S) url")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("MCP url cannot contain credentials, query, or fragment")
        for name in ("tool_allowlist", "resource_allowlist", "prompt_allowlist"):
            values = getattr(self, name)
            if any(not item or item != item.strip() for item in values):
                raise ValueError(f"{name} entries must be non-empty strings")
        if self.oauth is not None:
            self._validate_oauth(self.oauth)

    @staticmethod
    def _validate_oauth(oauth: dict[str, Any]) -> None:
        if not isinstance(oauth, dict):
            raise ValueError("oauth must be a mapping")
        if "client_id" not in oauth:
            raise ValueError("oauth requires client_id")
        # Endpoints are optional: when absent they are discovered from the server's
        # protected-resource metadata, and an explicit value overrides discovery.
        declared = [field for field in ("authorization_url", "token_url") if field in oauth]
        if len(declared) == 1:
            raise ValueError("oauth requires both authorization_url and token_url, or neither")
        for url_field in declared:
            parsed = urlsplit(str(oauth[url_field]))
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError(f"oauth.{url_field} must be a valid HTTPS URL")
        if not isinstance(oauth["client_id"], str) or not oauth["client_id"]:
            raise ValueError("oauth.client_id must be a non-empty string")
        scopes = oauth.get("scopes", [])
        if not isinstance(scopes, list) or any(not isinstance(s, str) or not s for s in scopes):
            raise ValueError("oauth.scopes must be a list of non-empty strings")
        redirect_port = oauth.get("redirect_port", 19823)
        if not isinstance(redirect_port, int) or not (1024 <= redirect_port <= 65535):
            raise ValueError("oauth.redirect_port must be an integer between 1024 and 65535")
        resource = oauth.get("resource")
        if resource is not None:
            parsed = urlsplit(str(resource))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("oauth.resource must be a valid HTTP(S) URL")
        unknown = set(oauth) - {
            "authorization_url", "token_url", "client_id", "client_secret",
            "scopes", "redirect_port", "resource",
        }
        if unknown:
            raise ValueError(f"oauth has unsupported fields: {', '.join(sorted(unknown))}")

    @classmethod
    def from_mapping(cls, connection_id: str, value: dict[str, Any]) -> McpConnectionDefinition:
        if not isinstance(value, dict):
            raise ValueError("MCP definition must be a mapping")
        allowed = {
            "transport", "command", "url", "credential_ref", "enabled", "oauth",
            "tool_allowlist", "resource_allowlist", "prompt_allowlist", "process",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"MCP definition has unknown fields: {', '.join(unknown)}")
        command = value.get("command", [])
        if not isinstance(command, list) or any(not isinstance(part, str) for part in command):
            raise ValueError("command must be a list of strings")
        filters: dict[str, tuple[str, ...]] = {}
        for name in ("tool_allowlist", "resource_allowlist", "prompt_allowlist"):
            raw = value.get(name, [])
            if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
                raise ValueError(f"{name} must be a list of strings")
            filters[name] = tuple(raw)
        transport = value.get("transport")
        if not isinstance(transport, str):
            raise ValueError("transport must be a string")
        url = value.get("url")
        if url is not None and not isinstance(url, str):
            raise ValueError("url must be a string")
        credential_ref = value.get("credential_ref")
        if credential_ref is not None and not isinstance(credential_ref, str):
            raise ValueError("credential_ref must be a string")
        process = value.get("process")
        if process is not None and not isinstance(process, dict):
            raise ValueError("process must be a mapping")
        enabled = value.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        oauth = value.get("oauth")
        if oauth is not None and not isinstance(oauth, dict):
            raise ValueError("oauth must be a mapping")
        return cls(
            connection_id=connection_id,
            transport=transport,  # type: ignore[arg-type]
            command=tuple(command),
            url=url,
            credential_ref=credential_ref,
            process=dict(process) if process is not None else None,
            enabled=enabled,
            oauth=dict(oauth) if oauth is not None else None,
            **filters,
        )

    @property
    def process_boundary(self) -> ProcessBoundary:
        if self.process is None:
            raise McpError("MCP connection has no process boundary")
        return ProcessBoundary.from_mapping(self.process)


@dataclass(frozen=True, slots=True)
class McpDiscovery:
    connection_id: str
    server_info: dict[str, Any] = field(default_factory=dict)
    protocol_version: str | None = None
    server_capabilities: dict[str, Any] = field(default_factory=dict)
    tools: tuple[dict[str, Any], ...] = ()
    resources: tuple[dict[str, Any], ...] = ()
    prompts: tuple[dict[str, Any], ...] = ()
    health: str = "unknown"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class McpPeer(Protocol):
    """Narrow peer seam, allowing focused tests without a running MCP server."""

    async def discovery(self) -> McpDiscovery: ...

    async def read_resource(self, uri: str) -> Any: ...

    async def get_prompt(self, name: str, arguments: dict[str, Any]) -> Any: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...

    async def cancel(self, request_id: str) -> None: ...

    async def aclose(self) -> None: ...


CredentialResolver = Callable[[McpConnectionDefinition], Awaitable[dict[str, str]]]
ActionAuthorizer = Callable[[ActionOperation, str, dict[str, Any]], Awaitable[None]]
ElicitationHandler = Callable[[McpConnectionDefinition, dict[str, Any]], Awaitable[dict[str, Any]]]
PeerFactory = Callable[[McpConnectionDefinition, dict[str, str], ElicitationHandler], Awaitable[McpPeer]]


@dataclass(frozen=True, slots=True)
class McpHostCallbacks:
    """Application-owned credentials and consent callbacks for peer operations."""

    resolve_credentials: CredentialResolver
    authorize: ActionAuthorizer
    request_elicitation: ElicitationHandler


class McpConnectionRuntime:
    """One host-owned MCP connection with explicit filters and cancellation."""

    def __init__(
        self,
        definition: McpConnectionDefinition,
        *,
        peer_factory: PeerFactory,
        callbacks: McpHostCallbacks,
    ) -> None:
        self.definition = definition
        self._peer_factory = peer_factory
        self._callbacks = callbacks
        self._peer: McpPeer | None = None
        self._discovery = McpDiscovery(connection_id=definition.connection_id)
        self._lock = asyncio.Lock()

    async def refresh(self, operation: ActionOperation) -> McpDiscovery:
        operation.check()
        if not self.definition.enabled:
            self._discovery = McpDiscovery(
                connection_id=self.definition.connection_id,
                health="disabled",
                error="MCP connection is disabled by its definition.",
            )
            return self._discovery
        try:
            await _await_operation(
                operation,
                self._callbacks.authorize(
                    operation,
                    "connect",
                    {"connection_id": self.definition.connection_id, "transport": self.definition.transport},
                ),
            )
            operation.check()
            peer = await _await_operation(operation, self._ensure_peer())
            discovered = await _await_operation(operation, peer.discovery())
            operation.check()
            discovery = McpDiscovery(
                connection_id=self.definition.connection_id,
                server_info=dict(discovered.server_info),
                protocol_version=discovered.protocol_version,
                server_capabilities=dict(discovered.server_capabilities),
                tools=_filter_records(discovered.tools, self.definition.tool_allowlist, "name"),
                resources=_filter_records(discovered.resources, self.definition.resource_allowlist, "uri"),
                prompts=_filter_records(discovered.prompts, self.definition.prompt_allowlist, "name"),
                health="ready",
            )
            _enforce_output_limit(operation, discovery.to_dict())
            self._discovery = discovery
        except ActionCancelledError:
            await self.close()
            raise
        except Exception as exc:
            with suppress(Exception):
                await self.close()
            self._discovery = McpDiscovery(
                connection_id=self.definition.connection_id,
                health="unavailable",
                error=str(exc),
            )
        return self._discovery

    def snapshot(self) -> McpDiscovery:
        return self._discovery

    async def read_resource(self, operation: ActionOperation, uri: str) -> Any:
        self._require_allowed(uri, self.definition.resource_allowlist, "resource")
        return await self._governed(operation, "read_resource", {"uri": uri}, lambda peer: peer.read_resource(uri))

    async def get_prompt(
        self, operation: ActionOperation, name: str, arguments: dict[str, Any]
    ) -> Any:
        self._require_allowed(name, self.definition.prompt_allowlist, "prompt")
        return await self._governed(
            operation, "get_prompt", {"name": name, "arguments": dict(arguments)},
            lambda peer: peer.get_prompt(name, dict(arguments)),
        )

    async def call_tool(
        self, operation: ActionOperation, name: str, arguments: dict[str, Any]
    ) -> Any:
        self._require_allowed(name, self.definition.tool_allowlist, "tool")
        result = await self._governed(
            operation, "call_tool", {"name": name, "arguments": dict(arguments)},
            lambda peer: peer.call_tool(name, dict(arguments)),
        )
        if isinstance(result, dict) and result.get("isError") is True:
            raise McpError(f"MCP tool reported an error: {name}")
        return result

    async def cancel(self, operation: ActionOperation, request_id: str) -> bool:
        operation.cancel.set()
        peer = self._peer
        if peer is None:
            return False
        await peer.cancel(request_id)
        return True

    async def close(self) -> None:
        """Ends the peer connection gracefully.

        Idempotent by design, not joinable: a second call while the first is still in
        flight sees `self._peer` already cleared and returns immediately having awaited
        nothing further. An earlier attempt at making a second call wait for the first
        via `asyncio.shield` was reverted - it corrupted anyio's own cancel-scope
        bookkeeping (`RuntimeError: Attempted to exit cancel scope in a different task
        than it was entered in`), confirmed by direct reproduction, since anyio's cancel
        scopes are bound to the task that entered them and shielding a second awaiter
        does not change which task that is. `backend/app/actions/sessions.py`'s `_close`
        owns not calling this a second, independent time while the first has not
        genuinely finished - see its own handling of `handlers.close is handlers.terminate`.
        """
        async with self._lock:
            peer, self._peer = self._peer, None
        if peer is not None:
            await peer.aclose()

    async def _ensure_peer(self) -> McpPeer:
        async with self._lock:
            if self._peer is None:
                credentials = await self._callbacks.resolve_credentials(self.definition)
                self._peer = await self._peer_factory(
                    self.definition, dict(credentials), self._callbacks.request_elicitation
                )
            return self._peer

    async def _governed(
        self,
        operation: ActionOperation,
        kind: str,
        request: dict[str, Any],
        invoke: Callable[[McpPeer], Awaitable[Any]],
    ) -> Any:
        operation.check()
        await _await_operation(
            operation, self._callbacks.authorize(operation, kind, dict(request))
        )
        operation.check()
        peer = await _await_operation(operation, self._ensure_peer())
        result = await _await_operation(operation, invoke(peer))
        operation.check()
        _enforce_output_limit(operation, result)
        return result

    def _require_allowed(self, value: str, allowlist: tuple[str, ...], kind: str) -> None:
        if allowlist and value not in allowlist:
            raise McpError(f"{kind} is not exposed by this MCP connection: {value}")


def peer_connection_died(exc: BaseException) -> bool:
    """Whether `exc`, raised from a tool/resource/prompt call, means the underlying
    connection died rather than the server returning an application-level error.

    Confirmed empirically, not assumed: killing a stdio server's process mid-session and
    then calling a tool against it raises the SDK's own `mcp.shared.exceptions.MCPError`
    carrying `mcp_types.CONNECTION_CLOSED` (-32000) - not a raw `anyio`/`ConnectionError`,
    and not this module's own `McpError` (a different class, used for application-level
    failures like an unlisted tool name or a tool-reported error result). Only that
    specific code means the connection itself is gone; any other `MCPError` (an
    unsupported method, a malformed request) is the server answering normally about a
    request it disliked, not evidence the connection needs to be evicted and reopened.
    """
    try:
        from mcp.shared.exceptions import MCPError as SdkMcpError
        from mcp_types import CONNECTION_CLOSED
    except ImportError:  # pragma: no cover - dependency provisioning owns this path.
        return False
    return isinstance(exc, SdkMcpError) and getattr(exc, "code", None) == CONNECTION_CLOSED


class McpSdkPeer:
    """Official MCP Python SDK v2 adapter for stdio and Streamable HTTP only."""

    def __init__(self, stack: AsyncExitStack, client: Any) -> None:
        self._stack = stack
        self._client = client

    @classmethod
    async def open(
        cls,
        definition: McpConnectionDefinition,
        credentials: dict[str, str],
        elicitation: ElicitationHandler,
    ) -> McpSdkPeer:
        try:
            from mcp import Client, StdioServerParameters
        except ImportError as exc:  # pragma: no cover - dependency provisioning owns this path.
            raise McpError("MCP Python SDK v2 is not installed") from exc

        async def on_elicitation(_context: Any, params: Any) -> Any:
            from mcp.types import ElicitResult

            response = await elicitation(definition, _to_mapping(params))
            action = response.get("action", "decline")
            content = response.get("content")
            return ElicitResult(action=action, content=content)

        stack = AsyncExitStack()
        try:
            if definition.transport == "stdio":
                command, *args = definition.command
                boundary = definition.process_boundary
                boundary.validate_argv(definition.command)
                target: Any = StdioServerParameters(
                    command=command,
                    args=args,
                    env=boundary.scrub_environment(credentials),
                    cwd=boundary.resolve_working_directory(),
                )
            else:
                import httpx2
                from mcp.client.streamable_http import streamable_http_client

                http_client = await stack.enter_async_context(
                    httpx2.AsyncClient(headers=dict(credentials), follow_redirects=False)
                )
                target = streamable_http_client(definition.url or "", http_client=http_client)
            client = await stack.enter_async_context(
                Client(target, elicitation_callback=on_elicitation)
            )
            return cls(stack, client)
        except BaseException:
            await stack.aclose()
            raise

    async def discovery(self) -> McpDiscovery:
        tools, resources, prompts = await asyncio.gather(
            _list_all(self._client.list_tools, "tools"),
            _list_all(self._client.list_resources, "resources"),
            _list_all(self._client.list_prompts, "prompts"),
        )
        return McpDiscovery(
            connection_id="",
            server_info=_to_mapping(getattr(self._client, "server_info", None)),
            protocol_version=str(getattr(self._client, "protocol_version", "")) or None,
            server_capabilities=_to_mapping(getattr(self._client, "server_capabilities", None)),
            tools=tuple(_to_mapping(item) for item in tools),
            resources=tuple(_to_mapping(item) for item in resources),
            prompts=tuple(_to_mapping(item) for item in prompts),
        )

    async def read_resource(self, uri: str) -> Any:
        return _to_mapping(await self._client.read_resource(uri))

    async def get_prompt(self, name: str, arguments: dict[str, Any]) -> Any:
        return _to_mapping(await self._client.get_prompt(name, arguments))

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return _to_mapping(await self._client.call_tool(name, arguments))

    async def cancel(self, request_id: str) -> None:
        session = getattr(self._client, "session", None)
        send_notification = getattr(session, "send_notification", None)
        if send_notification is None:
            return
        try:
            from mcp.types import CancelledNotification, CancelledNotificationParams

            await send_notification(
                CancelledNotification(params=CancelledNotificationParams(requestId=request_id))
            )
        except Exception:
            # MCP cancellation is cooperative. The host cancellation signal remains authoritative.
            return

    async def aclose(self) -> None:
        await self._stack.aclose()


async def open_mcp_sdk_peer(
    definition: McpConnectionDefinition,
    credentials: dict[str, str],
    elicitation: ElicitationHandler,
) -> McpPeer:
    return await McpSdkPeer.open(definition, credentials, elicitation)


def _filter_records(
    records: tuple[dict[str, Any], ...], allowlist: tuple[str, ...], key: str
) -> tuple[dict[str, Any], ...]:
    if not allowlist:
        return tuple(dict(record) for record in records)
    return tuple(dict(record) for record in records if record.get(key) in allowlist)


async def _list_all(method: Callable[..., Awaitable[Any]], attribute: str) -> tuple[Any, ...]:
    """Read every SDK page while refusing a malformed repeated pagination cursor."""
    cursor: str | None = None
    seen_cursors: set[str] = set()
    records: list[Any] = []
    while True:
        page = await method(cursor=cursor)
        records.extend(getattr(page, attribute, ()))
        next_cursor = getattr(page, "next_cursor", None)
        if not next_cursor:
            return tuple(records)
        if next_cursor in seen_cursors:
            raise McpError("MCP discovery repeated a pagination cursor")
        seen_cursors.add(next_cursor)
        cursor = next_cursor


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return dict(value)
    return {"value": str(value)}


async def _await_operation(operation: ActionOperation, awaitable: Awaitable[Any]) -> Any:
    """Bound one SDK await by the action deadline and cooperative cancel signal."""
    host_task = asyncio.current_task()
    if host_task is None:  # pragma: no cover - coroutines always run in a task here.
        raise RuntimeError("MCP operation requires an asyncio task")

    async def cancel_host() -> None:
        while not operation.cancel.is_set():
            await asyncio.sleep(0.05)
        host_task.cancel()

    remaining = max(0.0, (operation.boundary.timeout_ms - operation.elapsed_ms()) / 1000)
    watcher = asyncio.create_task(cancel_host())
    try:
        operation.check()
        async with asyncio.timeout(remaining):
            return await awaitable
    except TimeoutError as exc:
        operation.cancel.set()
        raise ActionCancelledError(f"action cancelled: {operation.capability_id}") from exc
    except asyncio.CancelledError as exc:
        if operation.cancel.is_set():
            raise ActionCancelledError(f"action cancelled: {operation.capability_id}") from exc
        raise
    finally:
        watcher.cancel()
        with suppress(asyncio.CancelledError):
            await watcher


def _enforce_output_limit(operation: ActionOperation, result: Any) -> None:
    encoded = len(json.dumps(result, default=str, ensure_ascii=False).encode("utf-8"))
    if encoded > operation.boundary.max_result_bytes:
        raise McpError(
            f"MCP result exceeded max_result_bytes ({encoded} > "
            f"{operation.boundary.max_result_bytes})"
        )


__all__ = [
    "MCP_TRANSPORTS",
    "ActionAuthorizer",
    "CredentialResolver",
    "ElicitationHandler",
    "McpConnectionDefinition",
    "McpConnectionRuntime",
    "McpDiscovery",
    "McpError",
    "McpHostCallbacks",
    "McpPeer",
    "McpSdkPeer",
    "McpTransport",
    "PeerFactory",
    "open_mcp_sdk_peer",
    "peer_connection_died",
]
