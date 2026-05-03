from __future__ import annotations

import json

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


class _FakeCache:
    def __init__(self) -> None:
        self.available = True
        self.store: dict[str, str] = {}
        self.last_get_key: str | None = None
        self.last_set: tuple[str, str, int] | None = None
        self.raise_on_get = False
        self.raise_on_set = False

    def is_available(self) -> bool:
        return self.available

    def get(self, key: str) -> str | None:
        if self.raise_on_get:
            raise RuntimeError("get failed")
        self.last_get_key = key
        return self.store.get(key)

    def set(self, key: str, value: str, ttl: int) -> bool:
        if self.raise_on_set:
            raise RuntimeError("set failed")
        self.last_set = (key, value, ttl)
        self.store[key] = value
        return True


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


def test_retrieve_populates_cache_on_first_call() -> None:
    episodic = _FakeEpisodic()
    cache = _FakeCache()
    facts = RetrievalManager().retrieve(query="apple", n=2, cache_manager=cache, episodic=episodic)  # type: ignore[arg-type]
    assert len(facts) == 1
    assert cache.last_set is not None
    key, payload, ttl = cache.last_set
    assert key.startswith("retrieval:keyword:")
    assert key.endswith(":2")
    assert ttl == 300
    decoded = json.loads(payload)
    assert decoded[0]["turn_id"] == "t2"


def test_retrieve_uses_cache_on_second_call() -> None:
    episodic = _FakeEpisodic()
    cache = _FakeCache()
    manager = RetrievalManager()
    first = manager.retrieve(query="apple", n=2, cache_manager=cache, episodic=episodic)  # type: ignore[arg-type]
    episodic.keyword_called_with = None
    second = manager.retrieve(query="apple", n=2, cache_manager=cache, episodic=episodic)  # type: ignore[arg-type]
    assert len(first) == len(second) == 1
    assert episodic.keyword_called_with is None
    assert second[0].turn_id == "t2"


def test_retrieve_falls_back_to_disk_when_cache_unavailable() -> None:
    episodic = _FakeEpisodic()
    cache = _FakeCache()
    cache.available = False
    facts = RetrievalManager().retrieve(query="apple", n=2, cache_manager=cache, episodic=episodic)  # type: ignore[arg-type]
    assert episodic.keyword_called_with == ("apple", 2)
    assert len(facts) == 1


def test_retrieve_falls_back_to_disk_when_cache_get_none() -> None:
    episodic = _FakeEpisodic()
    cache = _FakeCache()
    facts = RetrievalManager().retrieve(query="apple", n=2, cache_manager=cache, episodic=episodic)  # type: ignore[arg-type]
    assert episodic.keyword_called_with == ("apple", 2)
    assert len(facts) == 1


def test_retrieve_falls_back_to_disk_when_cache_get_raises() -> None:
    episodic = _FakeEpisodic()
    cache = _FakeCache()
    cache.raise_on_get = True
    facts = RetrievalManager().retrieve(query="apple", n=2, cache_manager=cache, episodic=episodic)  # type: ignore[arg-type]
    assert episodic.keyword_called_with == ("apple", 2)
    assert len(facts) == 1


def test_retrieve_falls_back_to_disk_on_invalid_cached_json() -> None:
    episodic = _FakeEpisodic()
    cache = _FakeCache()
    cache.store["retrieval:keyword:xyz:2"] = "not-json"
    manager = RetrievalManager()
    key = manager._cache_key("apple", 2)
    cache.store[key] = "not-json"
    facts = manager.retrieve(query="apple", n=2, cache_manager=cache, episodic=episodic)  # type: ignore[arg-type]
    assert episodic.keyword_called_with == ("apple", 2)
    assert len(facts) == 1


def test_retrieve_cache_set_raising_does_not_fail_retrieval() -> None:
    episodic = _FakeEpisodic()
    cache = _FakeCache()
    cache.raise_on_set = True
    facts = RetrievalManager().retrieve(query="apple", n=2, cache_manager=cache, episodic=episodic)  # type: ignore[arg-type]
    assert len(facts) == 1


def test_keyword_and_recency_keys_are_distinct_and_include_n() -> None:
    manager = RetrievalManager()
    key_keyword_n2 = manager._cache_key("apple", 2)
    key_keyword_n3 = manager._cache_key("apple", 3)
    key_recency_n2 = manager._cache_key(None, 2)
    assert key_keyword_n2 != key_recency_n2
    assert key_keyword_n2 != key_keyword_n3
    assert key_keyword_n2.endswith(":2")
    assert key_keyword_n3.endswith(":3")
    assert key_recency_n2 == "retrieval:recency:2"


def test_cached_facts_preserve_provenance_fields() -> None:
    episodic = _FakeEpisodic()
    cache = _FakeCache()
    manager = RetrievalManager()
    first = manager.retrieve(query="apple", n=2, cache_manager=cache, episodic=episodic)  # type: ignore[arg-type]
    episodic.keyword_called_with = None
    second = manager.retrieve(query="apple", n=2, cache_manager=cache, episodic=episodic)  # type: ignore[arg-type]
    assert episodic.keyword_called_with is None
    assert first[0].turn_id == second[0].turn_id
    assert first[0].session_id == second[0].session_id
    assert first[0].source_field == second[0].source_field
    assert first[0].relevance_method == second[0].relevance_method
