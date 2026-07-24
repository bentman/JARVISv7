from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
from backend.app.core.paths import DATA_DIR

SEMANTIC_SCHEMA_VERSION = 1
EVIDENCE_AUTHORITIES = (
    "direct_user_statement",
    "direct_user_action",
    "assistant_inference",
    "synthesized_summary",
    "imported_record",
    "legacy_unknown",
)
LIFECYCLE_STATES = (
    "pending_review",
    "active",
    "disputed",
    "superseded",
    "expired",
    "forgotten",
)
CURATION_JOB_STATUSES = ("pending", "processing", "completed", "failed", "cancelled")

_LEGACY_FACT_COLUMNS = (
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
_FTS_SHADOW_TABLES = {
    "semantic_fact_fts_config",
    "semantic_fact_fts_content",
    "semantic_fact_fts_data",
    "semantic_fact_fts_docsize",
    "semantic_fact_fts_idx",
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _get_text_hash(text: str) -> str:
    return hashlib.sha256(_normalize_text(text).encode("utf-8")).hexdigest()


def text_to_vector(text: str, dim: int = 128) -> np.ndarray:
    tokens = _normalize_text(text).split()
    if not tokens:
        return np.zeros(dim, dtype=np.float32)

    vec = np.zeros(dim, dtype=np.float32)
    for token in tokens:
        h = hashlib.md5(token.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], byteorder="big") % dim
        sign = 1 if (h[4] % 2 == 0) else -1
        vec[idx] += sign

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


@dataclass(slots=True)
class SemanticEntry:
    fact_id: str
    text: str
    source_session_id: str | None
    source_turn_id: str | None
    source_field: str | None
    created_at: str
    updated_at: str
    kind: str
    confidence: float | None
    metadata: dict[str, Any]
    vectorizer_id: str
    vector_dim: int
    vector_blob: bytes
    text_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "text": self.text,
            "source_session_id": self.source_session_id,
            "source_turn_id": self.source_turn_id,
            "source_field": self.source_field,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "kind": self.kind,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "vectorizer_id": self.vectorizer_id,
            "vector_dim": self.vector_dim,
            "vector_blob": self.vector_blob,
            "text_hash": self.text_hash,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> SemanticEntry:
        try:
            metadata = json.loads(row["metadata_json"])
        except Exception:
            metadata = {}
        return cls(
            fact_id=row["fact_id"],
            text=row["text"],
            source_session_id=row["source_session_id"],
            source_turn_id=row["source_turn_id"],
            source_field=row["source_field"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            kind=row["kind"],
            confidence=row["confidence"],
            metadata=metadata,
            vectorizer_id=row["vectorizer_id"],
            vector_dim=row["vector_dim"],
            vector_blob=row["vector_blob"],
            text_hash=row["text_hash"],
        )


class SemanticMemory:
    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            db_path = DATA_DIR / "memory" / "semantic" / "memory.sqlite"
        self.db_path = db_path
        self.supports_fts = False
        self._schema_ready = False
        self.schema_error: str | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            conn.close()
            raise sqlite3.OperationalError("SQLite foreign-key enforcement is unavailable")
        return conn

    def _init_db(self) -> None:
        conn: sqlite3.Connection | None = None
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = self._get_conn()
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if version > SEMANTIC_SCHEMA_VERSION:
                raise RuntimeError(
                    f"unsupported semantic schema version {version}; "
                    f"maximum supported is {SEMANTIC_SCHEMA_VERSION}"
                )

            if version == 0:
                database_state = self._classify_version_zero(conn)
                if database_state == "unexpected":
                    raise RuntimeError("unrecognized or partial version-0 semantic schema")
                conn.execute("BEGIN IMMEDIATE")
                try:
                    if database_state == "empty":
                        self._create_latest_schema(conn)
                    else:
                        self._migrate_legacy_to_v1(conn)
                    conn.execute(f"PRAGMA user_version = {SEMANTIC_SCHEMA_VERSION}")
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

            self._validate_latest_schema(conn)
            self.supports_fts = self._table_exists(conn, "semantic_fact_fts")
            self._schema_ready = True
            self.schema_error = None
        except Exception as exc:
            if conn is not None and conn.in_transaction:
                conn.rollback()
            self.supports_fts = False
            self._schema_ready = False
            self.schema_error = str(exc)
        finally:
            if conn is not None:
                conn.close()

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table_name: str) -> tuple[str, ...]:
        return tuple(row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})"))

    def _classify_version_zero(self, conn: sqlite3.Connection) -> str:
        objects = conn.execute(
            """
            SELECT type, name, sql
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()
        if not objects:
            return "empty"

        object_names = {row["name"] for row in objects}
        allowed_names = {
            "semantic_fact",
            "semantic_fact_fts",
            "idx_semantic_fact_hash",
            *_FTS_SHADOW_TABLES,
        }
        if "semantic_fact" not in object_names or not object_names <= allowed_names:
            return "unexpected"
        if self._table_columns(conn, "semantic_fact") != _LEGACY_FACT_COLUMNS:
            return "unexpected"

        index_rows = conn.execute("PRAGMA index_list(semantic_fact)").fetchall()
        hash_indexes = [row for row in index_rows if row["name"] == "idx_semantic_fact_hash"]
        if len(hash_indexes) != 1 or int(hash_indexes[0]["unique"]) != 1:
            return "unexpected"
        index_columns = tuple(
            row["name"] for row in conn.execute("PRAGMA index_info(idx_semantic_fact_hash)")
        )
        if index_columns != ("text_hash",):
            return "unexpected"

        has_fts = "semantic_fact_fts" in object_names
        present_fts_shadows = object_names & _FTS_SHADOW_TABLES
        if (has_fts and present_fts_shadows != _FTS_SHADOW_TABLES) or (
            not has_fts and present_fts_shadows
        ):
            return "unexpected"
        if has_fts:
            fts_row = conn.execute(
                "SELECT sql FROM sqlite_schema WHERE name = 'semantic_fact_fts'"
            ).fetchone()
            fts_sql = str(fts_row["sql"] or "").lower().replace(" ", "")
            if "usingfts5(text,tokenize='unicode61')" not in fts_sql or "content=" in fts_sql:
                return "unexpected"
            if self._table_columns(conn, "semantic_fact_fts") != ("text",):
                return "unexpected"
        return "legacy"

    def _create_latest_schema(self, conn: sqlite3.Connection) -> None:
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
                text_hash TEXT NOT NULL,
                claim_key TEXT,
                value_text TEXT,
                evidence_authority TEXT NOT NULL DEFAULT 'legacy_unknown'
                    CHECK (evidence_authority IN (
                        'direct_user_statement', 'direct_user_action',
                        'assistant_inference', 'synthesized_summary',
                        'imported_record', 'legacy_unknown'
                    )),
                state TEXT NOT NULL DEFAULT 'active'
                    CHECK (state IN (
                        'pending_review', 'active', 'disputed',
                        'superseded', 'expired', 'forgotten'
                    )),
                importance REAL CHECK (importance IS NULL OR importance BETWEEN 0.0 AND 1.0),
                reinforcement_count INTEGER NOT NULL DEFAULT 1
                    CHECK (reinforcement_count >= 1),
                last_confirmed_at TEXT,
                expires_at TEXT,
                superseded_by_fact_id TEXT REFERENCES semantic_fact(fact_id)
                    ON DELETE SET NULL,
                revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1)
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX idx_semantic_fact_hash ON semantic_fact(text_hash)"
        )
        self._create_governance_schema(conn)
        self._create_fts_if_available(conn, backfill=False)

    def _migrate_legacy_to_v1(self, conn: sqlite3.Connection) -> None:
        additions = (
            "claim_key TEXT",
            "value_text TEXT",
            "evidence_authority TEXT NOT NULL DEFAULT 'legacy_unknown' "
            "CHECK (evidence_authority IN "
            "('direct_user_statement', 'direct_user_action', 'assistant_inference', "
            "'synthesized_summary', 'imported_record', 'legacy_unknown'))",
            "state TEXT NOT NULL DEFAULT 'active' "
            "CHECK (state IN "
            "('pending_review', 'active', 'disputed', 'superseded', 'expired', 'forgotten'))",
            "importance REAL CHECK (importance IS NULL OR importance BETWEEN 0.0 AND 1.0)",
            "reinforcement_count INTEGER NOT NULL DEFAULT 1 CHECK (reinforcement_count >= 1)",
            "last_confirmed_at TEXT",
            "expires_at TEXT",
            "superseded_by_fact_id TEXT REFERENCES semantic_fact(fact_id) ON DELETE SET NULL",
            "revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1)",
        )
        for definition in additions:
            conn.execute(f"ALTER TABLE semantic_fact ADD COLUMN {definition}")

        self._create_governance_schema(conn)
        conn.execute(
            """
            INSERT INTO semantic_evidence (
                evidence_id, fact_id,
                source_session_id, source_turn_id, source_field,
                action_id, action_surface, action_reason,
                evidence_authority, observed_at, created_at, metadata_json
            )
            SELECT
                'legacy:' || fact_id, fact_id,
                source_session_id, source_turn_id, source_field,
                NULL, NULL, NULL,
                'legacy_unknown', created_at, created_at, '{}'
            FROM semantic_fact
            WHERE source_session_id IS NOT NULL
              AND source_turn_id IS NOT NULL
              AND source_field IS NOT NULL
            ORDER BY rowid
            ON CONFLICT(evidence_id) DO NOTHING
            """
        )
        self._create_fts_if_available(
            conn,
            backfill=not self._table_exists(conn, "semantic_fact_fts"),
        )

    def _create_governance_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE semantic_evidence (
                evidence_id TEXT PRIMARY KEY CHECK (length(evidence_id) > 0),
                fact_id TEXT NOT NULL REFERENCES semantic_fact(fact_id) ON DELETE CASCADE,
                source_session_id TEXT,
                source_turn_id TEXT,
                source_field TEXT,
                action_id TEXT,
                action_surface TEXT,
                action_reason TEXT,
                evidence_authority TEXT NOT NULL CHECK (evidence_authority IN (
                    'direct_user_statement', 'direct_user_action',
                    'assistant_inference', 'synthesized_summary',
                    'imported_record', 'legacy_unknown'
                )),
                observed_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
                    CHECK (length(metadata_json) <= 16384),
                CHECK (
                    (
                        source_session_id IS NOT NULL
                        AND source_turn_id IS NOT NULL
                        AND source_field IS NOT NULL
                        AND action_id IS NULL
                        AND action_surface IS NULL
                        AND action_reason IS NULL
                        AND evidence_authority <> 'direct_user_action'
                    )
                    OR
                    (
                        source_session_id IS NULL
                        AND source_turn_id IS NULL
                        AND source_field IS NULL
                        AND action_id IS NOT NULL
                        AND action_surface IS NOT NULL
                        AND action_reason IS NOT NULL
                        AND evidence_authority = 'direct_user_action'
                    )
                )
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX idx_semantic_evidence_turn_origin
            ON semantic_evidence(fact_id, source_session_id, source_turn_id, source_field)
            WHERE action_id IS NULL
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX idx_semantic_evidence_action_origin
            ON semantic_evidence(fact_id, action_id)
            WHERE action_id IS NOT NULL
            """
        )
        conn.execute(
            """
            CREATE TABLE semantic_event (
                event_id TEXT PRIMARY KEY CHECK (length(event_id) > 0),
                fact_id TEXT NOT NULL REFERENCES semantic_fact(fact_id) ON DELETE CASCADE,
                event_type TEXT NOT NULL CHECK (length(event_type) > 0),
                prior_state TEXT CHECK (prior_state IS NULL OR prior_state IN (
                    'pending_review', 'active', 'disputed',
                    'superseded', 'expired', 'forgotten'
                )),
                resulting_state TEXT CHECK (resulting_state IS NULL OR resulting_state IN (
                    'pending_review', 'active', 'disputed',
                    'superseded', 'expired', 'forgotten'
                )),
                related_fact_id TEXT REFERENCES semantic_fact(fact_id) ON DELETE SET NULL,
                reason_code TEXT NOT NULL CHECK (length(reason_code) > 0),
                occurred_at TEXT NOT NULL,
                source_session_id TEXT,
                source_turn_id TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
                    CHECK (length(metadata_json) <= 16384),
                CHECK (
                    (source_session_id IS NULL AND source_turn_id IS NULL)
                    OR
                    (source_session_id IS NOT NULL AND source_turn_id IS NOT NULL)
                )
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE semantic_curation_job (
                session_id TEXT PRIMARY KEY CHECK (length(session_id) > 0),
                artifact_ref TEXT NOT NULL CHECK (length(artifact_ref) > 0),
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending', 'processing', 'completed', 'failed', 'cancelled'
                    )),
                attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                created_at TEXT NOT NULL,
                started_at TEXT,
                updated_at TEXT NOT NULL,
                last_attempt_at TEXT,
                last_error TEXT,
                last_reason TEXT,
                lease_token TEXT,
                lease_owner TEXT,
                lease_expires_at TEXT,
                CHECK (
                    (lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL)
                    OR
                    (lease_token IS NOT NULL AND lease_owner IS NOT NULL
                     AND lease_expires_at IS NOT NULL)
                )
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE semantic_policy (
                singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                automatic_curation_enabled INTEGER NOT NULL DEFAULT 0
                    CHECK (automatic_curation_enabled IN (0, 1)),
                revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE semantic_meta (
                singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                content_revision INTEGER NOT NULL DEFAULT 0 CHECK (content_revision >= 0)
            )
            """
        )
        initialized_at = _iso_now()
        conn.execute(
            """
            INSERT INTO semantic_policy (
                singleton_id, automatic_curation_enabled, revision, updated_at
            ) VALUES (1, 0, 1, ?)
            """,
            (initialized_at,),
        )
        conn.execute(
            "INSERT INTO semantic_meta (singleton_id, content_revision) VALUES (1, 0)"
        )
        conn.execute(
            """
            CREATE TRIGGER semantic_policy_revision_monotonic
            BEFORE UPDATE OF revision ON semantic_policy
            WHEN NEW.revision < OLD.revision
            BEGIN
                SELECT RAISE(ABORT, 'semantic_policy revision cannot decrease');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER semantic_meta_revision_monotonic
            BEFORE UPDATE OF content_revision ON semantic_meta
            WHEN NEW.content_revision < OLD.content_revision
            BEGIN
                SELECT RAISE(ABORT, 'semantic_meta content_revision cannot decrease');
            END
            """
        )
        for table_name, identity_column in (
            ("semantic_evidence", "evidence_id"),
            ("semantic_event", "event_id"),
        ):
            conn.execute(
                f"""
                CREATE TRIGGER {table_name}_immutable_update
                BEFORE UPDATE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, '{table_name} rows are immutable');
                END
                """
            )
            conn.execute(
                f"""
                CREATE TRIGGER {table_name}_immutable_delete
                BEFORE DELETE ON {table_name}
                BEGIN
                    SELECT CASE
                        WHEN OLD.{identity_column} IS NOT NULL
                        THEN RAISE(ABORT, '{table_name} rows are immutable')
                    END;
                END
                """
            )

    def _create_fts_if_available(
        self,
        conn: sqlite3.Connection,
        *,
        backfill: bool,
    ) -> bool:
        if self._table_exists(conn, "semantic_fact_fts"):
            return True
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
        if backfill:
            conn.execute(
                """
                INSERT INTO semantic_fact_fts(rowid, text)
                SELECT rowid, text FROM semantic_fact ORDER BY rowid
                """
            )
        return True

    def _validate_latest_schema(self, conn: sqlite3.Connection) -> None:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version != SEMANTIC_SCHEMA_VERSION:
            raise RuntimeError(f"incomplete semantic schema migration at version {version}")
        required_tables = {
            "semantic_fact",
            "semantic_evidence",
            "semantic_event",
            "semantic_curation_job",
            "semantic_policy",
            "semantic_meta",
        }
        actual_tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        if not required_tables <= actual_tables:
            raise RuntimeError("versioned semantic schema is missing required tables")
        expected_fact_columns = (
            *_LEGACY_FACT_COLUMNS,
            "claim_key",
            "value_text",
            "evidence_authority",
            "state",
            "importance",
            "reinforcement_count",
            "last_confirmed_at",
            "expires_at",
            "superseded_by_fact_id",
            "revision",
        )
        if self._table_columns(conn, "semantic_fact") != expected_fact_columns:
            raise RuntimeError("versioned semantic_fact layout is not recognized")
        for table_name in ("semantic_policy", "semantic_meta"):
            singleton_ids = [
                row["singleton_id"]
                for row in conn.execute(
                    f"SELECT singleton_id FROM {table_name} ORDER BY singleton_id"
                )
            ]
            if singleton_ids != [1]:
                raise RuntimeError(f"{table_name} singleton authority is missing or ambiguous")

    def write_entry(self, entry: SemanticEntry) -> str | None:
        """Writes a fully constructed SemanticEntry to the store, performing deduplication on text_hash."""
        if not self._schema_ready:
            return None
        try:
            with self._get_conn() as conn:
                metadata_json = json.dumps(entry.metadata)
                # Deduplication rides on the unique text_hash index so a concurrent
                # same-text writer cannot slip between a check and the insert.
                cursor = conn.execute(
                    """
                    INSERT INTO semantic_fact (
                        fact_id, text, source_session_id, source_turn_id, source_field,
                        created_at, updated_at, kind, confidence, metadata_json,
                        vectorizer_id, vector_dim, vector_blob, text_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(text_hash) DO NOTHING
                    """,
                    (
                        entry.fact_id,
                        entry.text,
                        entry.source_session_id,
                        entry.source_turn_id,
                        entry.source_field,
                        entry.created_at,
                        entry.updated_at,
                        entry.kind,
                        entry.confidence,
                        metadata_json,
                        entry.vectorizer_id,
                        entry.vector_dim,
                        entry.vector_blob,
                        entry.text_hash,
                    ),
                )
                if cursor.rowcount == 0:
                    existing = conn.execute(
                        "SELECT fact_id FROM semantic_fact WHERE text_hash = ?", (entry.text_hash,)
                    ).fetchone()
                    if existing is None:
                        return None
                    return cast(str, existing["fact_id"])

                rowid = cursor.lastrowid
                if self.supports_fts and rowid is not None:
                    # A failed FTS insert must abort the enclosing transaction so the
                    # fact row and its FTS row commit together or not at all.
                    conn.execute(
                        "INSERT INTO semantic_fact_fts (rowid, text) VALUES (?, ?)",
                        (rowid, entry.text),
                    )
                return entry.fact_id
        except Exception:
            return None

    def write_fact(
        self,
        text: str,
        vector: np.ndarray | list[float] | None = None,
        vectorizer_id: str | None = None,
        source_session_id: str | None = None,
        source_turn_id: str | None = None,
        source_field: str | None = None,
        kind: str = "fact",
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Constructs and writes a SemanticEntry from components. Returns fact_id or None on error."""
        if not self._schema_ready:
            return None
        try:
            if vectorizer_id is None:
                vectorizer_id = "local_hashing_trick_v1_128"
            if vector is None:
                vector = text_to_vector(text, dim=128)

            text_hash = _get_text_hash(text)
            vec_arr = np.array(vector, dtype="<f4")
            vector_blob = vec_arr.tobytes()
            vector_dim = len(vec_arr)

            entry = SemanticEntry(
                fact_id=uuid.uuid4().hex,
                text=text,
                source_session_id=source_session_id,
                source_turn_id=source_turn_id,
                source_field=source_field,
                created_at=_iso_now(),
                updated_at=_iso_now(),
                kind=kind,
                confidence=confidence,
                metadata=metadata or {},
                vectorizer_id=vectorizer_id,
                vector_dim=vector_dim,
                vector_blob=vector_blob,
                text_hash=text_hash,
            )
            return self.write_entry(entry)
        except Exception:
            return None

    def read_entry(self, fact_id: str) -> SemanticEntry | None:
        """Reads a single entry by fact_id."""
        if not self._schema_ready:
            return None
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM semantic_fact WHERE fact_id = ?", (fact_id,)
                ).fetchone()
                if row is not None:
                    return SemanticEntry.from_row(row)
            return None
        except Exception:
            return None

    def search_lexical(self, query: str, n: int = 5) -> list[SemanticEntry]:
        """Performs lexical query match using FTS5 (or falling back to LIKE if FTS5 fails or is disabled)."""
        if not self._schema_ready:
            return []
        try:
            results: list[SemanticEntry] = []
            if not query.strip():
                return []

            with self._get_conn() as conn:
                if self.supports_fts:
                    try:
                        rows = conn.execute(
                            """
                            SELECT f.* FROM semantic_fact f
                            JOIN semantic_fact_fts fts ON f.rowid = fts.rowid
                            WHERE fts.text MATCH ?
                            LIMIT ?
                            """,
                            (query, n),
                        ).fetchall()
                        for row in rows:
                            results.append(SemanticEntry.from_row(row))
                        return results
                    except sqlite3.OperationalError:
                        # If FTS syntax is invalid or search failed, fallback to LIKE
                        pass

                # Fallback to standard LIKE
                like_pattern = f"%{query}%"
                rows = conn.execute(
                    """
                    SELECT * FROM semantic_fact
                    WHERE text LIKE ?
                    LIMIT ?
                    """,
                    (like_pattern, n),
                ).fetchall()
                for row in rows:
                    results.append(SemanticEntry.from_row(row))
                return results
        except Exception:
            return []

    def search_vector(
        self, query_vector: np.ndarray | list[float], n: int = 5
    ) -> list[tuple[SemanticEntry, float]]:
        """Computes cosine similarity of query_vector against all stored vectors and returns top-n matches."""
        if not self._schema_ready:
            return []
        try:
            q_arr = np.array(query_vector, dtype="<f4")
            q_norm = np.linalg.norm(q_arr)
            if q_norm == 0:
                return []

            candidates: list[tuple[SemanticEntry, float]] = []
            with self._get_conn() as conn:
                rows = conn.execute("SELECT * FROM semantic_fact").fetchall()
                for row in rows:
                    entry = SemanticEntry.from_row(row)
                    try:
                        v_arr = np.frombuffer(entry.vector_blob, dtype="<f4")
                        if len(v_arr) != entry.vector_dim:
                            continue
                        v_norm = np.linalg.norm(v_arr)
                        if v_norm == 0:
                            sim = 0.0
                        else:
                            sim = float(np.dot(q_arr, v_arr) / (q_norm * v_norm))
                        candidates.append((entry, sim))
                    except Exception:
                        continue

            candidates.sort(key=lambda item: item[1], reverse=True)
            return candidates[:n]
        except Exception:
            return []
