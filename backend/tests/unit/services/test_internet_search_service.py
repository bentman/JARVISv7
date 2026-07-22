from __future__ import annotations

from backend.app.runtimes.internetsearch import SearchBase, SearchResult
from backend.app.services.internet_search_service import InternetSearchService, TurnSearchSummary


class FakeSearchProvider(SearchBase):
    def __init__(
        self,
        name: str,
        *,
        available: bool = True,
        results: list[SearchResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._name = name
        self._available = available
        self._results = results or []
        self._error = error
        self.queries: list[str] = []

    def runtime_name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return self._available

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        self.queries.append(query)
        if self._error is not None:
            raise self._error
        return self._results[:max_results]


def _result(url: str, source: str) -> SearchResult:
    return SearchResult(title=f"title {url}", url=url, snippet=f"snippet {url}", source=source)


def test_first_provider_with_usable_results_wins() -> None:
    first = FakeSearchProvider("first", results=[_result("https://a.example", "first")])
    second = FakeSearchProvider("second", results=[_result("https://b.example", "second")])

    outcome = InternetSearchService([first, second]).search("query")

    assert outcome.status == "completed"
    assert outcome.provider == "first"
    assert outcome.attempted_providers == ("first",)
    assert [item.url for item in outcome.results] == ["https://a.example"]
    assert second.queries == []


def test_empty_results_fall_through_to_next_enabled_provider() -> None:
    first = FakeSearchProvider("first", results=[])
    second = FakeSearchProvider("second", results=[_result("https://b.example", "second")])

    outcome = InternetSearchService([first, second]).search("query")

    assert outcome.status == "completed"
    assert outcome.provider == "second"
    assert outcome.attempted_providers == ("first", "second")


def test_provider_exception_falls_through_and_is_recorded_as_attempted() -> None:
    first = FakeSearchProvider("first", error=RuntimeError("provider down"))
    second = FakeSearchProvider("second", results=[_result("https://b.example", "second")])

    outcome = InternetSearchService([first, second]).search("query")

    assert outcome.status == "completed"
    assert outcome.provider == "second"
    assert outcome.attempted_providers == ("first", "second")


def test_disabled_provider_is_skipped_and_not_attempted() -> None:
    disabled = FakeSearchProvider("disabled", available=False, results=[_result("https://a.example", "disabled")])
    enabled = FakeSearchProvider("enabled", results=[_result("https://b.example", "enabled")])

    outcome = InternetSearchService([disabled, enabled]).search("query")

    assert outcome.provider == "enabled"
    assert outcome.attempted_providers == ("enabled",)
    assert disabled.queries == []


def test_no_enabled_provider_reports_unavailable() -> None:
    outcome = InternetSearchService([FakeSearchProvider("off", available=False)]).search("query")

    assert outcome.status == "unavailable"
    assert outcome.provider is None
    assert outcome.attempted_providers == ()
    assert outcome.reason == "no search provider is enabled"


def test_all_enabled_providers_without_usable_results_reports_unavailable() -> None:
    first = FakeSearchProvider("first", results=[])
    second = FakeSearchProvider("second", error=RuntimeError("provider down"))

    outcome = InternetSearchService([first, second]).search("query")

    assert outcome.status == "unavailable"
    assert outcome.provider is None
    assert outcome.attempted_providers == ("first", "second")
    assert outcome.reason == "no enabled provider returned usable results"


def test_blank_query_is_rejected_without_calling_providers() -> None:
    provider = FakeSearchProvider("first", results=[_result("https://a.example", "first")])

    outcome = InternetSearchService([provider]).search("   ")

    assert outcome.status == "unavailable"
    assert outcome.reason == "empty search query"
    assert provider.queries == []


def test_result_count_is_bounded_by_max_results() -> None:
    results = [_result(f"https://a.example/{index}", "first") for index in range(5)]
    provider = FakeSearchProvider("first", results=results)

    outcome = InternetSearchService([provider]).search("query", max_results=2)

    assert len(outcome.results) == 2


def test_is_available_reflects_any_enabled_provider() -> None:
    assert InternetSearchService([FakeSearchProvider("on")]).is_available() is True
    assert InternetSearchService([FakeSearchProvider("off", available=False)]).is_available() is False
    assert InternetSearchService([]).is_available() is False


def test_turn_search_summary_defaults_to_not_requested() -> None:
    summary = TurnSearchSummary()

    assert summary.requested is False
    assert summary.status == "not_requested"
    assert summary.provider is None
    assert summary.sources == ()
    assert summary.reason is None
