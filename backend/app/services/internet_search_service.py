from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from backend.app.core.settings import Settings
from backend.app.runtimes.internetsearch import (
    DDGSRuntime,
    SearchBase,
    SearchResult,
    SearXNGRuntime,
    TavilyRuntime,
)


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    status: str  # "completed" | "unavailable"
    provider: str | None
    results: tuple[SearchResult, ...]
    attempted_providers: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class TurnSearchSummary:
    requested: bool = False
    status: str = "not_requested"  # "not_requested" | "completed" | "unavailable"
    provider: str | None = None
    sources: tuple[SearchResult, ...] = ()
    reason: str | None = None


class InternetSearchService:
    """Coordinates the configured search providers behind one bounded outcome.

    Providers are tried in the fixed order they are supplied; the first
    provider returning usable results wins. Empty or failed attempts fall
    through to the next enabled provider. Provider enablement remains the
    operator settings boundary owned by each runtime.
    """

    def __init__(self, providers: Sequence[SearchBase]) -> None:
        self._providers = list(providers)

    @classmethod
    def from_settings(cls, settings: Settings) -> "InternetSearchService":
        return cls(
            [
                SearXNGRuntime(settings),
                DDGSRuntime(settings),
                TavilyRuntime(settings),
            ]
        )

    def is_available(self) -> bool:
        return any(provider.is_available() for provider in self._providers)

    def search(self, query: str, *, max_results: int = 3) -> SearchOutcome:
        trimmed = query.strip()
        if not trimmed:
            return SearchOutcome(
                status="unavailable",
                provider=None,
                results=(),
                attempted_providers=(),
                reason="empty search query",
            )
        attempted: list[str] = []
        for provider in self._providers:
            if not provider.is_available():
                continue
            attempted.append(provider.runtime_name())
            try:
                results = provider.search(trimmed, max_results=max_results)
            except Exception:
                continue
            usable = tuple(item for item in results if isinstance(item, SearchResult))[:max_results]
            if usable:
                return SearchOutcome(
                    status="completed",
                    provider=provider.runtime_name(),
                    results=usable,
                    attempted_providers=tuple(attempted),
                    reason="provider returned usable results",
                )
        if not attempted:
            return SearchOutcome(
                status="unavailable",
                provider=None,
                results=(),
                attempted_providers=(),
                reason="no search provider is enabled",
            )
        return SearchOutcome(
            status="unavailable",
            provider=None,
            results=(),
            attempted_providers=tuple(attempted),
            reason="no enabled provider returned usable results",
        )
