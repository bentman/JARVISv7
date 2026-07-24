from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest
from backend.app.memory.semantic import (
    SEMANTIC_SCHEMA_VERSION,
    SemanticMemory,
    _get_text_hash,
    text_to_vector,
)


def _create_legacy_database(db_path: Path, *, with_fts: bool = True) -> bool:
    vector_blob = np.array([0.25, 0.75], dtype="<f4").tobytes()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE semantic_fact (
                fact_id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                source_session_id TEXT,
                source_turn_id TEXT,
                source_field TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'fact',
                confidence REAL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                vectorizer_id TEXT NOT NULL,
                vector_dim INTEGER NOT NULL,
                vector_blob BLOB NOT NULL,
                text_hash TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX idx_semantic_fact_hash ON semantic_fact(text_hash)"
        )
        cursor = conn.execute(
            """
            INSERT INTO semantic_fact (
                fact_id, text, source_session_id, source_turn_id, source_field,
                created_at, updated_at, kind, confidence, metadata_json,
                vectorizer_id, vector_dim, vector_blob, text_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-fact-id",
                "Legacy reactor fact",
                "legacy-session",
                "legacy-turn",
                "response_text",
                "2026-07-01T00:00:00+00:00",
                "2026-07-02T00:00:00+00:00",
                "fact",
                0.8,
                '{"legacy":true}',
                "legacy-vectorizer",
                2,
                vector_blob,
                _get_text_hash("Legacy reactor fact"),
            ),
        )
        if not with_fts:
            return False
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE semantic_fact_fts
                USING fts5(text, tokenize='unicode61')
                """
            )
        except sqlite3.OperationalError as exc:
            if "no such module: fts5" not in str(exc).lower():
                raise
            return False
        conn.execute(
            "INSERT INTO semantic_fact_fts(rowid, text) VALUES (?, ?)",
            (cursor.lastrowid, "Legacy reactor fact"),
        )
    return True


def test_init_db(tmp_path: Path):
    db_path = tmp_path / "subdir" / "memory.sqlite"
    memory = SemanticMemory(db_path)
    assert db_path.exists()

    # Verify tables
    with memory._get_conn() as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {row["name"] for row in tables}
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


def test_write_entry_rolls_back_fact_when_fts_insert_fails(tmp_path: Path):
    db_path = tmp_path / "memory.sqlite"
    memory = SemanticMemory(db_path)
    if not memory.supports_fts:
        pytest.skip("FTS5 unavailable on this host")

    # Break the FTS table after init so the FTS insert fails while the fact insert succeeds.
    with memory._get_conn() as conn:
        conn.execute("DROP TABLE semantic_fact_fts")

    fact_id = memory.write_fact(text="fact that must not commit half-indexed")
    assert fact_id is None

    with memory._get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM semantic_fact").fetchone()["c"]
    assert count == 0


def test_written_fact_is_visible_to_fts_lexical_search(tmp_path: Path):
    db_path = tmp_path / "memory.sqlite"
    memory = SemanticMemory(db_path)
    if not memory.supports_fts:
        pytest.skip("FTS5 unavailable on this host")

    fact_id = memory.write_fact(text="the reactor core is stable")
    assert fact_id is not None

    results = memory.search_lexical("reactor")
    assert [entry.fact_id for entry in results] == [fact_id]


def test_write_entry_returns_existing_fact_id_when_hash_row_already_present(tmp_path: Path):
    """A row inserted by another writer between any check and the insert must dedup, not fail."""
    db_path = tmp_path / "memory.sqlite"
    memory = SemanticMemory(db_path)

    first_id = memory.write_fact(text="the same fact")
    assert first_id is not None

    second_id = memory.write_fact(text="THE   same fact  ")  # normalizes to identical hash
    assert second_id == first_id

    with memory._get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM semantic_fact").fetchone()["c"]
    assert count == 1


def test_concurrent_same_text_writes_yield_one_row_and_one_fact_id(tmp_path: Path):
    import threading

    db_path = tmp_path / "memory.sqlite"
    memory = SemanticMemory(db_path)

    results: list[str | None] = [None] * 8
    barrier = threading.Barrier(8)

    def _write(slot: int) -> None:
        barrier.wait()
        results[slot] = memory.write_fact(text="racy duplicate fact")

    threads = [threading.Thread(target=_write, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r is not None for r in results)
    assert len(set(results)) == 1

    with memory._get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM semantic_fact").fetchone()["c"]
    assert count == 1


def test_new_database_creates_latest_governed_schema(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "new" / "memory.sqlite")

    assert memory._schema_ready is True
    with memory._get_conn() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SEMANTIC_SCHEMA_VERSION
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        assert {
            "semantic_fact",
            "semantic_evidence",
            "semantic_event",
            "semantic_curation_job",
            "semantic_policy",
            "semantic_meta",
        } <= tables
        policy = conn.execute("SELECT * FROM semantic_policy").fetchone()
        meta = conn.execute("SELECT * FROM semantic_meta").fetchone()
        assert dict(policy) == {
            "singleton_id": 1,
            "automatic_curation_enabled": 0,
            "revision": 1,
            "updated_at": policy["updated_at"],
        }
        assert dict(meta) == {"singleton_id": 1, "content_revision": 0}
        assert conn.execute("SELECT COUNT(*) FROM semantic_fact").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM semantic_evidence").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM semantic_event").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM semantic_curation_job").fetchone()[0] == 0


def test_recognized_legacy_database_migrates_and_preserves_fact_data(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    _create_legacy_database(db_path, with_fts=False)
    before_bytes = np.array([0.25, 0.75], dtype="<f4").tobytes()
    before_hash = _get_text_hash("Legacy reactor fact")

    memory = SemanticMemory(db_path)

    assert memory._schema_ready is True
    with memory._get_conn() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SEMANTIC_SCHEMA_VERSION
        row = conn.execute(
            "SELECT rowid, * FROM semantic_fact WHERE fact_id = 'legacy-fact-id'"
        ).fetchone()
        assert row["rowid"] == 1
        assert row["text"] == "Legacy reactor fact"
        assert row["vector_blob"] == before_bytes
        assert row["text_hash"] == before_hash
        assert row["metadata_json"] == '{"legacy":true}'
        assert row["source_session_id"] == "legacy-session"
        assert row["source_turn_id"] == "legacy-turn"
        assert row["source_field"] == "response_text"
        assert row["claim_key"] is None
        assert row["evidence_authority"] == "legacy_unknown"
        assert row["state"] == "active"
        assert row["reinforcement_count"] == 1
        assert row["revision"] == 1
        evidence = conn.execute("SELECT * FROM semantic_evidence").fetchall()
        assert len(evidence) == 1
        assert evidence[0]["evidence_id"] == "legacy:legacy-fact-id"
        assert evidence[0]["fact_id"] == "legacy-fact-id"
        assert evidence[0]["source_turn_id"] == "legacy-turn"


def test_repeat_initialization_after_migration_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    _create_legacy_database(db_path, with_fts=False)

    first = SemanticMemory(db_path)
    with first._get_conn() as conn:
        policy_before = tuple(conn.execute("SELECT * FROM semantic_policy").fetchone())

    second = SemanticMemory(db_path)

    assert second._schema_ready is True
    with second._get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM semantic_fact").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM semantic_evidence").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM semantic_event").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM semantic_curation_job").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM semantic_policy").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM semantic_meta").fetchone()[0] == 1
        assert tuple(conn.execute("SELECT * FROM semantic_policy").fetchone()) == policy_before


def test_unknown_future_user_version_fails_closed_without_mutation(tmp_path: Path) -> None:
    db_path = tmp_path / "future.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA user_version = 99")

    memory = SemanticMemory(db_path)

    assert memory._schema_ready is False
    assert memory.schema_error is not None
    assert "unsupported semantic schema version 99" in memory.schema_error
    assert memory.write_fact("must not write") is None
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 99
        assert conn.execute("SELECT COUNT(*) FROM sqlite_schema").fetchone()[0] == 0


def test_partial_version_zero_schema_fails_closed_without_repair(tmp_path: Path) -> None:
    db_path = tmp_path / "partial.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE semantic_fact (fact_id TEXT PRIMARY KEY, text TEXT)")

    memory = SemanticMemory(db_path)

    assert memory._schema_ready is False
    assert memory.schema_error == "unrecognized or partial version-0 semantic schema"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        assert tables == {"semantic_fact"}
        assert tuple(
            row[1] for row in conn.execute("PRAGMA table_info(semantic_fact)")
        ) == ("fact_id", "text")


def test_migration_failure_rolls_back_entire_step(tmp_path: Path) -> None:
    db_path = tmp_path / "rollback.sqlite"
    _create_legacy_database(db_path, with_fts=False)

    class FailingSemanticMemory(SemanticMemory):
        def _migrate_legacy_to_v1(self, conn: sqlite3.Connection) -> None:
            conn.execute("ALTER TABLE semantic_fact ADD COLUMN claim_key TEXT")
            conn.execute("CREATE TABLE migration_must_rollback (value TEXT)")
            raise RuntimeError("injected migration failure")

    memory = FailingSemanticMemory(db_path)

    assert memory._schema_ready is False
    assert memory.schema_error == "injected migration failure"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        assert "migration_must_rollback" not in tables
        assert tuple(
            row[1] for row in conn.execute("PRAGMA table_info(semantic_fact)")
        ) == (
            "fact_id",
            "text",
            "source_session_id",
            "source_turn_id",
            "source_field",
            "created_at",
            "updated_at",
            "kind",
            "confidence",
            "metadata_json",
            "vectorizer_id",
            "vector_dim",
            "vector_blob",
            "text_hash",
        )
        assert conn.execute("SELECT COUNT(*) FROM semantic_fact").fetchone()[0] == 1


def test_content_storing_fts_rowid_and_text_survive_legacy_migration(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-fts.sqlite"
    if not _create_legacy_database(db_path, with_fts=True):
        pytest.skip("FTS5 unavailable on this host")
    with sqlite3.connect(db_path) as conn:
        before = conn.execute(
            "SELECT rowid, text FROM semantic_fact_fts ORDER BY rowid"
        ).fetchall()

    memory = SemanticMemory(db_path)

    assert memory._schema_ready is True
    assert memory.supports_fts is True
    with memory._get_conn() as conn:
        after = conn.execute(
            "SELECT rowid, text FROM semantic_fact_fts ORDER BY rowid"
        ).fetchall()
        fts_sql = conn.execute(
            "SELECT sql FROM sqlite_schema WHERE name = 'semantic_fact_fts'"
        ).fetchone()["sql"]
        assert [tuple(row) for row in after] == before
        assert "content=" not in fts_sql.lower().replace(" ", "")
        joined = conn.execute(
            """
            SELECT f.fact_id, fts.text
            FROM semantic_fact AS f
            JOIN semantic_fact_fts AS fts ON f.rowid = fts.rowid
            """
        ).fetchone()
        assert tuple(joined) == ("legacy-fact-id", "Legacy reactor fact")
    assert [entry.fact_id for entry in memory.search_lexical("reactor")] == [
        "legacy-fact-id"
    ]


def test_schema_and_like_search_work_when_fts5_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        SemanticMemory,
        "_create_fts_if_available",
        lambda self, conn, *, backfill: False,
    )

    memory = SemanticMemory(tmp_path / "no-fts.sqlite")

    assert memory._schema_ready is True
    assert memory.supports_fts is False
    fact_id = memory.write_fact("fallback-only semantic record")
    assert fact_id is not None
    assert [entry.fact_id for entry in memory.search_lexical("fallback-only")] == [
        fact_id
    ]


def test_foreign_keys_are_enabled_and_enforced_on_every_connection(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "foreign-keys.sqlite")

    with memory._get_conn() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO semantic_evidence (
                    evidence_id, fact_id,
                    source_session_id, source_turn_id, source_field,
                    evidence_authority, observed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "orphan-evidence",
                    "missing-fact",
                    "session",
                    "turn",
                    "response_text",
                    "legacy_unknown",
                    "2026-07-01T00:00:00+00:00",
                    "2026-07-01T00:00:00+00:00",
                ),
            )


def test_policy_and_meta_singletons_are_structurally_enforced(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "singletons.sqlite")

    with memory._get_conn() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO semantic_policy (
                    singleton_id, automatic_curation_enabled, revision, updated_at
                ) VALUES (2, 0, 1, '2026-07-01T00:00:00+00:00')
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO semantic_meta (singleton_id, content_revision) VALUES (2, 0)"
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO semantic_policy (
                    singleton_id, automatic_curation_enabled, revision, updated_at
                ) VALUES (1, 0, 1, '2026-07-01T00:00:00+00:00')
                """
            )


def test_evidence_origin_uniqueness_and_immutability_constraints(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "evidence.sqlite")
    fact_id = memory.write_fact("Evidence constraint fact")
    assert fact_id is not None

    with memory._get_conn() as conn:
        turn_values = (
            "turn-evidence",
            fact_id,
            "session-1",
            "turn-1",
            "response_text",
            "direct_user_statement",
            "2026-07-01T00:00:00+00:00",
            "2026-07-01T00:00:00+00:00",
        )
        conn.execute(
            """
            INSERT INTO semantic_evidence (
                evidence_id, fact_id,
                source_session_id, source_turn_id, source_field,
                evidence_authority, observed_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            turn_values,
        )
        conn.execute(
            """
            INSERT INTO semantic_evidence (
                evidence_id, fact_id,
                action_id, action_surface, action_reason,
                evidence_authority, observed_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "action-evidence",
                fact_id,
                "action-1",
                "api",
                "explicit_correction",
                "direct_user_action",
                "2026-07-02T00:00:00+00:00",
                "2026-07-02T00:00:00+00:00",
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO semantic_evidence (
                    evidence_id, fact_id,
                    source_session_id, source_turn_id, source_field,
                    evidence_authority, observed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("duplicate-turn", *turn_values[1:]),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO semantic_evidence (
                    evidence_id, fact_id,
                    source_session_id, source_turn_id, source_field,
                    action_id, action_surface, action_reason,
                    evidence_authority, observed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "mixed-origin",
                    fact_id,
                    "fake-session",
                    "fake-turn",
                    "response_text",
                    "action-2",
                    "desktop",
                    "correction",
                    "direct_user_action",
                    "2026-07-02T00:00:00+00:00",
                    "2026-07-02T00:00:00+00:00",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                """
                UPDATE semantic_evidence
                SET metadata_json = '{"changed":true}'
                WHERE evidence_id = 'turn-evidence'
                """
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "DELETE FROM semantic_evidence WHERE evidence_id = 'turn-evidence'"
            )
        assert conn.execute("SELECT COUNT(*) FROM semantic_evidence").fetchone()[0] == 2


def test_event_job_fact_revision_and_policy_constraints(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "constraints.sqlite")
    first_id = memory.write_fact("First unconstrained claim identity")
    second_id = memory.write_fact("Second unconstrained claim identity")
    assert first_id is not None
    assert second_id is not None

    with memory._get_conn() as conn:
        conn.execute(
            """
            UPDATE semantic_fact
            SET claim_key = 'untrusted:model-proposal'
            WHERE fact_id IN (?, ?)
            """,
            (first_id, second_id),
        )
        assert (
            conn.execute(
                """
                SELECT COUNT(*) FROM semantic_fact
                WHERE claim_key = 'untrusted:model-proposal'
                """
            ).fetchone()[0]
            == 2
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE semantic_fact SET state = 'unknown' WHERE fact_id = ?",
                (first_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE semantic_fact SET revision = 0 WHERE fact_id = ?",
                (first_id,),
            )

        event_values = (
            "event-1",
            first_id,
            "observed",
            None,
            "active",
            second_id,
            "schema-test",
            "2026-07-01T00:00:00+00:00",
        )
        conn.execute(
            """
            INSERT INTO semantic_event (
                event_id, fact_id, event_type, prior_state, resulting_state,
                related_fact_id, reason_code, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            event_values,
        )
        conn.execute(
            """
            INSERT INTO semantic_event (
                event_id, fact_id, event_type, reason_code, occurred_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "event-2",
                first_id,
                "reinforced",
                "schema-test",
                "2026-07-02T00:00:00+00:00",
            ),
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE semantic_event SET reason_code = 'changed' WHERE event_id = 'event-1'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("DELETE FROM semantic_event WHERE event_id = 'event-1'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO semantic_event (
                    event_id, fact_id, event_type, resulting_state,
                    reason_code, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "bad-event",
                    first_id,
                    "observed",
                    "unknown",
                    "schema-test",
                    "2026-07-02T00:00:00+00:00",
                ),
            )

        conn.execute(
            """
            INSERT INTO semantic_curation_job (
                session_id, artifact_ref, status, attempt_count,
                created_at, updated_at,
                lease_token, lease_owner, lease_expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "session-1",
                "sessions/session-1/session.json",
                "processing",
                1,
                "2026-07-01T00:00:00+00:00",
                "2026-07-01T00:01:00+00:00",
                "lease-1",
                "worker-1",
                "2026-07-01T00:05:00+00:00",
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO semantic_curation_job (
                    session_id, artifact_ref, status, attempt_count,
                    created_at, updated_at
                ) VALUES ('bad-status', 'artifact', 'unknown', 0, 'now', 'now')
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO semantic_curation_job (
                    session_id, artifact_ref, status, attempt_count,
                    created_at, updated_at
                ) VALUES ('bad-attempt', 'artifact', 'pending', -1, 'now', 'now')
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO semantic_curation_job (
                    session_id, artifact_ref, status, attempt_count,
                    created_at, updated_at, lease_token
                ) VALUES ('bad-lease', 'artifact', 'processing', 1, 'now', 'now', 'lease')
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE semantic_policy SET automatic_curation_enabled = 2"
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE semantic_policy SET revision = 0")
        conn.execute("UPDATE semantic_policy SET revision = 3")
        with pytest.raises(sqlite3.IntegrityError, match="cannot decrease"):
            conn.execute("UPDATE semantic_policy SET revision = 2")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE semantic_meta SET content_revision = -1")
        conn.execute("UPDATE semantic_meta SET content_revision = 3")
        with pytest.raises(sqlite3.IntegrityError, match="cannot decrease"):
            conn.execute("UPDATE semantic_meta SET content_revision = 2")
        assert conn.execute("SELECT COUNT(*) FROM semantic_event").fetchone()[0] == 2


def test_initialization_and_reads_do_not_change_content_or_behavior(tmp_path: Path) -> None:
    db_path = tmp_path / "behavior.sqlite"
    memory = SemanticMemory(db_path)
    fact_id = memory.write_fact("Normal retrieval behavior remains available")
    assert fact_id is not None

    with memory._get_conn() as conn:
        revision_before = conn.execute(
            "SELECT content_revision FROM semantic_meta WHERE singleton_id = 1"
        ).fetchone()[0]
        fact_count_before = conn.execute("SELECT COUNT(*) FROM semantic_fact").fetchone()[0]

    assert memory.read_entry(fact_id) is not None
    assert [entry.fact_id for entry in memory.search_lexical("retrieval")] == [fact_id]
    assert memory.search_vector(text_to_vector("Normal retrieval behavior remains available"))
    reopened = SemanticMemory(db_path)

    with reopened._get_conn() as conn:
        assert (
            conn.execute(
                "SELECT content_revision FROM semantic_meta WHERE singleton_id = 1"
            ).fetchone()[0]
            == revision_before
        )
        assert conn.execute("SELECT COUNT(*) FROM semantic_fact").fetchone()[0] == fact_count_before
        assert conn.execute("SELECT COUNT(*) FROM semantic_evidence").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM semantic_event").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM semantic_curation_job").fetchone()[0] == 0
