from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class RegistryLike(Protocol):
    def invoke(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        ...


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: str
    error: str | None
    success: bool


class ToolExecutor:
    def execute(self, tool_name: str, tool_input: dict[str, Any], registry: RegistryLike) -> ToolResult:
        try:
            output = registry.invoke(tool_name, tool_input)
            return ToolResult(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=output,
                error=None,
                success=True,
            )
        except Exception as exc:  # fail-closed by contract
            return ToolResult(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output="",
                error=str(exc),
                success=False,
            )
