from __future__ import annotations

from backend.app.cognition.search_directive import (
    MAX_RESULT_SNIPPET_LENGTH,
    MAX_RESULT_TITLE_LENGTH,
    MAX_RESULT_URL_LENGTH,
    MAX_SEARCH_QUERY_LENGTH,
    MAX_SEARCH_RESULTS,
    parse_search_directive,
    search_answer_contract_segment,
    search_instruction_segment,
    search_results_segment,
)
from backend.app.runtimes.internetsearch import SearchResult


def test_parse_directive_extracts_trimmed_query() -> None:
    decision = parse_search_directive("  SEARCH:   latest CUDA release  \n")

    assert decision.requested is True
    assert decision.query == "latest CUDA release"
    assert decision.reason == "explicit-search-decision"


def test_parse_directive_uses_only_the_first_line() -> None:
    decision = parse_search_directive("SEARCH: current weather\nextra prose")

    assert decision.requested is True
    assert decision.query == "current weather"


def test_ordinary_answer_is_not_a_directive() -> None:
    decision = parse_search_directive("The capital of France is Paris.")

    assert decision.requested is False
    assert decision.query is None
    assert decision.reason == "ordinary-response"


def test_directive_prefix_is_case_sensitive() -> None:
    assert parse_search_directive("Search: engines history").requested is False
    assert parse_search_directive("search: engines history").requested is False


def test_directive_mentioned_mid_answer_is_not_a_directive() -> None:
    assert parse_search_directive("You could reply SEARCH: something to search.").requested is False


def test_empty_query_is_rejected_as_ordinary_response() -> None:
    decision = parse_search_directive("SEARCH:   ")

    assert decision.requested is False
    assert decision.query is None


def test_query_is_clamped_to_fixed_maximum_length() -> None:
    decision = parse_search_directive("SEARCH: " + "q" * (MAX_SEARCH_QUERY_LENGTH + 50))

    assert decision.requested is True
    assert decision.query is not None
    assert len(decision.query) == MAX_SEARCH_QUERY_LENGTH


def test_instruction_segment_is_trusted_application_instruction() -> None:
    segment = search_instruction_segment()

    assert segment.authority == "application"
    assert segment.content_type == "instruction"
    assert segment.trusted is True
    assert "SEARCH:" in segment.text


def test_results_segment_is_untrusted_tool_result_with_bounded_fields() -> None:
    oversized = SearchResult(
        title="t" * (MAX_RESULT_TITLE_LENGTH + 100),
        url="https://example.com/" + "u" * MAX_RESULT_URL_LENGTH,
        snippet="s" * (MAX_RESULT_SNIPPET_LENGTH + 100),
        source="fake",
    )
    segment = search_results_segment([oversized] * (MAX_SEARCH_RESULTS + 2))

    assert segment.authority == "tool"
    assert segment.content_type == "tool_result"
    assert segment.trusted is False
    assert segment.text.count("- title:") == MAX_SEARCH_RESULTS
    assert "t" * (MAX_RESULT_TITLE_LENGTH + 1) not in segment.text
    assert "s" * (MAX_RESULT_SNIPPET_LENGTH + 1) not in segment.text


def test_answer_contract_segment_is_trusted_output_contract() -> None:
    segment = search_answer_contract_segment()

    assert segment.authority == "output"
    assert segment.content_type == "contract"
    assert segment.trusted is True
    assert "Cite only URLs" in segment.text
