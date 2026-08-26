from __future__ import annotations

import httpx
from backend.app.core.settings import Settings
from backend.app.runtimes.internetsearch.base import (
    SearchBase,
    SearchResponse,
    map_results,
    search_failure,
)


class SearXNGRuntime(SearchBase):
    def __init__(self, settings: Settings, timeout_s: float = 5.0) -> None:
        self._base_url = settings.searxng_base_url.rstrip("/")
        self._enabled = bool(settings.use_searxng)
        self._timeout_s = timeout_s

    def runtime_name(self) -> str:
        return "searxng"

    def is_available(self) -> bool:
        return bool(self._enabled and self._base_url)

    def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        if not self._enabled:
            return SearchResponse("disabled")
        if not self._base_url:
            return SearchResponse("misconfigured", reason="SearXNG endpoint missing")
        if not query.strip() or max_results <= 0:
            return SearchResponse("empty")
        try:
            response = httpx.get(
                f"{self._base_url}/search", params={"q": query, "format": "json"}, timeout=self._timeout_s,
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("results") if isinstance(payload, dict) else None
            return map_results(items, "searxng", url_key="url", snippet_key="content", limit=min(5, max_results))
        except Exception as exc:
            return search_failure(exc)
