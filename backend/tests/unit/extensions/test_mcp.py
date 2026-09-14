from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from backend.app.actions import ActionCancelledError, ActionOperation, ExecutionBoundary
from backend.app.extensions.mcp import (
    McpConnectionDefinition,
    McpConnectionRuntime,
    McpDiscovery,
    McpError,
    McpHostCallbacks,
)
from backend.app.services.extension_runtime_service import ExtensionRuntimeService


def operation() -> ActionOperation:
    return ActionOperation(
        "session", "turn", "proposal", "mcp:server:tool", ExecutionBoundary(("data",), 10_000, True, 1024)
    )


@dataclass
class FakePeer:
    calls: list[tuple[str, object]] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)
    closed: bool = False

    async def discovery(self) -> McpDiscovery:
        return McpDiscovery(
            connection_id="ignored",
            server_info={"name": "fake"},
            protocol_version="2026-07-28",
            server_capabilities={"tools": {}},
            tools=(
                {"name": "safe", "inputSchema": {"type": "object", "anyOf": [{"type": "string"}]}},
                {"name": "hidden", "inputSchema": {"$ref": "https://example.invalid/schema"}},
            ),
            resources=({"uri": "file://safe"}, {"uri": "file://hidden"}),
            resource_templates=({"uriTemplate": "file://{name}"},),
            prompts=({"name": "safe-prompt"}, {"name": "hidden-prompt"}),
            cache_metadata={
                "tools": {"ttlMs": 60000, "cacheScope": "private"},
                "resources": {"ttlMs": 60000, "cacheScope": "public"},
                "resource_templates": {"ttlMs": 60000, "cacheScope": "public"},
                "prompts": {"ttlMs": 60000, "cacheScope": "public"},
            },
        )

    async def read_resource(self, uri: str) -> object:
        self.calls.append(("resource", uri))
        return {"contents": [{"text": "untrusted"}]}

    async def get_prompt(self, name: str, arguments: dict[str, object]) -> object:
        self.calls.append(("prompt", (name, arguments)))
        return {"messages": []}

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        self.calls.append(("tool", (name, arguments)))
        return {"structuredContent": {"ok": True}}

    async def cancel(self, request_id: str) -> None:
        self.cancelled.append(request_id)

    async def aclose(self) -> None:
        self.closed = True


def definition(**overrides: object) -> McpConnectionDefinition:
    values: dict[str, object] = {
        "connection_id": "example",
        "transport": "streamable_http",
        "url": "https://mcp.example.test/mcp",
        "tool_allowlist": ("safe",),
        "resource_allowlist": ("file://safe",),
        "prompt_allowlist": ("safe-prompt",),
    }
    values.update(overrides)
    return McpConnectionDefinition(**values)  # type: ignore[arg-type]


def run(coro):
    return asyncio.run(coro)


def test_definition_validates_transport_and_secret_free_urls() -> None:
    assert definition().transport == "streamable_http"
    assert McpConnectionDefinition.from_mapping(
        "stdio", {
            "transport": "stdio", "command": ["server", "--stdio"],
            "process": {
                "subprocess": True, "argv_allowlist": ["server"], "env_passthrough": [],
                "working_root": "data",
            },
        }
    ).command == ("server", "--stdio")

    with pytest.raises(ValueError, match="cannot contain credentials"):
        definition(url="https://user:password@mcp.example.test/mcp")
    with pytest.raises(ValueError, match="require command"):
        McpConnectionDefinition("missing", "stdio")


def test_refresh_preserves_raw_tool_schema_and_applies_host_filters() -> None:
    peer = FakePeer()

    async def factory(*_args):
        return peer

    async def credentials(_definition):
        return {"Authorization": "Bearer secret"}

    authorized: list[str] = []

    async def authorize(_operation, kind, _request):
        authorized.append(kind)

    async def elicit(*_args):
        return {"action": "decline"}

    runtime = McpConnectionRuntime(
        definition(), peer_factory=factory,
        callbacks=McpHostCallbacks(credentials, authorize, elicit),
    )
    snapshot = run(runtime.refresh(operation()))

    assert snapshot.health == "ready"
    assert snapshot.connection_id == "example"
    assert snapshot.tools == ({"name": "safe", "inputSchema": {"type": "object", "anyOf": [{"type": "string"}]}},)
    assert snapshot.resources == ({"uri": "file://safe"},)
    assert snapshot.resource_templates == ({"uriTemplate": "file://{name}"},)
    assert snapshot.prompts == ({"name": "safe-prompt"},)
    assert snapshot.cache_metadata["tools"] == {"ttlMs": 60000, "cacheScope": "private"}
    assert authorized == ["connect"]


def test_refresh_drops_tools_with_invalid_x_mcp_header_metadata() -> None:
    peer = FakePeer()

    async def discovery() -> McpDiscovery:
        return McpDiscovery(
            connection_id="ignored",
            tools=(
                {"name": "valid", "inputSchema": {
                    "type": "object",
                    "properties": {"tenant": {"type": "string", "x-mcp-header": "Tenant"}},
                }},
                {"name": "invalid", "inputSchema": {
                    "type": "object",
                    "properties": {"tenant": {"type": "number", "x-mcp-header": "Tenant"}},
                }},
            ),
        )

    peer.discovery = discovery  # type: ignore[method-assign]

    async def factory(*_args):
        return peer

    async def allow(*_args):
        return None

    async def elicit(*_args):
        return {"action": "decline"}

    async def no_credentials(_definition):
        return {}

    runtime = McpConnectionRuntime(
        definition(tool_allowlist=("valid", "invalid")),
        peer_factory=factory,
        callbacks=McpHostCallbacks(no_credentials, allow, elicit),
    )

    snapshot = run(runtime.refresh(operation()))

    assert [tool["name"] for tool in snapshot.tools] == ["valid"]
    assert snapshot.descriptor_problems == (
        {
            "kind": "tool",
            "name": "invalid",
            "reason": (
                "invalid x-mcp-header: property 'tenant': x-mcp-header is only "
                "permitted on integer/string/boolean properties (got 'number')"
            ),
        },
    )


def test_peer_operations_require_action_authorization_before_calls() -> None:
    peer = FakePeer()
    authorized: list[tuple[str, dict[str, object]]] = []

    async def factory(*_args):
        return peer

    async def credentials(_definition):
        return {}

    async def authorize(_operation, kind, request):
        authorized.append((kind, request))

    async def elicit(*_args):
        return {"action": "decline"}

    runtime = McpConnectionRuntime(
        definition(), peer_factory=factory,
        callbacks=McpHostCallbacks(credentials, authorize, elicit),
    )

    assert run(runtime.call_tool(operation(), "safe", {"q": "value"})) == {"structuredContent": {"ok": True}}
    assert authorized == [("call_tool", {"name": "safe", "arguments": {"q": "value"}})]
    assert peer.calls == [("tool", ("safe", {"q": "value"}))]

    with pytest.raises(McpError, match="not exposed"):
        run(runtime.call_tool(operation(), "hidden", {}))
    assert len(authorized) == 1 and len(peer.calls) == 1

    async def error_call(_name, _arguments):
        return {"content": [{"type": "text", "text": "failed"}], "isError": True}

    peer.call_tool = error_call  # type: ignore[method-assign]
    with pytest.raises(McpError, match="reported an error"):
        run(runtime.call_tool(operation(), "safe", {}))

    async def oversized_call(_name, _arguments):
        return {"structuredContent": "x" * 2048}

    peer.call_tool = oversized_call  # type: ignore[method-assign]
    small = ActionOperation(
        "session", "turn", "proposal", "mcp:server:tool",
        ExecutionBoundary(("data",), 10_000, True, 128),
    )
    with pytest.raises(McpError, match="max_result_bytes"):
        run(runtime.call_tool(small, "safe", {}))


def test_denied_host_authorization_cannot_reach_peer() -> None:
    peer = FakePeer()

    async def factory(*_args):
        return peer

    async def credentials(_definition):
        return {}

    async def authorize(*_args):
        raise PermissionError("operator declined")

    async def elicit(*_args):
        return {"action": "decline"}

    runtime = McpConnectionRuntime(
        definition(), peer_factory=factory,
        callbacks=McpHostCallbacks(credentials, authorize, elicit),
    )
    with pytest.raises(PermissionError, match="operator declined"):
        run(runtime.read_resource(operation(), "file://safe"))
    assert peer.calls == []


def test_factory_receives_host_owned_credentials_consent_and_change_callbacks() -> None:
    peer = FakePeer()
    received: dict[str, object] = {}

    async def factory(connection, credentials, elicitation, notify_list_changed):
        received["connection"] = connection
        received["credentials"] = credentials
        received["notify"] = notify_list_changed
        received["response"] = await elicitation(connection, {"message": "Need confirmation"})
        received["announced"] = await notify_list_changed(connection, "tools")
        return peer

    async def credentials(_definition):
        return {"Authorization": "Bearer secret"}

    async def allow(*_args):
        return None

    async def elicit(connection, request):
        assert connection.connection_id == "example"
        assert request == {"message": "Need confirmation"}
        return {"action": "accept", "content": {"answer": "yes"}}

    announced: list[object] = []

    async def announce(connection, kind):
        announced.append((connection, kind))

    runtime = McpConnectionRuntime(
        definition(), peer_factory=factory,
        callbacks=McpHostCallbacks(credentials, allow, elicit, announce),
    )
    run(runtime.refresh(operation()))

    assert received["credentials"] == {"Authorization": "Bearer secret"}
    assert received["response"] == {"action": "accept", "content": {"answer": "yes"}}
    assert announced == [(definition(), "tools")]


def test_cancellation_signals_operation_and_peer_then_closes() -> None:
    peer = FakePeer()

    async def factory(*_args):
        return peer

    async def no_credentials(_definition):
        return {}

    async def allow(*_args):
        return None

    async def elicit(*_args):
        return {"action": "decline"}

    runtime = McpConnectionRuntime(
        definition(), peer_factory=factory,
        callbacks=McpHostCallbacks(no_credentials, allow, elicit),
    )
    run(runtime.refresh(operation()))
    active = operation()
    assert run(runtime.cancel(active, "rpc-1")) is True
    assert active.cancel.is_set() and peer.cancelled == ["rpc-1"]
    run(runtime.close())
    assert peer.closed is True


def test_disabled_connection_never_resolves_credentials_or_connects() -> None:
    called = False

    async def factory(*_args):
        raise AssertionError("disabled connection must not connect")

    async def credentials(_definition):
        nonlocal called
        called = True
        return {}

    async def allow(*_args):
        return None

    async def elicit(*_args):
        return {"action": "decline"}

    runtime = McpConnectionRuntime(
        definition(enabled=False), peer_factory=factory,
        callbacks=McpHostCallbacks(credentials, allow, elicit),
    )
    assert run(runtime.refresh(operation())).health == "disabled"
    assert called is False


def test_refresh_propagates_cancellation_and_closes_peer() -> None:
    started = asyncio.Event()

    class SlowPeer(FakePeer):
        async def discovery(self) -> McpDiscovery:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    peer = SlowPeer()

    async def factory(*_args):
        return peer

    async def credentials(_definition):
        return {}

    async def authorize(_operation, _kind, _request):
        return None

    async def elicit(*_args):
        return {"action": "decline"}

    runtime = McpConnectionRuntime(
        definition(), peer_factory=factory,
        callbacks=McpHostCallbacks(credentials, authorize, elicit),
    )
    async def exercise() -> None:
        active = operation()
        refresh = asyncio.create_task(runtime.refresh(active))
        await started.wait()
        active.cancel.set()
        with pytest.raises(ActionCancelledError):
            await refresh

    run(exercise())

    assert peer.closed is True


def test_refresh_records_sdk_failure_as_unavailable_and_closes_peer() -> None:
    peer = FakePeer()

    async def discovery_failure() -> McpDiscovery:
        raise RuntimeError("SDK connection failed")

    peer.discovery = discovery_failure  # type: ignore[method-assign]

    async def factory(*_args):
        return peer

    async def no_credentials(_definition):
        return {}

    async def allow(*_args):
        return None

    async def elicit(*_args):
        return {"action": "decline"}

    runtime = McpConnectionRuntime(
        definition(), peer_factory=factory,
        callbacks=McpHostCallbacks(no_credentials, allow, elicit),
    )
    snapshot = run(runtime.refresh(operation()))

    assert snapshot.health == "unavailable"
    assert snapshot.error == "SDK connection failed"
    assert peer.closed is True


def test_stale_mcp_snapshot_keeps_detail_data_but_hides_dynamic_operations() -> None:
    service = ExtensionRuntimeService.__new__(ExtensionRuntimeService)
    service._snapshots = {
        "mcp:example": {
            "tools": [{"name": "safe", "inputSchema": {"type": "object"}}],
            "resources": [{"uri": "file://safe"}],
            "prompts": [{"name": "safe-prompt"}],
            "discovered_at": (datetime.now(UTC) - timedelta(seconds=2)).isoformat(),
            "cache_metadata": {
                "tools": {"ttlMs": 1, "cacheScope": "public"},
                "resources": {},
                "prompts": {},
            },
        }
    }
    service.mcp_credentials = lambda _definition, _local_id: {}  # type: ignore[method-assign]

    snapshot = service._fresh_mcp_snapshot("mcp:example", definition(), "example")

    assert snapshot["tools"] == []
    assert snapshot["resources"] == [{"uri": "file://safe"}]
    assert snapshot["cache_metadata"]["tools"]["freshness"] == "stale"
    assert snapshot["cache_metadata"]["resources"]["freshness"] == "unknown"


def test_private_mcp_snapshot_is_not_reused_after_credential_context_changes() -> None:
    service = ExtensionRuntimeService.__new__(ExtensionRuntimeService)
    service._snapshots = {
        "mcp:example": {
            "tools": [{"name": "safe", "inputSchema": {"type": "object"}}],
            "credential_context_hash": "previous",
            "cache_metadata": {"tools": {"ttlMs": 60000, "cacheScope": "private"}},
        }
    }
    service.mcp_credentials = lambda _definition, _local_id: {"Authorization": "Bearer changed"}  # type: ignore[method-assign]

    assert service._fresh_mcp_snapshot("mcp:example", definition(), "example") == {}


def test_private_mcp_snapshot_without_stored_credential_context_is_not_reused() -> None:
    service = ExtensionRuntimeService.__new__(ExtensionRuntimeService)
    service._snapshots = {
        "mcp:example": {
            "tools": [{"name": "safe", "inputSchema": {"type": "object"}}],
            "cache_metadata": {"tools": {"ttlMs": 60000, "cacheScope": "private"}},
        }
    }

    assert service._fresh_mcp_snapshot("mcp:example", definition(), "example") == {}
