from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from backend.app.cognition.prompt_envelope import PromptSegment
from backend.app.runtimes.internetsearch import SearchResult

SEARCH_DIRECTIVE_PREFIX = "SEARCH:"
MAX_SEARCH_QUERY_LENGTH = 200
MAX_SEARCH_RESULTS = 3
MAX_RESULT_TITLE_LENGTH = 120
MAX_RESULT_SNIPPET_LENGTH = 400
MAX_RESULT_URL_LENGTH = 300

SEARCH_UNAVAILABLE_RESPONSE = (
    "I couldn't verify that with live search because no configured search provider returned results."
)


@dataclass(frozen=True, slots=True)
class SearchDecision:
    requested: bool
    query: str | None
    reason: str  # "explicit-search-decision" | "ordinary-response"


def parse_search_directive(response_text: str, *, max_query_length: int = MAX_SEARCH_QUERY_LENGTH) -> SearchDecision:
    """Parse the model's first response into an explicit search decision.

    The directive matches only when the first line of the response starts with
    the exact reserved prefix. Anything else is the ordinary assistant answer.
    The proposed query is trimmed and clamped to a fixed maximum length; it is
    never interpreted as an endpoint or command.
    """
    stripped = response_text.strip()
    first_line = stripped.splitlines()[0] if stripped else ""
    if not first_line.startswith(SEARCH_DIRECTIVE_PREFIX):
        return SearchDecision(requested=False, query=None, reason="ordinary-response")
    query = first_line[len(SEARCH_DIRECTIVE_PREFIX):].strip()[:max_query_length].strip()
    if not query:
        return SearchDecision(requested=False, query=None, reason="ordinary-response")
    return SearchDecision(requested=True, query=query, reason="explicit-search-decision")


def search_instruction_segment() -> PromptSegment:
    return PromptSegment(
        authority="application",
        content_type="instruction",
        trusted=True,
        text=(
            "Live internet search is available for this turn. If the request needs current or "
            "recent information you cannot verify from what you already know, reply with exactly "
            f"one line in the form `{SEARCH_DIRECTIVE_PREFIX} <search query>` and nothing else. "
            "Otherwise answer normally."
        ),
    )


def search_results_segment(results: Sequence[SearchResult]) -> PromptSegment:
    lines: list[str] = []
    for item in results[:MAX_SEARCH_RESULTS]:
        lines.append(
            "- title: {title}\n  url: {url}\n  snippet: {snippet}\n  provider: {provider}".format(
                title=item.title[:MAX_RESULT_TITLE_LENGTH],
                url=item.url[:MAX_RESULT_URL_LENGTH],
                snippet=item.snippet[:MAX_RESULT_SNIPPET_LENGTH],
                provider=item.source,
            )
        )
    return PromptSegment(
        authority="tool",
        content_type="tool_result",
        trusted=False,
        text="Live search results:\n" + "\n".join(lines),
    )


def search_answer_contract_segment() -> PromptSegment:
    return PromptSegment(
        authority="output",
        content_type="contract",
        trusted=True,
        text=(
            "Live search has already run for this turn. Answer the user's original request using "
            "the relevant returned results. Cite only URLs present in the supplied results. Do not "
            "invent sources or claim broader browsing. If the results do not support a firm answer, "
            "say so plainly. Do not request another search."
        ),
    )
