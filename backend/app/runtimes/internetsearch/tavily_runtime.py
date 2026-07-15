from __future__ import annotations

import httpx
from backend.app.core.settings import Settings
from backend.app.runtimes.internetsearch.base import SearchBase, SearchResult


class TavilyRuntime(SearchBase):
    def __init__(self, settings: Settings, timeout_s: float = 8.0) -> None:
        self._enabled = bool(settings.use_tavily)
        self._api_key = settings.tavily_api_key
        self._timeout_s = timeout_s

    def runtime_name(self) -> str:
        return "tavily"

    def is_available(self) -> bool:
        return bool(self._enabled and self._api_key)

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        if not self.is_available() or not query.strip():
            return []
        try:
            response = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": max(0, max_results),
                },
                timeout=self._timeout_s,
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results", []) if isinstance(payload, dict) else []
            mapped: list[SearchResult] = []
            for item in results[: max(0, max_results)]:
                if not isinstance(item, dict):
                    continue
                mapped.append(
                    SearchResult(
                        title=str(item.get("title", "")),
                        url=str(item.get("url", "")),
                        snippet=str(item.get("content", "")),
                        source="tavily",
                    )
                )
            return mapped
        except Exception:
            return []
