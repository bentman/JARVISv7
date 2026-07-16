from __future__ import annotations

import pytest
from pathlib import Path
import json

from backend.app.memory.episodic import EpisodicMemory, EpisodicEntry
from backend.app.memory.semantic import SemanticMemory, text_to_vector
from backend.app.memory.retrieval import RetrievalManager, RetrievedFact
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.memory.write_policy import WritePolicy


class MockCacheManager:
    def __init__(self, available: bool = True):
        self.available = available
        self.store = {}

    def get(self, key: str) -> str | None:
        if not self.available:
            raise Exception("Redis disconnected")
        return self.store.get(key)

    def set(self, key: str, value: str, ttl: int) -> bool:
        if not self.available:
            raise Exception("Redis disconnected")
        self.store[key] = value
        return True

    def is_available(self) -> bool:
        if not self.available:
            return False
        return True


def test_episodic_only_retrieval(tmp_path: Path):
    episodic_dir = tmp_path / "episodic"
    episodic = EpisodicMemory(base_dir=episodic_dir, sessions_base_dir=tmp_path / "sessions")
    
    # Write episodic entries
    policy = WritePolicy()
    artifact_1 = TurnArtifact(
        turn_id="t-1",
        session_id="s-1",
        input_modality="text",
        final_state="completed",
        transcript="what is the capital of France?",
        response_text="The capital of France is Paris.",
        tools_invoked=[],
    )
    episodic.write_entry(artifact_1, policy)

    retrieval = RetrievalManager()
    
    # 1. Recency retrieval
    facts_recency = retrieval.retrieve(query=None, n=1, episodic=episodic, semantic=None)
    assert len(facts_recency) == 1
    assert facts_recency[0].content == "The capital of France is Paris."
    assert facts_recency[0].relevance_method == "recency"

    # 2. Keyword retrieval
    facts_kw = retrieval.retrieve(query="Paris", n=1, episodic=episodic, semantic=None)
    assert len(facts_kw) == 1
    assert facts_kw[0].content == "The capital of France is Paris."
    assert facts_kw[0].relevance_method == "keyword"

    # 3. No matches
    facts_none = retrieval.retrieve(query="Berlin", n=1, episodic=episodic, semantic=None)
    assert len(facts_none) == 0


def test_semantic_only_retrieval(tmp_path: Path):
    db_path = tmp_path / "memory.sqlite"
    semantic = SemanticMemory(db_path)
    
    # Write semantic entry
    semantic.write_fact(
        text="The capital of Spain is Madrid.",
        vector=None,
        vectorizer_id=None,
        source_session_id="s-1",
        source_turn_id="t-2",
        source_field="response_text"
    )

    retrieval = RetrievalManager()

    # 1. Lexical retrieval
    facts_lex = retrieval.retrieve(query="Madrid", n=1, episodic=None, semantic=semantic)
    assert len(facts_lex) == 1
    assert facts_lex[0].content == "The capital of Spain is Madrid."
    assert facts_lex[0].relevance_method == "lexical"

    # 2. Vector retrieval
    facts_vec = retrieval.retrieve(query="capital Spain", n=1, episodic=None, semantic=semantic)
    assert len(facts_vec) == 1
    assert facts_vec[0].content == "The capital of Spain is Madrid."
    # With RRF rank merging, when query is not None and semantic is not None,
    # the returned relevance_method is the method of the winning candidate in fact_map.
    # Depending on list ordering, it could be 'lexical' or 'vector'. Both are fine.
    assert facts_vec[0].relevance_method in {"lexical", "vector"}


def test_hybrid_retrieval_and_rrf_rank_merge(tmp_path: Path):
    episodic_dir = tmp_path / "episodic"
    episodic = EpisodicMemory(base_dir=episodic_dir, sessions_base_dir=tmp_path / "sessions")
    
    db_path = tmp_path / "memory.sqlite"
    semantic = SemanticMemory(db_path)

    policy = WritePolicy()
    
    # Write same concept to episodic and semantic with slightly different wording to test RRF ranking
    # Episodic match
    artifact = TurnArtifact(
        turn_id="t-1",
        session_id="s-1",
        input_modality="text",
        final_state="completed",
        transcript="weather in London",
        response_text="It is raining in London.",
        tools_invoked=[],
    )
    episodic.write_entry(artifact, policy)

    # Semantic match
    semantic.write_fact("London is famous for its rainy weather.", source_session_id="s-1", source_turn_id="t-1")
    semantic.write_fact("Unrelated semantic fact.", source_session_id="s-1", source_turn_id="t-2")

    retrieval = RetrievalManager()
    
    # Retrieve top 2 facts for query "London"
    facts = retrieval.retrieve(query="London", n=2, episodic=episodic, semantic=semantic)

    # Should return both facts, ordered by RRF rank score
    assert len(facts) == 2
    contents = {f.content for f in facts}
    assert "It is raining in London." in contents
    assert "London is famous for its rainy weather." in contents
    assert "Unrelated semantic fact." not in contents


def test_deduplication_between_sources(tmp_path: Path):
    episodic_dir = tmp_path / "episodic"
    episodic = EpisodicMemory(base_dir=episodic_dir, sessions_base_dir=tmp_path / "sessions")
    
    db_path = tmp_path / "memory.sqlite"
    semantic = SemanticMemory(db_path)

    policy = WritePolicy()

    # Write IDENTICAL text to both
    artifact = TurnArtifact(
        turn_id="t-1",
        session_id="s-1",
        input_modality="text",
        final_state="completed",
        transcript="ident",
        response_text="Identical content.",
        tools_invoked=[],
    )
    episodic.write_entry(artifact, policy)
    semantic.write_fact("Identical content.", source_session_id="s-1", source_turn_id="t-1")

    retrieval = RetrievalManager()

    # Retrieval should merge them and return only 1 copy of the fact
    facts = retrieval.retrieve(query="content", n=5, episodic=episodic, semantic=semantic)
    assert len(facts) == 1
    assert facts[0].content == "Identical content."


def test_cache_miss_hit_and_corruption(tmp_path: Path):
    episodic_dir = tmp_path / "episodic"
    episodic = EpisodicMemory(base_dir=episodic_dir, sessions_base_dir=tmp_path / "sessions")
    db_path = tmp_path / "memory.sqlite"
    semantic = SemanticMemory(db_path)

    policy = WritePolicy()
    artifact = TurnArtifact(
        turn_id="t-1",
        session_id="s-1",
        input_modality="text",
        final_state="completed",
        transcript="test",
        response_text="Cache test response.",
        tools_invoked=[],
    )
    episodic.write_entry(artifact, policy)

    retrieval = RetrievalManager()
    cache = MockCacheManager(available=True)

    # 1. First retrieve: Cache miss, writes to cache
    facts_1 = retrieval.retrieve("test", n=1, cache_manager=cache, episodic=episodic, semantic=semantic)
    assert len(facts_1) == 1
    assert len(cache.store) == 1  # Should have 1 cache key written
    
    # 2. Second retrieve: Cache hit
    facts_2 = retrieval.retrieve("test", n=1, cache_manager=cache, episodic=episodic, semantic=semantic)
    assert len(facts_2) == 1
    assert facts_2[0].content == "Cache test response."

    # 3. Corrupt the cache value
    cache_key = list(cache.store.keys())[0]
    cache.store[cache_key] = "{invalid json string}"

    # 4. Third retrieve: Cache corruption fallback to database
    facts_3 = retrieval.retrieve("test", n=1, cache_manager=cache, episodic=episodic, semantic=semantic)
    assert len(facts_3) == 1
    assert facts_3[0].content == "Cache test response."


def test_redis_unavailable_fallback(tmp_path: Path):
    episodic_dir = tmp_path / "episodic"
    episodic = EpisodicMemory(base_dir=episodic_dir, sessions_base_dir=tmp_path / "sessions")
    db_path = tmp_path / "memory.sqlite"
    semantic = SemanticMemory(db_path)

    policy = WritePolicy()
    artifact = TurnArtifact(
        turn_id="t-1",
        session_id="s-1",
        input_modality="text",
        final_state="completed",
        transcript="test",
        response_text="Redis down response.",
        tools_invoked=[],
    )
    episodic.write_entry(artifact, policy)

    retrieval = RetrievalManager()
    cache = MockCacheManager(available=False)  # Redis unavailable

    # Retrieve should not crash and should correctly query DB
    facts = retrieval.retrieve("test", n=1, cache_manager=cache, episodic=episodic, semantic=semantic)
    assert len(facts) == 1
    assert facts[0].content == "Redis down response."


def test_cached_result_from_missing_backend_not_served_after_backend_returns(tmp_path: Path):
    """A recency result cached while episodic was unavailable must not mask real entries later."""
    episodic_dir = tmp_path / "episodic"
    episodic = EpisodicMemory(base_dir=episodic_dir, sessions_base_dir=tmp_path / "sessions")
    semantic = SemanticMemory(tmp_path / "memory.sqlite")
    episodic.write_entry(
        TurnArtifact(
            turn_id="t-1",
            session_id="s-1",
            input_modality="text",
            final_state="completed",
            transcript="hello there",
            response_text="General Kenobi, a long enough response.",
            tools_invoked=[],
        ),
        WritePolicy(),
    )

    cache = MockCacheManager(available=True)
    retrieval = RetrievalManager()

    # Episodic backend down: recency retrieval computes (and caches) an empty result.
    degraded = retrieval.retrieve(query=None, n=1, cache_manager=cache, episodic=None, semantic=semantic)
    assert degraded == []

    # Episodic backend back: the degraded cached empty result must not be served.
    recovered = retrieval.retrieve(query=None, n=1, cache_manager=cache, episodic=episodic, semantic=semantic)
    assert len(recovered) == 1
    assert recovered[0].turn_id == "t-1"


def test_cache_key_distinguishes_backend_availability():
    manager = RetrievalManager()
    keys = {
        manager._cache_key(query=None, n=3, has_episodic=True, has_semantic=True),
        manager._cache_key(query=None, n=3, has_episodic=False, has_semantic=True),
        manager._cache_key(query="q", n=3, has_episodic=True, has_semantic=True),
        manager._cache_key(query="q", n=3, has_episodic=False, has_semantic=True),
        manager._cache_key(query="q", n=3, has_episodic=True, has_semantic=False),
    }
    assert len(keys) == 5
