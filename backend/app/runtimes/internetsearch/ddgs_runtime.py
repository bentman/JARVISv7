from __future__ import annotations

from backend.app.core.settings import Settings
from backend.app.runtimes.internetsearch.base import (
    SearchBase,
    SearchResponse,
    map_results,
    search_failure,
)
from ddgs import DDGS


class DDGSRuntime(SearchBase):
    def __init__(self, settings: Settings, timeout_s: int = 5) -> None:
        self._enabled = bool(settings.use_ddgs)
        self._timeout_s = timeout_s

    def runtime_name(self) -> str:
        return "ddgs"

    def is_available(self) -> bool:
        return self._enabled

    def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        if not self._enabled:
            return SearchResponse("disabled")
        if not query.strip() or max_results <= 0:
            return SearchResponse("empty")
        try:
            with DDGS(timeout=self._timeout_s, verify=True) as client:
                items = client.text(query, max_results=min(5, max_results))
            return map_results(items, "ddgs", url_key="href", snippet_key="body", limit=min(5, max_results))
        except Exception as exc:
            return search_failure(exc)
