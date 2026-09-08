"""Streamable-HTTP MCP against a server that actually demands authorization.

The stdio suite cannot cover this: bearer injection, the 401 challenge, and the
httpx2 client path only exist on the HTTP transport.
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from backend.app.actions import ActionOperation, ExecutionBoundary
from backend.app.extensions.mcp import (
    McpConnectionDefinition,
    McpConnectionRuntime,
    McpHostCallbacks,
    open_mcp_sdk_peer,
)
from backend.app.extensions.mcp_oauth import parse_resource_metadata_url

TOKEN = "expected-token"

_SERVER = '''
import sys
import uvicorn
from mcp.server import MCPServer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

PORT = int(sys.argv[1])
TOKEN = "{token}"
mcp = MCPServer("httpfixture")

@mcp.tool()
def echo(value: str) -> str:
    return value

class RequireBearer(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/.well-known"):
            return await call_next(request)
        if request.headers.get("authorization") != f"Bearer {{TOKEN}}":
            metadata = (
                "http://127.0.0.1:%d/.well-known/oauth-protected-resource/mcp" % PORT
            )
            return JSONResponse(
                {{"error": "invalid_token"}},
                status_code=401,
                headers={{"WWW-Authenticate": 'Bearer resource_metadata="%s"' % metadata}},
            )
        return await call_next(request)

app = mcp.streamable_http_app()
app.add_middleware(RequireBearer)
uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="error")
'''


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _operation() -> ActionOperation:
    return ActionOperation(
        "session", "turn", "proposal", "mcp:httpfixture",
        ExecutionBoundary(("data",), 20_000, True, 64_000),
    )


def _definition(port: int) -> McpConnectionDefinition:
    return McpConnectionDefinition.from_mapping("httpfixture", {
        "transport": "streamable_http",
        "url": f"http://127.0.0.1:{port}/mcp",
        "tool_allowlist": ["echo"],
    })


async def _discover_and_call(definition: McpConnectionDefinition, token: str):
    async def credentials(_definition):
        return {"Authorization": f"Bearer {token}"}

    async def authorize(operation, _kind, _request):
        operation.check()

    async def elicit(_definition, _request):
        return {}

    runtime = McpConnectionRuntime(
        definition,
        peer_factory=open_mcp_sdk_peer,
        callbacks=McpHostCallbacks(credentials, authorize, elicit),
    )
    try:
        snapshot = await runtime.refresh(_operation())
        if snapshot.health != "ready":
            return snapshot, None
        return snapshot, await runtime.call_tool(_operation(), "echo", {"value": "hello"})
    finally:
        await runtime.close()


@pytest.fixture
def authorized_server(tmp_path: Path):
    port = _free_port()
    script = tmp_path / "http_mcp_fixture.py"
    script.write_text(_SERVER.format(token=TOKEN), encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, str(script), str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        started = False
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/mcp", timeout=1)
            except urllib.error.HTTPError:
                started = True
                break
            except Exception:
                time.sleep(0.2)
        if not started:
            pytest.skip("HTTP MCP fixture did not start in time")
        yield port
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_streamable_http_mcp_discovers_and_calls_with_a_bearer_token(
    authorized_server: int,
) -> None:
    snapshot, result = asyncio.run(_discover_and_call(_definition(authorized_server), TOKEN))

    assert snapshot.health == "ready"
    assert [tool["name"] for tool in snapshot.tools] == ["echo"]
    payload = result if isinstance(result, dict) else result.model_dump(mode="json")
    assert "hello" in json.dumps(payload)


def test_streamable_http_mcp_without_a_valid_token_is_unavailable(
    authorized_server: int,
) -> None:
    snapshot, result = asyncio.run(
        _discover_and_call(_definition(authorized_server), "wrong-token")
    )

    assert snapshot.health == "unavailable"
    assert result is None


def test_the_server_challenge_advertises_its_protected_resource_metadata(
    authorized_server: int,
) -> None:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{authorized_server}/mcp", timeout=5)
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
        challenge = exc.headers.get("WWW-Authenticate", "")
    else:  # pragma: no cover - the fixture always challenges
        pytest.fail("server did not challenge an unauthenticated request")

    assert parse_resource_metadata_url(challenge) == (
        f"http://127.0.0.1:{authorized_server}/.well-known/oauth-protected-resource/mcp"
    )
