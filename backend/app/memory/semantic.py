from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
from backend.app.core.paths import DATA_DIR

_LOGGER = logging.getLogger(__name__)


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
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._get_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS semantic_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS semantic_fact (
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
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_semantic_fact_hash ON semantic_fact(text_hash)"
                )

                # Check FTS5 support and initialize virtual table
                try:
                    conn.execute(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS semantic_fact_fts USING fts5(text, tokenize='unicode61')"
                    )
                    self.supports_fts = True
                except sqlite3.OperationalError:
                    self.supports_fts = False

                # Schema version check / migration stub
                res = conn.execute("SELECT value FROM semantic_meta WHERE key = 'version'").fetchone()
                if res is None:
                    conn.execute("INSERT INTO semantic_meta (key, value) VALUES ('version', '1')")
        except Exception:
            # Fail closed - do not crash callers
            pass

    def write_entry(self, entry: SemanticEntry) -> str | None:
        """Writes a fully constructed SemanticEntry to the store, performing deduplication on text_hash."""
        try:
            with self._get_conn() as conn:
                metadata_json = json.dumps(entry.metadata)
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
                    # Lost the race (or duplicate): another writer owns this text_hash.
                    existing = conn.execute(
                        "SELECT fact_id FROM semantic_fact WHERE text_hash = ?",
                        (entry.text_hash,),
                    ).fetchone()
                    if existing is not None:
                        return cast(str, existing["fact_id"])
                    return None
                rowid = cursor.lastrowid
                if self.supports_fts and rowid is not None:
                    # Same transaction as the fact insert: an FTS failure rolls
                    # back the fact too, so no fact is invisible to lexical search.
                    conn.execute(
                        "INSERT INTO semantic_fact_fts (rowid, text) VALUES (?, ?)",
                        (rowid, entry.text),
                    )
                return entry.fact_id
        except sqlite3.IntegrityError:
            try:
                with self._get_conn() as conn:
                    existing = conn.execute(
                        "SELECT fact_id FROM semantic_fact WHERE text_hash = ?",
                        (entry.text_hash,),
                    ).fetchone()
                    if existing is not None:
                        return cast(str, existing["fact_id"])
            except Exception:
                pass
            return None
        except Exception:
            _LOGGER.warning("semantic write_entry failed for text_hash=%s", entry.text_hash, exc_info=True)
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
