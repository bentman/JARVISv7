from __future__ import annotations

from pydantic import BaseModel


class ToolCallSummary(BaseModel):
    tool_name: str
    tool_input: dict[str, object]
    tool_output_summary: str
    success: bool
