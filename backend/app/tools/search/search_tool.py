from __future__ import annotations

import json

from backend.app.core.settings import Settings
from backend.app.runtimes.internetsearch import DDGSRuntime, SearchBase, SearchResult, SearXNGRuntime, TavilyRuntime
from backend.app.tools.registry import ToolBase


class SearchTool(ToolBase):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def name(self) -> str:
        return "search"

    def description(self) -> str:
        return "Internet search adapter over configured search runtime."

    def _providers(self) -> list[SearchBase]:
        return [
            SearXNGRuntime(self._settings),
            DDGSRuntime(self._settings),
            TavilyRuntime(self._settings),
        ]

    @staticmethod
    def _usable_results(results: list[SearchResult]) -> list[SearchResult]:
        return [item for item in results if isinstance(item, SearchResult)]

    def run(self, tool_input: dict[str, object]) -> str:
        query = tool_input.get("query")
        if not isinstance(query, str) or not query.strip():
            return "[]"
        max_results_raw = tool_input.get("max_results", 3)
        max_results = max_results_raw if isinstance(max_results_raw, int) and max_results_raw > 0 else 3

        for runtime in self._providers():
            if not runtime.is_available():
                continue
            try:
                results = self._usable_results(runtime.search(query, max_results=max_results))
            except Exception:
                continue
            if not results:
                continue
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
        return "[]"
