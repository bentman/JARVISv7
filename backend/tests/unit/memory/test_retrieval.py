from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.memory.curation import OperationStatus, StoreResult
from backend.app.memory.episodic import EpisodicEntry, EpisodicMemory
from backend.app.memory.retrieval import RetrievalManager, RetrievedFact
from backend.app.memory.semantic import SemanticEntry, SemanticMemory, text_to_vector
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
    assert facts_lex[0].relevance_method == "lexical+vector"
    assert facts_lex[0].semantic_fact_id is not None
    assert facts_lex[0].source_kind == "semantic"

    # 2. Vector retrieval
    facts_vec = retrieval.retrieve(query="capital Spain", n=1, episodic=None, semantic=semantic)
    assert len(facts_vec) == 1
    assert facts_vec[0].content == "The capital of Spain is Madrid."
    assert facts_vec[0].relevance_method == "lexical+vector"


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


def test_distinct_cross_source_records_are_not_collapsed_by_content(tmp_path: Path):
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

    # Identical display text does not erase either source identity or its RRF contribution.
    facts = retrieval.retrieve(query="content", n=5, episodic=episodic, semantic=semantic)
    assert len(facts) == 2
    assert [fact.content for fact in facts] == ["Identical content.", "Identical content."]
    assert {fact.source_kind for fact in facts} == {"episodic", "semantic"}


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


def test_episodic_revision_changes_cache_identity_after_a_write(tmp_path: Path) -> None:
    episodic = EpisodicMemory(
        base_dir=tmp_path / "episodic",
        sessions_base_dir=tmp_path / "sessions",
    )
    cache = MockCacheManager()
    retrieval = RetrievalManager()
    policy = WritePolicy()

    episodic.write_entry(
        TurnArtifact(
            turn_id="turn-1",
            session_id="session-1",
            input_modality="text",
            final_state="IDLE",
            transcript="first",
            response_text="first episodic response",
        ),
        policy,
    )
    first = retrieval.retrieve("episodic", n=3, cache_manager=cache, episodic=episodic)

    episodic.write_entry(
        TurnArtifact(
            turn_id="turn-2",
            session_id="session-1",
            input_modality="text",
            final_state="IDLE",
            transcript="episodic",
            response_text="second episodic response",
        ),
        policy,
    )
    refreshed = retrieval.retrieve("episodic", n=3, cache_manager=cache, episodic=episodic)

    assert [fact.turn_id for fact in first] == ["turn-1"]
    assert [fact.turn_id for fact in refreshed] == ["turn-2", "turn-1"]
    assert len(cache.store) == 2


def _semantic_entry(
    fact_id: str,
    *,
    content: str = "same content",
    authority: str = "legacy_unknown",
    confidence: float | None = None,
    importance: float | None = None,
    reinforcement_count: int = 1,
    updated_at: str = "2026-07-01T00:00:00+00:00",
) -> SemanticEntry:
    vector = text_to_vector(content)
    return SemanticEntry(
        fact_id=fact_id,
        text=content,
        source_session_id="source-session",
        source_turn_id=f"source-{fact_id}",
        source_field="transcript",
        created_at=updated_at,
        updated_at=updated_at,
        kind="personal_fact",
        confidence=confidence,
        metadata={},
        vectorizer_id="hashing-v1",
        vector_dim=len(vector),
        vector_blob=vector.astype("<f4").tobytes(),
        text_hash=f"hash-{fact_id}",
        evidence_authority=authority,
        state="active",
        importance=importance,
        reinforcement_count=reinforcement_count,
        evidence_refs=(
            {
                "evidence_id": f"evidence-{fact_id}",
                "evidence_authority": authority,
                "source_session_id": "source-session",
                "source_turn_id": f"source-{fact_id}",
                "source_field": "transcript",
            },
        ),
    )


class _FakeSemantic:
    def __init__(
        self,
        lexical: list[SemanticEntry],
        vector: list[SemanticEntry],
        *,
        revision: int = 7,
    ) -> None:
        self.lexical = lexical
        self.vector = vector
        self.revision = revision

    def read_content_revision(self) -> StoreResult[int]:
        return StoreResult(OperationStatus.SUCCESS, self.revision)

    def search_lexical(self, query: str, n: int = 5) -> list[SemanticEntry]:
        return self.lexical[:n]

    def search_vector(self, query_vector, n: int = 5):
        return [(entry, 0.5) for entry in self.vector[:n]]


def test_semantic_lexical_and_vector_hits_fuse_by_fact_id() -> None:
    entry = _semantic_entry("fact-one")

    facts = RetrievalManager().retrieve(
        "same",
        n=3,
        semantic=_FakeSemantic([entry], [entry]),  # type: ignore[arg-type]
    )

    assert len(facts) == 1
    assert facts[0].semantic_fact_id == "fact-one"
    assert facts[0].relevance_method == "lexical+vector"
    assert facts[0].retrieval_scores is not None
    assert facts[0].retrieval_scores["rrf_score"] == pytest.approx(2 / 61)


def test_distinct_semantic_facts_with_same_content_keep_distinct_identity() -> None:
    first = _semantic_entry("fact-a")
    second = _semantic_entry("fact-b")

    facts = RetrievalManager().retrieve(
        "same",
        n=3,
        semantic=_FakeSemantic([first, second], [second, first]),  # type: ignore[arg-type]
    )

    assert {fact.semantic_fact_id for fact in facts} == {"fact-a", "fact-b"}


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (
            {"fact_id": "fact-a", "authority": "direct_user_action"},
            {"fact_id": "fact-b", "authority": "direct_user_statement"},
            "fact-a",
        ),
        (
            {"fact_id": "fact-a", "authority": "direct_user_statement"},
            {"fact_id": "fact-b", "authority": "assistant_inference"},
            "fact-a",
        ),
        (
            {"fact_id": "fact-a", "authority": "assistant_inference"},
            {"fact_id": "fact-b", "authority": "synthesized_summary"},
            "fact-a",
        ),
        (
            {"fact_id": "fact-a", "authority": "synthesized_summary"},
            {"fact_id": "fact-b", "authority": "imported_record"},
            "fact-a",
        ),
        (
            {"fact_id": "fact-a", "authority": "imported_record"},
            {"fact_id": "fact-b", "authority": "legacy_unknown"},
            "fact-a",
        ),
        (
            {"fact_id": "fact-a", "authority": "legacy_unknown", "confidence": 0.9},
            {"fact_id": "fact-b", "authority": "legacy_unknown", "confidence": 0.2},
            "fact-a",
        ),
        (
            {"fact_id": "fact-a", "authority": "legacy_unknown", "importance": 0.9},
            {"fact_id": "fact-b", "authority": "legacy_unknown", "importance": 0.2},
            "fact-a",
        ),
        (
            {"fact_id": "fact-a", "authority": "legacy_unknown", "reinforcement_count": 4},
            {"fact_id": "fact-b", "authority": "legacy_unknown", "reinforcement_count": 2},
            "fact-a",
        ),
        (
            {
                "fact_id": "fact-a",
                "authority": "legacy_unknown",
                "updated_at": "2026-07-02T00:00:00+00:00",
            },
            {
                "fact_id": "fact-b",
                "authority": "legacy_unknown",
                "updated_at": "2026-07-01T00:00:00+00:00",
            },
            "fact-a",
        ),
        (
            {"fact_id": "fact-z", "authority": "legacy_unknown"},
            {"fact_id": "fact-a", "authority": "legacy_unknown"},
            "fact-a",
        ),
    ],
)
def test_equal_rrf_uses_exact_quality_then_stable_id_order(
    first: dict[str, object],
    second: dict[str, object],
    expected: str,
) -> None:
    lexical = _semantic_entry(**first)  # type: ignore[arg-type]
    vector = _semantic_entry(**second)  # type: ignore[arg-type]

    facts = RetrievalManager().retrieve(
        "same",
        n=2,
        semantic=_FakeSemantic([lexical], [vector]),  # type: ignore[arg-type]
    )

    assert facts[0].semantic_fact_id == expected


def test_higher_rrf_score_beats_quality_metadata() -> None:
    repeated = _semantic_entry("fact-repeated", authority="legacy_unknown")
    direct = _semantic_entry("fact-direct", authority="direct_user_action")

    facts = RetrievalManager().retrieve(
        "same",
        n=2,
        semantic=_FakeSemantic([repeated], [repeated, direct]),  # type: ignore[arg-type]
    )

    assert facts[0].semantic_fact_id == "fact-repeated"


def test_episodic_transcript_uses_direct_statement_tie_compatibility() -> None:
    entry = EpisodicEntry(
        turn_id="turn-episodic",
        session_id="session-episodic",
        session_started_at="2026-07-01T00:00:00+00:00",
        transcript="same tie content",
        response_text=None,
        tools_invoked=[],
        written_at="2026-07-01T00:00:00+00:00",
    )

    class EpisodicTranscript:
        def retrieve_by_keyword(self, query: str, n: int = 5):
            return [entry]

    episodic = EpisodicTranscript()
    semantic_entry = _semantic_entry(
        "fact-semantic",
        authority="assistant_inference",
    )

    facts = RetrievalManager().retrieve(
        "same",
        n=2,
        episodic=episodic,  # type: ignore[arg-type]
        semantic=_FakeSemantic([semantic_entry], []),  # type: ignore[arg-type]
    )

    assert facts[0].source_kind == "episodic"
    assert facts[0].source_field == "transcript"


def test_direct_user_action_semantic_tie_precedes_episodic_transcript() -> None:
    entry = EpisodicEntry(
        turn_id="turn-episodic",
        session_id="session-episodic",
        session_started_at="2026-07-01T00:00:00+00:00",
        transcript="same tie content",
        response_text=None,
        tools_invoked=[],
        written_at="2026-07-01T00:00:00+00:00",
    )

    class EpisodicTranscript:
        def retrieve_by_keyword(self, query: str, n: int = 5):
            return [entry]

    episodic = EpisodicTranscript()
    semantic_entry = _semantic_entry(
        "fact-semantic",
        authority="direct_user_action",
    )

    facts = RetrievalManager().retrieve(
        "same",
        n=2,
        episodic=episodic,  # type: ignore[arg-type]
        semantic=_FakeSemantic([semantic_entry], []),  # type: ignore[arg-type]
    )

    assert facts[0].semantic_fact_id == "fact-semantic"


def test_semantic_revision_changes_cache_identity_and_roundtrips_provenance(
    tmp_path: Path,
) -> None:
    semantic = SemanticMemory(tmp_path / "memory.sqlite")
    first_id = semantic.write_fact(
        "revision target one",
        source_session_id="session-1",
        source_turn_id="turn-1",
        source_field="transcript",
    )
    assert first_id is not None
    cache = MockCacheManager()
    retrieval = RetrievalManager()

    first = retrieval.retrieve("revision target", n=5, cache_manager=cache, semantic=semantic)
    cached = retrieval.retrieve("revision target", n=5, cache_manager=cache, semantic=semantic)
    second_id = semantic.write_fact(
        "revision target two",
        source_session_id="session-2",
        source_turn_id="turn-2",
        source_field="transcript",
    )
    refreshed = retrieval.retrieve("revision target", n=5, cache_manager=cache, semantic=semantic)

    assert first == cached
    assert first[0].semantic_fact_id == first_id
    assert first[0].source_evidence_refs
    assert second_id is not None
    assert {fact.semantic_fact_id for fact in refreshed} == {first_id, second_id}
    assert len(cache.store) == 2
    assert any(":r1:" in key for key in cache.store)
    assert any(":r2:" in key for key in cache.store)


def test_incompatible_cached_payload_is_ignored_safely(tmp_path: Path) -> None:
    semantic = SemanticMemory(tmp_path / "memory.sqlite")
    semantic.write_fact("safe cache fallback")
    retrieval = RetrievalManager()
    cache = MockCacheManager()
    key = retrieval._cache_key(
        "safe",
        1,
        has_semantic=True,
        semantic_revision=1,
    )
    cache.store[key] = json.dumps(
        [
            {
                "turn_id": "turn",
                "session_id": "session",
                "content": "poisoned",
                "source_field": "text",
                "relevance_method": "vector",
                "source_kind": "unsupported",
            }
        ]
    )

    facts = retrieval.retrieve("safe", n=1, cache_manager=cache, semantic=semantic)

    assert facts[0].content == "safe cache fallback"


def test_legacy_episodic_cache_payload_remains_compatible() -> None:
    payload = json.dumps(
        [
            {
                "turn_id": "turn-1",
                "session_id": "session-1",
                "content": "legacy cached content",
                "source_field": "response_text",
                "relevance_method": "keyword",
            }
        ]
    )

    facts = RetrievalManager()._facts_from_cache_value(payload)

    assert facts == [
        RetrievedFact(
            turn_id="turn-1",
            session_id="session-1",
            content="legacy cached content",
            source_field="response_text",
            relevance_method="keyword",
        )
    ]


def test_semantic_revision_read_failure_disables_cache_but_not_retrieval() -> None:
    entry = _semantic_entry("fact-one")

    class RevisionFailure(_FakeSemantic):
        def read_content_revision(self):
            raise RuntimeError("revision unavailable")

    semantic = RevisionFailure([entry], [entry])
    cache = MockCacheManager()

    facts = RetrievalManager().retrieve(
        "same",
        n=1,
        cache_manager=cache,
        semantic=semantic,  # type: ignore[arg-type]
    )

    assert facts[0].semantic_fact_id == "fact-one"
    assert cache.store == {}
