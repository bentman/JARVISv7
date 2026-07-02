from __future__ import annotations

from backend.app.cognition.executor import ToolExecutor


class _Registry:
    def __init__(self, *, should_raise: bool = False, missing: bool = False) -> None:
        self.should_raise = should_raise
        self.missing = missing
        self.calls: list[tuple[str, dict[str, object]]] = []

    def invoke(self, tool_name: str, tool_input: dict[str, object]) -> str:
        self.calls.append((tool_name, tool_input))
        if self.missing:
            raise KeyError(f"unknown tool: {tool_name}")
        if self.should_raise:
            raise RuntimeError("tool execution failed")
        return "ok"


def test_tool_executor_calls_registry_invoke() -> None:
    registry = _Registry()
    result = ToolExecutor().execute("stub.echo", {"value": 1}, registry)

    assert registry.calls == [("stub.echo", {"value": 1})]
    assert result.success is True
    assert result.error is None
    assert result.tool_output == "ok"


def test_tool_executor_returns_fail_closed_result_when_tool_missing() -> None:
    registry = _Registry(missing=True)
    result = ToolExecutor().execute("missing.tool", {}, registry)

    assert result.success is False
    assert result.error is not None
    assert result.tool_output == ""


def test_tool_executor_returns_fail_closed_result_when_tool_raises() -> None:
    registry = _Registry(should_raise=True)
    result = ToolExecutor().execute("stub.echo", {"x": "y"}, registry)

    assert result.success is False
    assert result.error == "tool execution failed"
    assert result.tool_output == ""


def test_tool_executor_result_has_success_false_on_error() -> None:
    registry = _Registry(should_raise=True)
    result = ToolExecutor().execute("stub.echo", {}, registry)

    assert result.success is False
