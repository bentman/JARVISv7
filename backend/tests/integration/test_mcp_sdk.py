from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from backend.app.actions import ActionOperation, ExecutionBoundary
from backend.app.extensions.mcp import (
    McpConnectionDefinition,
    McpConnectionRuntime,
    McpHostCallbacks,
    open_mcp_sdk_peer,
)


def _operation(capability_id: str = "mcp:fixture") -> ActionOperation:
    return ActionOperation(
        "session", "turn", "proposal", capability_id, ExecutionBoundary(("data",), 10_000, True, 1024)
    )


def _process_is_running(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()[2]
    except FileNotFoundError:
        return False
    return state not in {"X", "Z"}


def test_sdk_v2_stdio_adapter_round_trips_discovery_and_tool_call(tmp_path: Path) -> None:
    server = tmp_path / "mcp_fixture.py"
    child_pid = tmp_path / "child.pid"
    server.write_text(
        "import os\n"
        "import subprocess\n"
        "import sys\n"
        "from contextlib import asynccontextmanager\n"
        "import anyio\n"
        "from mcp.server import MCPServer\n"
        "@asynccontextmanager\n"
        "async def lifespan(_server):\n"
        "    try:\n"
        "        yield\n"
        "    finally:\n"
        "        await anyio.sleep(60)\n"
        "mcp = MCPServer('fixture', lifespan=lifespan)\n"
        "@mcp.tool()\n"
        "def echo(value: str) -> str:\n"
        "    return value if 'UNRELATED_SECRET' not in os.environ else 'leaked'\n"
        "@mcp.resource('fixture://status')\n"
        "def status() -> str:\n"
        "    return 'ready'\n"
        "@mcp.prompt()\n"
        "def greeting() -> str:\n"
        "    return 'hello'\n"
        "if __name__ == '__main__':\n"
        "    child = subprocess.Popen(\n"
        "        [sys.executable, '-c', 'import time; time.sleep(60)'],\n"
        "        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,\n"
        "    )\n"
        "    open(sys.argv[1], 'w', encoding='utf-8').write(str(child.pid))\n"
        "    mcp.run(transport='stdio')\n",
        encoding="utf-8",
    )
    definition = McpConnectionDefinition(
        connection_id="fixture",
        transport="stdio",
        command=(sys.executable, str(server), str(child_pid)),
        process={
            "subprocess": True,
            "argv_allowlist": [sys.executable],
            "env_passthrough": [],
            "working_root": "data",
        },
        tool_allowlist=("echo",),
        resource_allowlist=("fixture://status",),
        prompt_allowlist=("greeting",),
    )

    async def credentials(_definition: McpConnectionDefinition) -> dict[str, str]:
        return {"UNRELATED_SECRET": "must-not-reach-child"}

    async def authorize(_operation: ActionOperation, _kind: str, _request: dict[str, object]) -> None:
        return None

    async def elicit(*_args: object) -> dict[str, object]:
        return {"action": "decline"}

    async def exercise() -> tuple[object, object]:
        runtime = McpConnectionRuntime(
            definition,
            peer_factory=open_mcp_sdk_peer,
            callbacks=McpHostCallbacks(credentials, authorize, elicit),
        )
        try:
            snapshot = await runtime.refresh(_operation("mcp:fixture:connect"))
            result = await runtime.call_tool(_operation("mcp:fixture:echo"), "echo", {"value": "hello"})
            return snapshot, result
        finally:
            await runtime.close()

    snapshot, result = asyncio.run(asyncio.wait_for(exercise(), timeout=10))

    assert snapshot.health == "ready"
    assert snapshot.protocol_version == "2026-07-28"
    assert [tool["name"] for tool in snapshot.tools] == ["echo"]
    assert [resource["uri"] for resource in snapshot.resources] == ["fixture://status"]
    assert [prompt["name"] for prompt in snapshot.prompts] == ["greeting"]
    output_schema = snapshot.tools[0]["outputSchema"]
    assert output_schema["type"] == "object"
    assert output_schema["required"] == ["result"]
    assert output_schema["properties"]["result"]["type"] == "string"
    assert result["structuredContent"] == {"result": "hello"}
    pid = int(child_pid.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and _process_is_running(pid):
        time.sleep(0.02)
    assert not _process_is_running(pid), "SDK close must terminate the stdio process tree"
