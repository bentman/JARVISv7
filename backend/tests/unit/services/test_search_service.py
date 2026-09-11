from __future__ import annotations

import pytest
from backend.app.runtimes.internetsearch.base import SearchBase, SearchResponse, SearchResult
from backend.app.runtimes.internetsearch.page_reader import PageResult, SearchCancelledError
from backend.app.services.search_service import SearchService

pytestmark = pytest.mark.search


class Provider(SearchBase):
    def __init__(self, name, response, calls):
        self.name, self.response, self.calls = name, response, calls
    def runtime_name(self):
        return self.name
    def is_available(self):
        return True
    def search(self, query, *, max_results=5):
        self.calls.append((self.name, query, max_results))
        return self.response


def result(url="https://example.com/?q=one"):
    return SearchResult("Title", url, "Public evidence", "test")


@pytest.mark.parametrize("status", ["disabled", "misconfigured", "empty", "timeout", "rate_limited", "failed"])
def test_order_and_stop_on_first_usable_set(status):
    calls = []
    service = SearchService([
        Provider("ddgs", SearchResponse(status), calls),
        Provider("searxng", SearchResponse("success", (result(),)), calls),
        Provider("tavily", SearchResponse("success", (result(),)), calls),
    ])
    with service.operation("session", "turn") as operation:
        evidence = service.retrieve(operation, mode="search", topic="topic", queries=["one", "two"])
        assert evidence.outcome == "success"
        assert [attempt.status for attempt in evidence.attempts] == [status, "success"]
    assert calls == [("ddgs", "one", 5), ("searxng", "one", 5)]


def test_research_limits_deduplication_and_partial_pages():
    calls, pages = [], []
    results = tuple(result(url) for url in (
        "https://one.example.com/?q=1", "https://one.example.com/?q=1#fragment",
        "https://one.example.com/?q=2", "https://two.example.com/", "https://three.example.com/",
    ))
    class Reader:
        def read(self, url, *, cancelled):
            pages.append(url)
            return PageResult(url, "unsupported")
    service = SearchService([
        Provider("ddgs", SearchResponse("empty"), calls),
        Provider("searxng", SearchResponse("failed"), calls),
        Provider("tavily", SearchResponse("success", results), calls),
    ], Reader())  # type: ignore[arg-type]
    with service.operation("session", "turn") as operation:
        evidence = service.retrieve(operation, mode="research", topic="topic", queries=["one", "two", "three", "four"])
        assert evidence.outcome == "partial"
        assert len(evidence.sources) == 4
        assert all(source.basis == "search_excerpt" for source in evidence.sources)
        assert len({source.id for source in evidence.sources}) == 4
        assert all(source.retrieved_at for source in evidence.sources)
    assert len([call for call in calls if call[0] == "tavily"]) == 3
    assert pages == ["https://one.example.com/?q=1", "https://two.example.com/", "https://three.example.com/"]


def test_unusable_results_advance_and_cancellation_is_scoped():
    calls = []
    service = SearchService([Provider("ddgs", SearchResponse("success", (result("http://127.0.0.1/"),)), calls)])
    with service.operation("session", "turn") as operation:
        evidence = service.retrieve(operation, mode="search", topic="topic", queries=["one"])
        assert evidence.outcome == "unavailable" and not evidence.sources
        assert not service.cancel("other", "turn")
        assert not service.cancel("session", "old")
        assert service.cancel("session", "turn")
        with pytest.raises(SearchCancelledError):
            operation.check()
    assert service.cancel("session", "turn")
    with service.operation("session", "next") as operation:
        assert service.cancel("session", "turn")
        operation.check()
        operation.evidence.stage = "complete"
        assert not service.cancel("session", "next")


def test_cancelled_provider_attempt_is_audited_without_fallback():
    calls = []
    service = SearchService([])
    class Cancelling(Provider):
        def search(self, query, *, max_results=5):
            service.cancel("session", "turn")
            return super().search(query, max_results=max_results)
    service.providers = (Cancelling("ddgs", SearchResponse("timeout"), calls), Provider("tavily", SearchResponse("empty"), calls))
    with service.operation("session", "turn") as operation:
        with pytest.raises(SearchCancelledError):
            service.retrieve(operation, mode="search", topic="topic", queries=["one"])
        assert len(operation.evidence.attempts) == 1
        assert operation.evidence.attempts[0].status == "timeout"
    assert len(calls) == 1


def test_redirected_pages_deduplicate_and_retain_provider_provenance():
    class Reader:
        def read(self, url, *, cancelled):
            return PageResult("https://final.example.com/", "success", "Public fact")
    results = (result("https://one.example.com/"), result("https://two.example.com/"))
    service = SearchService([Provider("ddgs", SearchResponse("success", results), [])], Reader())  # type: ignore[arg-type]
    with service.operation("s", "t") as operation:
        evidence = service.retrieve(operation, mode="research", topic="topic", queries=["one"])
        assert len(evidence.sources) == 1
        assert evidence.sources[0].page_duration_ms is not None
        assert evidence.sources[0].basis == "page_excerpt"
