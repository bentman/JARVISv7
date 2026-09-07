from __future__ import annotations

from typing import Any

from backend.app.runtimes.internetsearch.base import (
    SearchBase,
    SearchResponse,
    SearchResult,
)

# ---------------------------------------------------------------------------
# Pre-built raw response fixtures (provider-shaped dicts)
# ---------------------------------------------------------------------------

SAMPLE_DDGS_RESPONSE: list[dict[str, Any]] = [
    {
        "title": "Python Official Documentation",
        "href": "https://docs.python.org/3/",
        "body": "Official documentation for the Python programming language.",
    },
    {
        "title": "Python Tutorial - W3Schools",
        "href": "https://www.w3schools.com/python/",
        "body": "Easy to understand Python tutorial with examples.",
    },
    {
        "title": "Python Package Index",
        "href": "https://pypi.org/",
        "body": "Find and install Python packages from PyPI.",
    },
]

SAMPLE_SEARXNG_RESPONSE: list[dict[str, Any]] = [
    {
        "title": "Solar Panel Efficiency Explained",
        "url": "https://example.com/solar-efficiency",
        "content": "Modern solar panels achieve 20-23% efficiency in standard conditions.",
    },
    {
        "title": "Best Solar Panels 2026",
        "url": "https://example.com/best-solar",
        "content": "Top-rated solar panels for residential installation in 2026.",
    },
    {
        "title": "Solar Energy Basics",
        "url": "https://example.com/solar-basics",
        "content": "A comprehensive guide to solar energy fundamentals.",
    },
]

SAMPLE_TAVILY_RESPONSE: list[dict[str, Any]] = [
    {
        "title": "Quantum Computing Overview",
        "url": "https://example.com/quantum",
        "content": "Quantum computing leverages quantum mechanical phenomena.",
        "score": 0.95,
    },
    {
        "title": "Quantum Algorithms Explained",
        "url": "https://example.com/quantum-algorithms",
        "content": "Key quantum algorithms including Shor's and Grover's.",
        "score": 0.88,
    },
    {
        "title": "Quantum Computing Hardware",
        "url": "https://example.com/quantum-hardware",
        "content": "Current quantum hardware platforms and their capabilities.",
        "score": 0.82,
    },
]

EMPTY_RESPONSE: list[dict[str, Any]] = []

RATE_LIMITED_ERROR = Exception("rate limit exceeded")


# ---------------------------------------------------------------------------
# Mock search provider
# ---------------------------------------------------------------------------


class MockSearchProvider(SearchBase):
    """A mock search provider for testing without live external services.

    Stores pre-built :class:`SearchResponse` objects keyed by query string.
    Supports failure modes that simulate common provider errors.
    """

    def __init__(
        self,
        provider_name: str,
        responses: dict[str, SearchResponse] | None = None,
        failure_mode: str | None = None,
    ) -> None:
        self._name = provider_name
        self._responses = dict(responses or {})
        self._failure_mode = failure_mode
        self.calls: list[tuple[str, int]] = []

    def runtime_name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return True

    def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        self.calls.append((query, max_results))
        if self._failure_mode == "timeout":
            raise TimeoutError(f"{self._name}: provider timed out")
        if self._failure_mode == "error":
            raise RuntimeError(f"{self._name}: provider error")
        if self._failure_mode == "rate_limited":
            raise RuntimeError(f"{self._name}: rate limit exceeded")
        if self._failure_mode == "empty":
            return SearchResponse("empty", reason="no results")
        return self._responses.get(query, SearchResponse("empty", reason="no mock data for query"))


# ---------------------------------------------------------------------------
# Helper to build SearchResponse from raw provider-shaped dicts
# ---------------------------------------------------------------------------


def _build_response(
    items: list[dict[str, Any]],
    provider: str,
    url_key: str,
    snippet_key: str,
) -> SearchResponse:
    results = []
    for item in items:
        results.append(
            SearchResult(
                title=str(item.get("title", "")),
                url=str(item.get(url_key, "")),
                snippet=str(item.get(snippet_key, "")),
                source=provider,
            )
        )
    return SearchResponse("success" if results else "empty", tuple(results))


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def mock_ddgs_provider(
    responses: dict[str, list[dict[str, Any]]] | None = None,
    failure_mode: str | None = None,
    **overrides: Any,
) -> MockSearchProvider:
    """Return a :class:`MockSearchProvider` with DDGS-shaped responses."""
    raw = responses or {"Python documentation": SAMPLE_DDGS_RESPONSE}
    search_responses = {
        q: _build_response(items, "ddgs", url_key="href", snippet_key="body")
        for q, items in raw.items()
    }
    return MockSearchProvider("ddgs", search_responses, failure_mode)


def mock_searxng_provider(
    responses: dict[str, list[dict[str, Any]]] | None = None,
    failure_mode: str | None = None,
    **overrides: Any,
) -> MockSearchProvider:
    """Return a :class:`MockSearchProvider` with SearXNG-shaped responses."""
    raw = responses or {"solar panel efficiency": SAMPLE_SEARXNG_RESPONSE}
    search_responses = {
        q: _build_response(items, "searxng", url_key="url", snippet_key="content")
        for q, items in raw.items()
    }
    return MockSearchProvider("searxng", search_responses, failure_mode)


def mock_tavily_provider(
    responses: dict[str, list[dict[str, Any]]] | None = None,
    failure_mode: str | None = None,
    **overrides: Any,
) -> MockSearchProvider:
    """Return a :class:`MockSearchProvider` with Tavily-shaped responses."""
    raw = responses or {"quantum computing": SAMPLE_TAVILY_RESPONSE}
    search_responses = {
        q: _build_response(items, "tavily", url_key="url", snippet_key="content")
        for q, items in raw.items()
    }
    return MockSearchProvider("tavily", search_responses, failure_mode)
