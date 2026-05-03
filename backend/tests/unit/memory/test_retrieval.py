from __future__ import annotations

from backend.app.memory.episodic import EpisodicEntry
from backend.app.memory.retrieval import RetrievalManager


class _FakeEpisodic:
    def __init__(self) -> None:
        self.recent_called = False
        self.keyword_called_with: tuple[str, int] | None = None

    def retrieve_recent(self, n: int = 5):
        self.recent_called = True
        return [EpisodicEntry("t1", "s1", "x", "hello", "world", [], "2026-01-01T00:00:00+00:00")]

    def retrieve_by_keyword(self, keyword: str, n: int = 5):
        self.keyword_called_with = (keyword, n)
        return [EpisodicEntry("t2", "s2", "x", "apple", "banana", [], "2026-01-01T00:00:00+00:00")]


def test_retrieve_returns_recent_facts_when_no_query() -> None:
    episodic = _FakeEpisodic()
    facts = RetrievalManager().retrieve(query=None, n=3, episodic=episodic)  # type: ignore[arg-type]
    assert episodic.recent_called is True
    assert facts[0].relevance_method == "recency"


def test_retrieve_returns_keyword_facts_when_query_given() -> None:
    episodic = _FakeEpisodic()
    facts = RetrievalManager().retrieve(query="apple", n=2, episodic=episodic)  # type: ignore[arg-type]
    assert episodic.keyword_called_with == ("apple", 2)
    assert facts[0].relevance_method == "keyword"


def test_retrieve_returns_empty_list_when_episodic_unavailable() -> None:
    assert RetrievalManager().retrieve(query="x", episodic=None) == []


def test_retrieved_fact_has_provenance_fields() -> None:
    episodic = _FakeEpisodic()
    fact = RetrievalManager().retrieve(query="x", episodic=episodic)[0]  # type: ignore[arg-type]
    assert fact.turn_id
    assert fact.session_id
    assert fact.source_field in {"response_text", "transcript"}
