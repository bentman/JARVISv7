from __future__ import annotations

import pytest

from backend.app.tools.registry import ToolBase, ToolNotFoundError, ToolRegistry


class _EchoTool(ToolBase):
    def name(self) -> str:
        return "echo"

    def description(self) -> str:
        return "echo tool"

    def run(self, tool_input: dict[str, object]) -> str:
        return str(tool_input.get("value", ""))


def test_registry_invoke_calls_tool_run() -> None:
    reg = ToolRegistry()
    reg.register(_EchoTool())
    assert reg.invoke("echo", {"value": "ok"}) == "ok"


def test_registry_raises_not_found_for_unknown_tool() -> None:
    reg = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        reg.invoke("missing", {})


def test_registry_raises_on_duplicate_registration() -> None:
    reg = ToolRegistry()
    reg.register(_EchoTool())
    with pytest.raises(ValueError):
        reg.register(_EchoTool())


def test_registry_list_tools_returns_registered_names() -> None:
    reg = ToolRegistry()
    reg.register(_EchoTool())
    assert reg.list_tools() == ["echo"]
