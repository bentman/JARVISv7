from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

import httpx

SearchStatus = Literal["success", "empty", "disabled", "misconfigured", "timeout", "rate_limited", "failed"]


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str


@dataclass(frozen=True, slots=True)
class SearchResponse:
    status: SearchStatus
    results: tuple[SearchResult, ...] = ()
    reason: str | None = None


def search_failure(exc: Exception) -> SearchResponse:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)) or "timeout" in type(exc).__name__.lower():
        return SearchResponse("timeout", reason="provider timed out")
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in {401, 403}:
            return SearchResponse("misconfigured", reason=f"provider HTTP {code}")
        if code in {429, 432, 433}:
            return SearchResponse("rate_limited", reason=f"provider HTTP {code}")
        return SearchResponse("failed", reason=f"provider HTTP {code}")
    if "ratelimit" in type(exc).__name__.lower():
        return SearchResponse("rate_limited", reason="provider rate limited")
    # Exception messages can contain credentials, request URLs, or response bodies.
    return SearchResponse("failed", reason=f"provider failure ({type(exc).__name__})")


def map_results(items: object, provider: str, *, url_key: str, snippet_key: str, limit: int) -> SearchResponse:
    if not isinstance(items, list):
        return SearchResponse("failed", reason="invalid provider result payload")
    mapped = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        title, url, snippet = item.get("title"), item.get(url_key), item.get(snippet_key)
        if not isinstance(url, str) or len(url) > 4096 or not isinstance(snippet, str) or not url.strip() or not snippet.strip():
            continue
        mapped.append(SearchResult(str(title or "")[:240], url, snippet[:1600], provider))
    return SearchResponse("success" if mapped else "empty", tuple(mapped))


class SearchBase(ABC):
    @abstractmethod
    def runtime_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        raise NotImplementedError


class NullSearchRuntime(SearchBase):
    def __init__(self, reason: str = "search unavailable") -> None:
        self.reason = reason

    def runtime_name(self) -> str:
        return "null"

    def is_available(self) -> bool:
        return False

    def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        return SearchResponse("disabled", reason=self.reason)
