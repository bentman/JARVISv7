from __future__ import annotations

import httpx
from backend.app.core.settings import Settings
from backend.app.runtimes.internetsearch.base import (
    SearchBase,
    SearchResponse,
    map_results,
    search_failure,
)


class TavilyRuntime(SearchBase):
    def __init__(self, settings: Settings, timeout_s: float = 8.0) -> None:
        self._enabled = bool(settings.use_tavily)
        self._api_key = settings.tavily_api_key
        self._timeout_s = timeout_s

    def runtime_name(self) -> str:
        return "tavily"

    def is_available(self) -> bool:
        return bool(self._enabled and self._api_key)

    def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        if not self._enabled:
            return SearchResponse("disabled")
        if not self._api_key:
            return SearchResponse("misconfigured", reason="Tavily key missing")
        if not query.strip() or max_results <= 0:
            return SearchResponse("empty")
        try:
            response = httpx.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "query": query, "max_results": min(5, max_results),
                    "search_depth": "basic", "auto_parameters": False,
                    "include_answer": False, "include_raw_content": False,
                },
                timeout=self._timeout_s,
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("results") if isinstance(payload, dict) else None
            return map_results(items, "tavily", url_key="url", snippet_key="content", limit=min(5, max_results))
        except Exception as exc:
            return search_failure(exc)
