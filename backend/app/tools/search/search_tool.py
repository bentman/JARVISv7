from __future__ import annotations

import json

from backend.app.core.settings import Settings
from backend.app.routing.runtime_selector import select_search_runtime
from backend.app.tools.registry import ToolBase


class SearchTool(ToolBase):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def name(self) -> str:
        return "search"

    def description(self) -> str:
        return "Internet search adapter over configured search runtime."

    def run(self, tool_input: dict[str, object]) -> str:
        query = tool_input.get("query")
        if not isinstance(query, str) or not query.strip():
            return "[]"
        max_results_raw = tool_input.get("max_results", 3)
        max_results = max_results_raw if isinstance(max_results_raw, int) and max_results_raw > 0 else 3

        runtime, _trace = select_search_runtime(self._settings)
        try:
            results = runtime.search(query, max_results=max_results)
            payload = [
                {
                    "title": item.title,
                    "url": item.url,
                    "snippet": item.snippet,
                    "source": item.source,
                }
                for item in results
            ]
            return json.dumps(payload, sort_keys=True)
        except Exception:
            return "[]"
