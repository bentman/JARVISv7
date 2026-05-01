from __future__ import annotations

from ddgs import DDGS

from backend.app.core.settings import Settings
from backend.app.runtimes.internetsearch.base import SearchBase, SearchResult


class DDGSRuntime(SearchBase):
    def __init__(self, settings: Settings) -> None:
        self._enabled = bool(settings.use_ddgs)

    def runtime_name(self) -> str:
        return "ddgs"

    def is_available(self) -> bool:
        return self._enabled

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        if not self._enabled or not query.strip():
            return []
        try:
            mapped: list[SearchResult] = []
            with DDGS() as client:
                for item in client.text(query, max_results=max(0, max_results)):
                    if not isinstance(item, dict):
                        continue
                    mapped.append(
                        SearchResult(
                            title=str(item.get("title", "")),
                            url=str(item.get("href", "")),
                            snippet=str(item.get("body", "")),
                            source="ddgs",
                        )
                    )
            return mapped
        except Exception:
            return []
