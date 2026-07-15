from __future__ import annotations

import httpx
from backend.app.core.settings import Settings
from backend.app.runtimes.internetsearch.base import SearchBase, SearchResult


class SearXNGRuntime(SearchBase):
    def __init__(self, settings: Settings, timeout_s: float = 5.0) -> None:
        self._base_url = settings.searxng_base_url.rstrip("/")
        self._enabled = bool(settings.use_searxng and self._base_url)
        self._timeout_s = timeout_s

    def runtime_name(self) -> str:
        return "searxng"

    def is_available(self) -> bool:
        return self._enabled

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        if not self._enabled or not query.strip():
            return []
        try:
            response = httpx.get(
                f"{self._base_url}/search",
                params={"q": query, "format": "json"},
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
                        source="searxng",
                    )
                )
            return mapped
        except Exception:
            return []
