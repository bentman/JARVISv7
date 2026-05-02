from __future__ import annotations

from abc import ABC, abstractmethod


class ToolNotFoundError(LookupError):
    pass


class ToolBase(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    def run(self, tool_input: dict[str, object]) -> str: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolBase] = {}

    def register(self, tool: ToolBase) -> None:
        tool_name = tool.name()
        if tool_name in self._tools:
            raise ValueError(f"tool already registered: {tool_name}")
        self._tools[tool_name] = tool

    def invoke(self, tool_name: str, tool_input: dict[str, object]) -> str:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ToolNotFoundError(f"tool not found: {tool_name}")
        return tool.run(tool_input)

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())
