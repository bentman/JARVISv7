from __future__ import annotations

from datetime import UTC, datetime

from backend.app.tools.registry import ToolBase


class TimeTool(ToolBase):
    def name(self) -> str:
        return "time"

    def description(self) -> str:
        return "Return current UTC date/time in ISO-8601 format."

    def run(self, tool_input: dict[str, object]) -> str:
        return datetime.now(UTC).isoformat()
