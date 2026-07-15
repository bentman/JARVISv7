from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest
from backend.app.memory.semantic import SemanticMemory, _get_text_hash


def test_init_db(tmp_path: Path):
    db_path = tmp_path / "subdir" / "memory.sqlite"
    memory = SemanticMemory(db_path)
    assert db_path.exists()

    # Verify tables
    with memory._get_conn() as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {row["name"] for row in tables}
        assert "semantic_meta" in table_names
        assert "semantic_fact" in table_names
        if memory.supports_fts:
            assert "semantic_fact_fts" in table_names


def test_write_read_entry(tmp_path: Path):
    db_path = tmp_path / "memory.sqlite"
    memory = SemanticMemory(db_path)

    vector = [0.1, 0.2, 0.3, 0.4]
    fact_id = memory.write_fact(
        text="Hello world test",
        vector=vector,
        vectorizer_id="test-vec-1",
        source_session_id="session-1",
        source_turn_id="turn-1",
        source_field="response_text",
        confidence=0.95,
        metadata={"custom": "info"},
    )
    assert fact_id is not None

    entry = memory.read_entry(fact_id)
    assert entry is not None
    assert entry.fact_id == fact_id
    assert entry.text == "Hello world test"
    assert entry.source_session_id == "session-1"
    assert entry.source_turn_id == "turn-1"
    assert entry.source_field == "response_text"
    assert entry.confidence == 0.95
    assert entry.metadata == {"custom": "info"}
    assert entry.vectorizer_id == "test-vec-1"
    assert entry.vector_dim == 4

    # Vector round-trip check
    v_arr = np.frombuffer(entry.vector_blob, dtype="<f4")
    assert np.allclose(v_arr, vector)


def test_deduplication(tmp_path: Path):
    db_path = tmp_path / "memory.sqlite"
    memory = SemanticMemory(db_path)

    vector = [1.0, 0.0]
    fact_id_1 = memory.write_fact("Deduplicate me", vector, "test-vec")
    fact_id_2 = memory.write_fact("  DEDUPLICATE   me ", vector, "test-vec")

    assert fact_id_1 is not None
    assert fact_id_2 == fact_id_1  # Should return the same ID

    # Double check total count in table is 1
    with memory._get_conn() as conn:
        count = conn.execute("SELECT count(*) FROM semantic_fact").fetchone()[0]
        assert count == 1


def test_lexical_search(tmp_path: Path):
    db_path = tmp_path / "memory.sqlite"
    memory = SemanticMemory(db_path)

    memory.write_fact("The quick brown fox jumps over the lazy dog", [1.0, 0.0], "test-vec")
    memory.write_fact("Sphinx of black quartz, judge my vow", [0.0, 1.0], "test-vec")

    # Positive matches
    res_1 = memory.search_lexical("fox")
    assert len(res_1) == 1
    assert "quick brown fox" in res_1[0].text

    res_2 = memory.search_lexical("quartz")
    assert len(res_2) == 1
    assert "black quartz" in res_2[0].text

    # No matches
    res_empty = memory.search_lexical("nonexistent")
    assert len(res_empty) == 0


def test_vector_search(tmp_path: Path):
    db_path = tmp_path / "memory.sqlite"
    memory = SemanticMemory(db_path)

    # Insert two vectors
    memory.write_fact("Match closely", [1.0, 0.0, 0.0], "test-vec")
    memory.write_fact("Match half-way", [1.0, 1.0, 0.0], "test-vec")

    # Search with query vector [1.0, 0.0, 0.0]
    results = memory.search_vector([1.0, 0.0, 0.0], n=2)
    assert len(results) == 2

    entry_0, sim_0 = results[0]
    entry_1, sim_1 = results[1]

    assert entry_0.text == "Match closely"
    assert pytest.approx(sim_0) == 1.0

    assert entry_1.text == "Match half-way"
    assert pytest.approx(sim_1) == 1.0 / np.sqrt(2)  # ~0.707


def test_fts_fallback_on_syntax_error(tmp_path: Path):
    db_path = tmp_path / "memory.sqlite"
    memory = SemanticMemory(db_path)

    memory.write_fact("Testing special characters like OR AND MATCH", [0.0], "test-vec")

    # In FTS5, "AND" or "OR" without adjacent values is a syntax error.
    # Our search_lexical should gracefully catch it and fall back to LIKE search, returning the match.
    results = memory.search_lexical("AND")
    assert len(results) == 1
    assert "Testing special characters" in results[0].text


def test_malformed_metadata_handling(tmp_path: Path):
    db_path = tmp_path / "memory.sqlite"
    memory = SemanticMemory(db_path)

    # Insert a fact with manual, malformed JSON metadata
    entry_id = "test-malformed-id"
    with memory._get_conn() as conn:
        conn.execute(
            """
            INSERT INTO semantic_fact (
                fact_id, text, created_at, updated_at, vectorizer_id, vector_dim, vector_blob, text_hash, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                "Malformed JSON fact",
                "2026-07-09T00:00:00Z",
                "2026-07-09T00:00:00Z",
                "test-vec",
                1,
                np.array([1.0], dtype="<f4").tobytes(),
                _get_text_hash("Malformed JSON fact"),
                "{invalid json}",
            ),
        )

    entry = memory.read_entry(entry_id)
    assert entry is not None
    assert entry.metadata == {}  # Defaults to empty dict on parse error


def test_fail_closed_error_handling(tmp_path: Path):
    db_path = tmp_path / "memory.sqlite"
    memory = SemanticMemory(db_path)

    # Force connection error by mocking _get_conn
    def mock_get_conn():
        raise sqlite3.OperationalError("Mocked connection failure")
    memory._get_conn = mock_get_conn

    # Verify that calls do not throw exceptions and fail gracefully
    assert memory.write_fact("Fail gracefully", [1.0], "test-vec") is None
    assert memory.read_entry("nonexistent") is None
    assert memory.search_lexical("query") == []
    assert memory.search_vector([1.0]) == []


def test_text_to_vector():
    from backend.app.memory.semantic import text_to_vector

    # 1. Determinism
    v1 = text_to_vector("hello world")
    v2 = text_to_vector("hello world")
    assert np.allclose(v1, v2)
    assert len(v1) == 128

    # 2. Normalization (L2 norm should be 1.0)
    assert pytest.approx(np.linalg.norm(v1)) == 1.0

    # 3. Empty text handling
    v_empty = text_to_vector("   ")
    assert np.allclose(v_empty, 0.0)
    assert len(v_empty) == 128

    # 4. Token sensitivity (different text should yield different vectors)
    v3 = text_to_vector("different text")
    assert not np.allclose(v1, v3)

    # 5. Dimension stability
    v_custom = text_to_vector("hello world", dim=64)
    assert len(v_custom) == 64
    assert pytest.approx(np.linalg.norm(v_custom)) == 1.0


def test_auto_vectorization_on_write(tmp_path: Path):
    db_path = tmp_path / "memory.sqlite"
    memory = SemanticMemory(db_path)

    # Write without vector or vectorizer_id
    fact_id = memory.write_fact("Auto vectorized test fact")
    assert fact_id is not None

    entry = memory.read_entry(fact_id)
    assert entry is not None
    assert entry.vectorizer_id == "local_hashing_trick_v1_128"
    assert entry.vector_dim == 128

    # Retrieve using query string
    from backend.app.memory.semantic import text_to_vector
    q_vec = text_to_vector("Auto vectorized test fact")
    results = memory.search_vector(q_vec, n=1)
    assert len(results) == 1
    assert results[0][0].text == "Auto vectorized test fact"
    assert pytest.approx(results[0][1]) == 1.0
