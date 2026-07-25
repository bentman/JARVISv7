from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import numpy as np
from backend.app.core.paths import DATA_DIR
from backend.app.memory.curation import (
    TRANSITION_MATRIX,
    CorrectionResult,
    CurationJob,
    CurationJobStatus,
    CurationValidationError,
    EvidenceInput,
    EvidenceRecord,
    FactDetail,
    GovernedEvidenceAuthority,
    GovernedFactInput,
    GovernedFactRecord,
    LifecycleEventRecord,
    LifecycleState,
    MemoryPolicy,
    OperationStatus,
    StoreResult,
    require_timestamp,
    validate_error,
    validate_job_identity,
    validate_kind_filter,
    validate_list_limit,
    validate_query,
    validate_reason,
    validate_worker_identity,
)
from backend.app.memory.curation_contract import GovernedMemoryKind, validate_claim_key

SEMANTIC_SCHEMA_VERSION = 3
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
CURATION_JOB_STATUSES = (
    "pending",
    "processing",
    "retry_wait",
    "succeeded",
    "failed",
    "cancelled",
)
_WRITE_BUSY_RETRIES = 3
_WRITE_BUSY_TIMEOUT_MS = 250
_WRITE_BUSY_BACKOFF_SECONDS = 0.02

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


class _StoreConflictError(RuntimeError):
    pass


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
    evidence_authority: str = "legacy_unknown"
    state: str = "active"
    importance: float | None = None
    reinforcement_count: int = 1
    expires_at: str | None = None
    superseded_by_fact_id: str | None = None
    evidence_refs: tuple[dict[str, str], ...] = ()

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
            "evidence_authority": self.evidence_authority,
            "state": self.state,
            "importance": self.importance,
            "reinforcement_count": self.reinforcement_count,
            "expires_at": self.expires_at,
            "superseded_by_fact_id": self.superseded_by_fact_id,
            "evidence_refs": self.evidence_refs,
        }

    @classmethod
    def from_row(
        cls,
        row: sqlite3.Row,
        *,
        evidence_refs: tuple[dict[str, str], ...] = (),
    ) -> SemanticEntry:
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
            evidence_authority=row["evidence_authority"],
            state=row["state"],
            importance=row["importance"],
            reinforcement_count=row["reinforcement_count"],
            expires_at=row["expires_at"],
            superseded_by_fact_id=row["superseded_by_fact_id"],
            evidence_refs=evidence_refs,
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
        conn.execute(f"PRAGMA busy_timeout = {_WRITE_BUSY_TIMEOUT_MS}")
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
            elif version == 1:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    self._migrate_curation_jobs_to_v2(conn)
                    conn.execute(f"PRAGMA user_version = {SEMANTIC_SCHEMA_VERSION}")
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
            elif version == 2:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    self._migrate_curation_jobs_to_v3(conn)
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
        conn.execute("CREATE UNIQUE INDEX idx_semantic_fact_hash ON semantic_fact(text_hash)")
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
        self._create_curation_job_v3(conn)
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
        conn.execute("INSERT INTO semantic_meta (singleton_id, content_revision) VALUES (1, 0)")
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

    @staticmethod
    def _create_curation_job_v3(
        conn: sqlite3.Connection,
        *,
        table_name: str = "semantic_curation_job",
    ) -> None:
        conn.execute(
            f"""
            CREATE TABLE {table_name} (
                job_id TEXT NOT NULL UNIQUE CHECK (length(job_id) > 0),
                session_id TEXT PRIMARY KEY CHECK (length(session_id) > 0),
                session_artifact_path TEXT NOT NULL
                    CHECK (length(session_artifact_path) > 0),
                policy_revision INTEGER NOT NULL CHECK (policy_revision >= 1),
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending', 'processing', 'retry_wait',
                        'succeeded', 'failed', 'cancelled'
                    )),
                attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts = 3),
                authorized_at TEXT NOT NULL,
                enqueued_at TEXT NOT NULL,
                next_attempt_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                boot_id TEXT,
                claim_token TEXT,
                claimed_at TEXT,
                lease_expires_at TEXT,
                generation_started_at TEXT,
                generation_finished_at TEXT,
                generation_duration_ms REAL,
                persisted_at TEXT,
                completed_at TEXT,
                cancel_requested_at TEXT,
                cancelled_at TEXT,
                cancel_reason TEXT,
                last_error_code TEXT,
                last_error_detail TEXT,
                last_error_at TEXT,
                blocked_reason TEXT,
                last_result_reason TEXT,
                result_candidates_proposed INTEGER
                    CHECK (result_candidates_proposed IS NULL
                           OR result_candidates_proposed BETWEEN 0 AND 3),
                result_candidates_rejected INTEGER
                    CHECK (result_candidates_rejected IS NULL
                           OR result_candidates_rejected BETWEEN 0 AND 3),
                result_active_records_created INTEGER
                    CHECK (result_active_records_created IS NULL
                           OR result_active_records_created BETWEEN 0 AND 3),
                result_pending_review_created INTEGER
                    CHECK (result_pending_review_created IS NULL
                           OR result_pending_review_created BETWEEN 0 AND 3),
                result_records_reinforced INTEGER
                    CHECK (result_records_reinforced IS NULL
                           OR result_records_reinforced BETWEEN 0 AND 3),
                result_records_superseded_or_disputed INTEGER
                    CHECK (result_records_superseded_or_disputed IS NULL
                           OR result_records_superseded_or_disputed BETWEEN 0 AND 3),
                result_duplicate_noops INTEGER
                    CHECK (result_duplicate_noops IS NULL
                           OR result_duplicate_noops BETWEEN 0 AND 3),
                result_failure_count INTEGER
                    CHECK (result_failure_count IS NULL
                           OR result_failure_count BETWEEN 0 AND 3),
                runtime_name TEXT,
                model_id TEXT,
                serve_profile_id TEXT,
                accelerator TEXT,
                CHECK (
                    (claim_token IS NULL AND boot_id IS NULL
                     AND claimed_at IS NULL AND lease_expires_at IS NULL)
                    OR
                    (claim_token IS NOT NULL AND boot_id IS NOT NULL
                     AND claimed_at IS NOT NULL AND lease_expires_at IS NOT NULL)
                )
            )
            """
        )
        conn.execute(
            f"""
            CREATE INDEX idx_{table_name}_due
            ON {table_name}(status, next_attempt_at, enqueued_at, job_id)
            """
        )

    def _migrate_curation_jobs_to_v2(self, conn: sqlite3.Connection) -> None:
        self._create_curation_job_v3(
            conn,
            table_name="semantic_curation_job_v2",
        )
        rows = conn.execute(
            "SELECT * FROM semantic_curation_job ORDER BY created_at, session_id"
        ).fetchall()
        for row in rows:
            old_status = cast(str, row["status"])
            attempts = int(row["attempt_count"])
            status = {
                "completed": "succeeded",
                "failed": "retry_wait" if attempts < 3 else "failed",
            }.get(old_status, old_status)
            enqueued_at = cast(str, row["created_at"])
            conn.execute(
                """
                INSERT INTO semantic_curation_job_v2 (
                    job_id, session_id, session_artifact_path, policy_revision,
                    status, attempt_count, max_attempts, authorized_at,
                    enqueued_at, next_attempt_at, updated_at,
                    boot_id, claim_token, claimed_at, lease_expires_at,
                    completed_at, cancelled_at, cancel_reason,
                    last_error_code, last_error_detail, last_error_at
                ) VALUES (?, ?, ?, 1, ?, ?, 3, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid5(uuid.NAMESPACE_URL, f"jarvis-curation:{row['session_id']}").hex,
                    row["session_id"],
                    row["artifact_ref"],
                    status,
                    attempts,
                    enqueued_at,
                    enqueued_at,
                    row["updated_at"],
                    row["updated_at"],
                    row["lease_owner"],
                    row["lease_token"],
                    row["last_attempt_at"],
                    row["lease_expires_at"],
                    row["updated_at"] if status == "succeeded" else None,
                    row["updated_at"] if status == "cancelled" else None,
                    row["last_reason"] if status == "cancelled" else None,
                    row["last_reason"] if status in {"retry_wait", "failed"} else None,
                    row["last_error"],
                    row["updated_at"] if row["last_error"] else None,
                ),
            )
        conn.execute("DROP TABLE semantic_curation_job")
        conn.execute(
            "ALTER TABLE semantic_curation_job_v2 RENAME TO semantic_curation_job"
        )

    @staticmethod
    def _migrate_curation_jobs_to_v3(conn: sqlite3.Connection) -> None:
        for column_name in (
            "result_candidates_proposed",
            "result_candidates_rejected",
            "result_active_records_created",
            "result_pending_review_created",
            "result_records_reinforced",
            "result_records_superseded_or_disputed",
            "result_duplicate_noops",
            "result_failure_count",
        ):
            conn.execute(
                f"""
                ALTER TABLE semantic_curation_job
                ADD COLUMN {column_name} INTEGER
                    CHECK ({column_name} IS NULL OR {column_name} BETWEEN 0 AND 3)
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
            for row in conn.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")
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
        expected_job_columns = {
            "job_id",
            "session_id",
            "session_artifact_path",
            "policy_revision",
            "status",
            "attempt_count",
            "max_attempts",
            "authorized_at",
            "enqueued_at",
            "next_attempt_at",
            "updated_at",
            "boot_id",
            "claim_token",
            "claimed_at",
            "lease_expires_at",
            "generation_started_at",
            "generation_finished_at",
            "generation_duration_ms",
            "persisted_at",
            "completed_at",
            "cancel_requested_at",
            "cancelled_at",
            "cancel_reason",
            "last_error_code",
            "last_error_detail",
            "last_error_at",
            "blocked_reason",
            "last_result_reason",
            "result_candidates_proposed",
            "result_candidates_rejected",
            "result_active_records_created",
            "result_pending_review_created",
            "result_records_reinforced",
            "result_records_superseded_or_disputed",
            "result_duplicate_noops",
            "result_failure_count",
            "runtime_name",
            "model_id",
            "serve_profile_id",
            "accelerator",
        }
        if set(self._table_columns(conn, "semantic_curation_job")) != expected_job_columns:
            raise RuntimeError("versioned semantic_curation_job layout is not recognized")
        for table_name in ("semantic_policy", "semantic_meta"):
            singleton_ids = [
                row["singleton_id"]
                for row in conn.execute(
                    f"SELECT singleton_id FROM {table_name} ORDER BY singleton_id"
                )
            ]
            if singleton_ids != [1]:
                raise RuntimeError(f"{table_name} singleton authority is missing or ambiguous")

    @staticmethod
    def _is_busy_error(exc: sqlite3.OperationalError) -> bool:
        message = str(exc).lower()
        return "database is locked" in message or "database is busy" in message

    def _run_write(
        self,
        operation: Callable[[sqlite3.Connection], StoreResult[Any]],
    ) -> StoreResult[Any]:
        if not self._schema_ready:
            return StoreResult(OperationStatus.UNAVAILABLE, message=self.schema_error)
        for attempt in range(_WRITE_BUSY_RETRIES):
            conn: sqlite3.Connection | None = None
            try:
                conn = self._get_conn()
                conn.execute("BEGIN IMMEDIATE")
                result = operation(conn)
                if result.succeeded:
                    conn.commit()
                else:
                    conn.rollback()
                return result
            except _StoreConflictError as exc:
                if conn is not None and conn.in_transaction:
                    conn.rollback()
                return StoreResult(OperationStatus.CONFLICT, message=str(exc))
            except CurationValidationError as exc:
                if conn is not None and conn.in_transaction:
                    conn.rollback()
                return StoreResult(OperationStatus.INVALID, message=str(exc))
            except sqlite3.OperationalError as exc:
                if conn is not None and conn.in_transaction:
                    conn.rollback()
                if self._is_busy_error(exc):
                    if attempt + 1 == _WRITE_BUSY_RETRIES:
                        return StoreResult(
                            OperationStatus.BUSY,
                            message="semantic store is busy",
                        )
                    time.sleep(_WRITE_BUSY_BACKOFF_SECONDS * (attempt + 1))
                    continue
                return StoreResult(OperationStatus.UNAVAILABLE, message=str(exc))
            except Exception as exc:
                if conn is not None and conn.in_transaction:
                    conn.rollback()
                return StoreResult(OperationStatus.UNAVAILABLE, message=str(exc))
            finally:
                if conn is not None:
                    conn.close()
        return StoreResult(OperationStatus.BUSY, message="semantic store is busy")

    @staticmethod
    def _json_object(raw: str) -> dict[str, Any]:
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    @classmethod
    def _fact_record(cls, row: sqlite3.Row) -> GovernedFactRecord:
        return GovernedFactRecord(
            fact_id=cast(str, row["fact_id"]),
            text=cast(str, row["text"]),
            kind=cast(str, row["kind"]),
            claim_key=cast(str | None, row["claim_key"]),
            value_text=cast(str | None, row["value_text"]),
            evidence_authority=cast(str, row["evidence_authority"]),
            state=cast(str, row["state"]),
            confidence=cast(float | None, row["confidence"]),
            importance=cast(float | None, row["importance"]),
            reinforcement_count=int(row["reinforcement_count"]),
            created_at=cast(str, row["created_at"]),
            updated_at=cast(str, row["updated_at"]),
            last_confirmed_at=cast(str | None, row["last_confirmed_at"]),
            expires_at=cast(str | None, row["expires_at"]),
            superseded_by_fact_id=cast(str | None, row["superseded_by_fact_id"]),
            revision=int(row["revision"]),
            metadata=cls._json_object(cast(str, row["metadata_json"])),
            vectorizer_id=cast(str, row["vectorizer_id"]),
            vector_dim=int(row["vector_dim"]),
            text_hash=cast(str, row["text_hash"]),
        )

    @classmethod
    def _evidence_record(cls, row: sqlite3.Row) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=cast(str, row["evidence_id"]),
            fact_id=cast(str, row["fact_id"]),
            authority=cast(str, row["evidence_authority"]),
            observed_at=cast(str, row["observed_at"]),
            created_at=cast(str, row["created_at"]),
            source_session_id=cast(str | None, row["source_session_id"]),
            source_turn_id=cast(str | None, row["source_turn_id"]),
            source_field=cast(str | None, row["source_field"]),
            action_id=cast(str | None, row["action_id"]),
            action_surface=cast(str | None, row["action_surface"]),
            action_reason=cast(str | None, row["action_reason"]),
            metadata=cls._json_object(cast(str, row["metadata_json"])),
        )

    @classmethod
    def _event_record(cls, row: sqlite3.Row) -> LifecycleEventRecord:
        return LifecycleEventRecord(
            event_id=cast(str, row["event_id"]),
            fact_id=cast(str, row["fact_id"]),
            event_type=cast(str, row["event_type"]),
            prior_state=cast(str | None, row["prior_state"]),
            resulting_state=cast(str | None, row["resulting_state"]),
            related_fact_id=cast(str | None, row["related_fact_id"]),
            reason_code=cast(str, row["reason_code"]),
            occurred_at=cast(str, row["occurred_at"]),
            source_session_id=cast(str | None, row["source_session_id"]),
            source_turn_id=cast(str | None, row["source_turn_id"]),
            metadata=cls._json_object(cast(str, row["metadata_json"])),
        )

    @staticmethod
    def _job_record(row: sqlite3.Row) -> CurationJob:
        return CurationJob(
            job_id=cast(str, row["job_id"]),
            session_id=cast(str, row["session_id"]),
            session_artifact_path=cast(str, row["session_artifact_path"]),
            policy_revision=int(row["policy_revision"]),
            status=CurationJobStatus(cast(str, row["status"])),
            attempt_count=int(row["attempt_count"]),
            max_attempts=int(row["max_attempts"]),
            authorized_at=cast(str, row["authorized_at"]),
            enqueued_at=cast(str, row["enqueued_at"]),
            next_attempt_at=cast(str, row["next_attempt_at"]),
            updated_at=cast(str, row["updated_at"]),
            boot_id=cast(str | None, row["boot_id"]),
            claim_token=cast(str | None, row["claim_token"]),
            claimed_at=cast(str | None, row["claimed_at"]),
            lease_expires_at=cast(str | None, row["lease_expires_at"]),
            generation_started_at=cast(str | None, row["generation_started_at"]),
            generation_finished_at=cast(str | None, row["generation_finished_at"]),
            generation_duration_ms=cast(float | None, row["generation_duration_ms"]),
            persisted_at=cast(str | None, row["persisted_at"]),
            completed_at=cast(str | None, row["completed_at"]),
            cancel_requested_at=cast(str | None, row["cancel_requested_at"]),
            cancelled_at=cast(str | None, row["cancelled_at"]),
            cancel_reason=cast(str | None, row["cancel_reason"]),
            last_error_code=cast(str | None, row["last_error_code"]),
            last_error_detail=cast(str | None, row["last_error_detail"]),
            last_error_at=cast(str | None, row["last_error_at"]),
            blocked_reason=cast(str | None, row["blocked_reason"]),
            last_result_reason=cast(str | None, row["last_result_reason"]),
            result_candidates_proposed=cast(int | None, row["result_candidates_proposed"]),
            result_candidates_rejected=cast(int | None, row["result_candidates_rejected"]),
            result_active_records_created=cast(
                int | None, row["result_active_records_created"]
            ),
            result_pending_review_created=cast(
                int | None, row["result_pending_review_created"]
            ),
            result_records_reinforced=cast(int | None, row["result_records_reinforced"]),
            result_records_superseded_or_disputed=cast(
                int | None, row["result_records_superseded_or_disputed"]
            ),
            result_duplicate_noops=cast(int | None, row["result_duplicate_noops"]),
            result_failure_count=cast(int | None, row["result_failure_count"]),
            runtime_name=cast(str | None, row["runtime_name"]),
            model_id=cast(str | None, row["model_id"]),
            serve_profile_id=cast(str | None, row["serve_profile_id"]),
            accelerator=cast(str | None, row["accelerator"]),
        )

    @staticmethod
    def _is_mutable_governed_row(row: sqlite3.Row) -> bool:
        try:
            GovernedMemoryKind(cast(str, row["kind"]))
            LifecycleState(cast(str, row["state"]))
            validate_claim_key(cast(str, row["claim_key"]))
        except (TypeError, ValueError):
            return False
        return True

    @staticmethod
    def _increment_content_revision(conn: sqlite3.Connection) -> None:
        cursor = conn.execute(
            """
            UPDATE semantic_meta
            SET content_revision = content_revision + 1
            WHERE singleton_id = 1
            """
        )
        if cursor.rowcount != 1:
            raise RuntimeError("semantic content revision authority is unavailable")

    def read_content_revision(self) -> StoreResult[int]:
        if not self._schema_ready:
            return StoreResult(OperationStatus.UNAVAILABLE, message=self.schema_error)
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    """
                    SELECT content_revision
                    FROM semantic_meta
                    WHERE singleton_id = 1
                    """
                ).fetchone()
            if row is None:
                return StoreResult(
                    OperationStatus.UNAVAILABLE,
                    message="semantic content revision authority is unavailable",
                )
            return StoreResult(OperationStatus.SUCCESS, int(row["content_revision"]))
        except Exception as exc:
            return StoreResult(OperationStatus.UNAVAILABLE, message=str(exc))

    def read_policy(self) -> StoreResult[MemoryPolicy]:
        if not self._schema_ready:
            return StoreResult(OperationStatus.UNAVAILABLE, message=self.schema_error)
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    """
                    SELECT automatic_curation_enabled, revision, updated_at
                    FROM semantic_policy
                    WHERE singleton_id = 1
                    """
                ).fetchone()
            if row is None:
                return StoreResult(
                    OperationStatus.UNAVAILABLE,
                    message="semantic policy authority is unavailable",
                )
            return StoreResult(
                OperationStatus.SUCCESS,
                MemoryPolicy(
                    automatic_curation_enabled=bool(row["automatic_curation_enabled"]),
                    revision=int(row["revision"]),
                    updated_at=cast(str, row["updated_at"]),
                ),
            )
        except Exception as exc:
            return StoreResult(OperationStatus.UNAVAILABLE, message=str(exc))

    def read_fact(self, fact_id: str) -> StoreResult[FactDetail]:
        if not isinstance(fact_id, str) or not fact_id.strip() or len(fact_id) > 128:
            return StoreResult(OperationStatus.INVALID, message="fact_id is invalid")
        if not self._schema_ready:
            return StoreResult(OperationStatus.UNAVAILABLE, message=self.schema_error)
        try:
            with self._get_conn() as conn:
                fact = conn.execute(
                    "SELECT * FROM semantic_fact WHERE fact_id = ?",
                    (fact_id,),
                ).fetchone()
                if fact is None:
                    return StoreResult(OperationStatus.NOT_FOUND)
                evidence = conn.execute(
                    """
                    SELECT *
                    FROM semantic_evidence
                    WHERE fact_id = ?
                    ORDER BY created_at ASC, evidence_id ASC
                    """,
                    (fact_id,),
                ).fetchall()
                events = conn.execute(
                    """
                    SELECT *
                    FROM semantic_event
                    WHERE fact_id = ?
                    ORDER BY occurred_at ASC, event_id ASC
                    """,
                    (fact_id,),
                ).fetchall()
            return StoreResult(
                OperationStatus.SUCCESS,
                FactDetail(
                    fact=self._fact_record(fact),
                    evidence=tuple(self._evidence_record(row) for row in evidence),
                    events=tuple(self._event_record(row) for row in events),
                ),
            )
        except Exception as exc:
            return StoreResult(OperationStatus.UNAVAILABLE, message=str(exc))

    def list_facts(
        self,
        *,
        state: LifecycleState | None = None,
        kind: GovernedMemoryKind | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> StoreResult[tuple[GovernedFactRecord, ...]]:
        try:
            validate_list_limit(limit)
            kind_value = validate_kind_filter(kind)
            query_value = validate_query(query)
            if state is not None and not isinstance(state, LifecycleState):
                raise CurationValidationError("state filter is invalid")
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))
        if not self._schema_ready:
            return StoreResult(OperationStatus.UNAVAILABLE, message=self.schema_error)
        clauses: list[str] = []
        params: list[Any] = []
        if state is not None:
            clauses.append("state = ?")
            params.append(state.value)
        if kind_value is not None:
            clauses.append("kind = ?")
            params.append(kind_value)
        if query_value is not None:
            clauses.append("(text LIKE ? OR claim_key LIKE ? OR value_text LIKE ?)")
            pattern = f"%{query_value}%"
            params.extend((pattern, pattern, pattern))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    f"""
                    SELECT *
                    FROM semantic_fact
                    {where}
                    ORDER BY created_at DESC, fact_id ASC
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
            return StoreResult(
                OperationStatus.SUCCESS,
                tuple(self._fact_record(row) for row in rows),
            )
        except Exception as exc:
            return StoreResult(OperationStatus.UNAVAILABLE, message=str(exc))

    @staticmethod
    def _evidence_existing_row(
        conn: sqlite3.Connection,
        fact_id: str,
        evidence: EvidenceInput,
    ) -> sqlite3.Row | None:
        if evidence.action_id is not None:
            return conn.execute(
                """
                SELECT *
                FROM semantic_evidence
                WHERE fact_id = ? AND action_id = ?
                """,
                (fact_id, evidence.action_id),
            ).fetchone()
        return conn.execute(
            """
            SELECT *
            FROM semantic_evidence
            WHERE fact_id = ?
              AND source_session_id = ?
              AND source_turn_id = ?
              AND source_field = ?
              AND action_id IS NULL
            """,
            (
                fact_id,
                evidence.source_session_id,
                evidence.source_turn_id,
                evidence.source_field,
            ),
        ).fetchone()

    @classmethod
    def _insert_evidence(
        cls,
        conn: sqlite3.Connection,
        fact_id: str,
        evidence: EvidenceInput,
        *,
        created_at: str,
    ) -> tuple[bool, str]:
        metadata_json = json.dumps(
            evidence.metadata,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        existing = cls._evidence_existing_row(conn, fact_id, evidence)
        if existing is not None:
            comparable = (
                cast(str, existing["evidence_authority"]),
                cast(str, existing["observed_at"]),
                cast(str | None, existing["source_session_id"]),
                cast(str | None, existing["source_turn_id"]),
                cast(str | None, existing["source_field"]),
                cast(str | None, existing["action_id"]),
                cast(str | None, existing["action_surface"]),
                cast(str | None, existing["action_reason"]),
                cast(str, existing["metadata_json"]),
            )
            requested = (
                evidence.authority.value,
                evidence.observed_at,
                evidence.source_session_id,
                evidence.source_turn_id,
                evidence.source_field,
                evidence.action_id,
                evidence.action_surface,
                evidence.action_reason,
                metadata_json,
            )
            if comparable != requested:
                raise _StoreConflictError(
                    "evidence origin already exists with different parameters"
                )
            return False, cast(str, existing["evidence_id"])

        evidence_id = uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO semantic_evidence (
                evidence_id, fact_id,
                source_session_id, source_turn_id, source_field,
                action_id, action_surface, action_reason,
                evidence_authority, observed_at, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
                fact_id,
                evidence.source_session_id,
                evidence.source_turn_id,
                evidence.source_field,
                evidence.action_id,
                evidence.action_surface,
                evidence.action_reason,
                evidence.authority.value,
                evidence.observed_at,
                created_at,
                metadata_json,
            ),
        )
        return True, evidence_id

    @staticmethod
    def _insert_event(
        conn: sqlite3.Connection,
        *,
        fact_id: str,
        event_type: str,
        prior_state: str | None,
        resulting_state: str | None,
        related_fact_id: str | None,
        reason_code: str,
        occurred_at: str,
        evidence: EvidenceInput | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event_metadata = dict(metadata or {})
        if evidence is not None and evidence.action_id is not None:
            event_metadata["action_id"] = evidence.action_id
            event_metadata["action_surface"] = evidence.action_surface
        conn.execute(
            """
            INSERT INTO semantic_event (
                event_id, fact_id, event_type, prior_state, resulting_state,
                related_fact_id, reason_code, occurred_at,
                source_session_id, source_turn_id, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                fact_id,
                event_type,
                prior_state,
                resulting_state,
                related_fact_id,
                reason_code,
                occurred_at,
                evidence.source_session_id if evidence is not None else None,
                evidence.source_turn_id if evidence is not None else None,
                json.dumps(
                    event_metadata,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            ),
        )

    @staticmethod
    def _vector_values(
        fact: GovernedFactInput,
    ) -> tuple[str, int, bytes]:
        vectorizer_id = fact.vectorizer_id or "local_hashing_trick_v1_128"
        vector = (
            np.array(fact.vector, dtype="<f4")
            if fact.vector is not None
            else text_to_vector(fact.text, dim=128)
        )
        return vectorizer_id, len(vector), vector.tobytes()

    def _insert_governed_fact_row(
        self,
        conn: sqlite3.Connection,
        fact: GovernedFactInput,
        *,
        fact_id: str,
        state: LifecycleState,
        now: str,
    ) -> None:
        vectorizer_id, vector_dim, vector_blob = self._vector_values(fact)
        cursor = conn.execute(
            """
            INSERT INTO semantic_fact (
                fact_id, text, source_session_id, source_turn_id, source_field,
                created_at, updated_at, kind, confidence, metadata_json,
                vectorizer_id, vector_dim, vector_blob, text_hash,
                claim_key, value_text, evidence_authority, state, importance,
                reinforcement_count, last_confirmed_at, expires_at,
                superseded_by_fact_id, revision
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1,
                ?, ?, NULL, 1
            )
            """,
            (
                fact_id,
                fact.text,
                fact.evidence[0].source_session_id,
                fact.evidence[0].source_turn_id,
                fact.evidence[0].source_field,
                now,
                now,
                fact.identity.kind.value,
                fact.confidence,
                json.dumps(
                    fact.metadata,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                vectorizer_id,
                vector_dim,
                vector_blob,
                _get_text_hash(fact.text),
                fact.identity.claim_key,
                fact.value_text,
                fact.evidence_authority.value,
                state.value,
                fact.importance,
                now if state is LifecycleState.ACTIVE else None,
                fact.expires_at,
            ),
        )
        if self.supports_fts and cursor.lastrowid is not None:
            conn.execute(
                "INSERT INTO semantic_fact_fts (rowid, text) VALUES (?, ?)",
                (cursor.lastrowid, fact.text),
            )
        for evidence in fact.evidence:
            self._insert_evidence(conn, fact_id, evidence, created_at=now)
        self._insert_event(
            conn,
            fact_id=fact_id,
            event_type="created",
            prior_state=None,
            resulting_state=state.value,
            related_fact_id=None,
            reason_code="governed_fact_created",
            occurred_at=now,
            evidence=fact.evidence[0],
        )

    def create_governed_fact(
        self,
        fact: GovernedFactInput,
    ) -> StoreResult[GovernedFactRecord]:
        def operation(conn: sqlite3.Connection) -> StoreResult[GovernedFactRecord]:
            now = _iso_now()
            text_hash = _get_text_hash(fact.text)
            same_text = conn.execute(
                "SELECT * FROM semantic_fact WHERE text_hash = ?",
                (text_hash,),
            ).fetchone()
            if same_text is not None:
                if (
                    same_text["kind"] != fact.identity.kind.value
                    or same_text["claim_key"] != fact.identity.claim_key
                    or same_text["value_text"] != fact.value_text
                ):
                    return StoreResult(
                        OperationStatus.CONFLICT,
                        message="text hash already belongs to a different governed identity",
                    )
                if not self._is_mutable_governed_row(same_text):
                    return StoreResult(
                        OperationStatus.CONFLICT,
                        message="matching fact has an unknown or terminal contract",
                    )
                if same_text["state"] not in {
                    LifecycleState.PENDING_REVIEW.value,
                    LifecycleState.ACTIVE.value,
                    LifecycleState.DISPUTED.value,
                }:
                    return StoreResult(
                        OperationStatus.CONFLICT,
                        message="terminal facts cannot be implicitly reinforced",
                    )
                return self._reinforce_existing_from_creation(
                    conn,
                    same_text,
                    fact,
                    now=now,
                )

            occupant = conn.execute(
                """
                SELECT *
                FROM semantic_fact
                WHERE claim_key = ?
                  AND state IN ('active', 'pending_review', 'disputed')
                ORDER BY
                    CASE state
                        WHEN 'active' THEN 0
                        WHEN 'disputed' THEN 1
                        ELSE 2
                    END,
                    created_at ASC,
                    fact_id ASC
                LIMIT 1
                """,
                (fact.identity.claim_key,),
            ).fetchone()
            if occupant is not None and not self._is_mutable_governed_row(occupant):
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="claim identity is occupied by an unknown governed record",
                )
            if (
                occupant is not None
                and occupant["kind"] == fact.identity.kind.value
                and occupant["value_text"] == fact.value_text
            ):
                return self._reinforce_existing_from_creation(
                    conn,
                    occupant,
                    fact,
                    now=now,
                )
            if (
                occupant is not None
                and occupant["kind"] != fact.identity.kind.value
                and occupant["value_text"] == fact.value_text
            ):
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="claim identity is occupied by a different governed kind",
                )

            resulting_state = fact.state
            result_status = OperationStatus.SUCCESS
            if occupant is not None and occupant["value_text"] != fact.value_text:
                resulting_state = LifecycleState.PENDING_REVIEW
                result_status = OperationStatus.REVIEW_REQUIRED

            fact_id = uuid.uuid4().hex
            self._insert_governed_fact_row(
                conn,
                fact,
                fact_id=fact_id,
                state=resulting_state,
                now=now,
            )
            self._increment_content_revision(conn)
            row = conn.execute(
                "SELECT * FROM semantic_fact WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            return StoreResult(
                result_status,
                self._fact_record(row),
                (
                    "different value for an occupied claim requires review"
                    if result_status is OperationStatus.REVIEW_REQUIRED
                    else None
                ),
            )

        return cast(StoreResult[GovernedFactRecord], self._run_write(operation))

    def _reinforce_existing_from_creation(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        fact: GovernedFactInput,
        *,
        now: str,
    ) -> StoreResult[GovernedFactRecord]:
        inserted_ids: list[str] = []
        for evidence in fact.evidence:
            inserted, evidence_id = self._insert_evidence(
                conn,
                cast(str, row["fact_id"]),
                evidence,
                created_at=now,
            )
            if inserted:
                inserted_ids.append(evidence_id)
        if not inserted_ids:
            return StoreResult(OperationStatus.NO_CHANGE, self._fact_record(row))

        confidence = (
            max(
                float(row["confidence"]) if row["confidence"] is not None else 0.0,
                fact.confidence if fact.confidence is not None else 0.0,
            )
            if row["confidence"] is not None or fact.confidence is not None
            else None
        )
        importance = (
            max(
                float(row["importance"]) if row["importance"] is not None else 0.0,
                fact.importance if fact.importance is not None else 0.0,
            )
            if row["importance"] is not None or fact.importance is not None
            else None
        )
        conn.execute(
            """
            UPDATE semantic_fact
            SET reinforcement_count = reinforcement_count + 1,
                confidence = ?,
                importance = ?,
                last_confirmed_at = ?,
                updated_at = ?,
                revision = revision + 1
            WHERE fact_id = ?
            """,
            (
                confidence,
                importance,
                now,
                now,
                row["fact_id"],
            ),
        )
        self._insert_event(
            conn,
            fact_id=cast(str, row["fact_id"]),
            event_type="reinforced",
            prior_state=cast(str, row["state"]),
            resulting_state=cast(str, row["state"]),
            related_fact_id=None,
            reason_code="compatible_evidence",
            occurred_at=now,
            evidence=fact.evidence[0],
            metadata={"evidence_ids": inserted_ids},
        )
        self._increment_content_revision(conn)
        updated = conn.execute(
            "SELECT * FROM semantic_fact WHERE fact_id = ?",
            (row["fact_id"],),
        ).fetchone()
        return StoreResult(OperationStatus.SUCCESS, self._fact_record(updated))

    def append_evidence(
        self,
        fact_id: str,
        evidence: EvidenceInput,
        *,
        expected_revision: int | None = None,
    ) -> StoreResult[GovernedFactRecord]:
        try:
            self._validate_fact_id(fact_id)
            if expected_revision is not None:
                self._validate_expected_revision(expected_revision)
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[GovernedFactRecord]:
            row = conn.execute(
                "SELECT * FROM semantic_fact WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            if row is None:
                return StoreResult(OperationStatus.NOT_FOUND)
            if expected_revision is not None and int(row["revision"]) != expected_revision:
                return StoreResult(OperationStatus.CONFLICT, message="stale fact revision")
            if not self._is_mutable_governed_row(row):
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="fact has an unknown or invalid governed contract",
                )
            now = _iso_now()
            inserted, evidence_id = self._insert_evidence(
                conn,
                fact_id,
                evidence,
                created_at=now,
            )
            if not inserted:
                return StoreResult(OperationStatus.NO_CHANGE, self._fact_record(row))
            conn.execute(
                """
                UPDATE semantic_fact
                SET updated_at = ?, revision = revision + 1
                WHERE fact_id = ?
                """,
                (now, fact_id),
            )
            self._insert_event(
                conn,
                fact_id=fact_id,
                event_type="evidence_appended",
                prior_state=cast(str, row["state"]),
                resulting_state=cast(str, row["state"]),
                related_fact_id=None,
                reason_code="evidence_appended",
                occurred_at=now,
                evidence=evidence,
                metadata={"evidence_id": evidence_id},
            )
            updated = conn.execute(
                "SELECT * FROM semantic_fact WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            return StoreResult(OperationStatus.SUCCESS, self._fact_record(updated))

        return cast(StoreResult[GovernedFactRecord], self._run_write(operation))

    @staticmethod
    def _validate_expected_revision(expected_revision: int) -> None:
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise CurationValidationError("expected_revision must be a positive integer")

    @staticmethod
    def _validate_fact_id(fact_id: str, label: str = "fact_id") -> None:
        if not isinstance(fact_id, str) or not fact_id.strip() or len(fact_id) > 128:
            raise CurationValidationError(f"{label} is invalid")

    @staticmethod
    def _require_user_action(evidence: EvidenceInput) -> None:
        if (
            evidence.authority is not GovernedEvidenceAuthority.DIRECT_USER_ACTION
            or evidence.action_id is None
        ):
            raise CurationValidationError(
                "operator lifecycle mutations require direct user-action evidence"
            )

    def _transition_fact(
        self,
        fact_id: str,
        *,
        expected_revision: int,
        target: LifecycleState,
        evidence: EvidenceInput,
        reason: str,
        event_type: str,
        related_fact_id: str | None = None,
    ) -> StoreResult[GovernedFactRecord]:
        try:
            self._validate_fact_id(fact_id)
            self._validate_expected_revision(expected_revision)
            self._require_user_action(evidence)
            validate_reason(reason)
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[GovernedFactRecord]:
            row = conn.execute(
                "SELECT * FROM semantic_fact WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            if row is None:
                return StoreResult(OperationStatus.NOT_FOUND)
            if int(row["revision"]) != expected_revision:
                return StoreResult(OperationStatus.CONFLICT, message="stale fact revision")
            if not self._is_mutable_governed_row(row):
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="fact has an unknown or invalid governed contract",
                )
            current = LifecycleState(cast(str, row["state"]))
            if target not in TRANSITION_MATRIX[current]:
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message=f"transition {current.value} -> {target.value} is not allowed",
                )
            if target is LifecycleState.ACTIVE:
                active_occupant = conn.execute(
                    """
                    SELECT fact_id
                    FROM semantic_fact
                    WHERE claim_key = ?
                      AND fact_id <> ?
                      AND state = 'active'
                    LIMIT 1
                    """,
                    (row["claim_key"], fact_id),
                ).fetchone()
                if active_occupant is not None:
                    return StoreResult(
                        OperationStatus.CONFLICT,
                        message="claim identity already has an active occupant",
                    )
            now = _iso_now()
            inserted, _ = self._insert_evidence(
                conn,
                fact_id,
                evidence,
                created_at=now,
            )
            if not inserted:
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="user-action evidence was already used for this fact",
                )
            cursor = conn.execute(
                """
                UPDATE semantic_fact
                SET state = ?,
                    superseded_by_fact_id = ?,
                    last_confirmed_at = CASE WHEN ? = 'active' THEN ? ELSE last_confirmed_at END,
                    updated_at = ?,
                    revision = revision + 1
                WHERE fact_id = ? AND revision = ?
                """,
                (
                    target.value,
                    related_fact_id,
                    target.value,
                    now,
                    now,
                    fact_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise _StoreConflictError("fact revision changed during transition")
            self._insert_event(
                conn,
                fact_id=fact_id,
                event_type=event_type,
                prior_state=current.value,
                resulting_state=target.value,
                related_fact_id=related_fact_id,
                reason_code=reason,
                occurred_at=now,
                evidence=evidence,
            )
            self._increment_content_revision(conn)
            updated = conn.execute(
                "SELECT * FROM semantic_fact WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            return StoreResult(OperationStatus.SUCCESS, self._fact_record(updated))

        return cast(StoreResult[GovernedFactRecord], self._run_write(operation))

    def confirm_fact(
        self,
        fact_id: str,
        *,
        expected_revision: int,
        evidence: EvidenceInput,
        reason: str = "user_confirmed",
    ) -> StoreResult[GovernedFactRecord]:
        return self._transition_fact(
            fact_id,
            expected_revision=expected_revision,
            target=LifecycleState.ACTIVE,
            evidence=evidence,
            reason=reason,
            event_type="confirmed",
        )

    def dispute_fact(
        self,
        fact_id: str,
        *,
        expected_revision: int,
        evidence: EvidenceInput,
        reason: str = "user_disputed",
    ) -> StoreResult[GovernedFactRecord]:
        return self._transition_fact(
            fact_id,
            expected_revision=expected_revision,
            target=LifecycleState.DISPUTED,
            evidence=evidence,
            reason=reason,
            event_type="disputed",
        )

    def expire_fact(
        self,
        fact_id: str,
        *,
        expected_revision: int,
        evidence: EvidenceInput,
        reason: str = "explicit_expiration",
    ) -> StoreResult[GovernedFactRecord]:
        return self._transition_fact(
            fact_id,
            expected_revision=expected_revision,
            target=LifecycleState.EXPIRED,
            evidence=evidence,
            reason=reason,
            event_type="expired",
        )

    def forget_fact(
        self,
        fact_id: str,
        *,
        expected_revision: int,
        evidence: EvidenceInput,
        reason: str = "user_forgotten",
    ) -> StoreResult[GovernedFactRecord]:
        return self._transition_fact(
            fact_id,
            expected_revision=expected_revision,
            target=LifecycleState.FORGOTTEN,
            evidence=evidence,
            reason=reason,
            event_type="forgotten",
        )

    def reinforce_fact(
        self,
        fact_id: str,
        *,
        evidence: EvidenceInput,
        confidence: float | None = None,
        importance: float | None = None,
        confirmed_at: str | None = None,
    ) -> StoreResult[GovernedFactRecord]:
        try:
            self._validate_fact_id(fact_id)
            if confidence is not None and (
                isinstance(confidence, bool)
                or not math.isfinite(float(confidence))
                or not 0.0 <= float(confidence) <= 1.0
            ):
                raise CurationValidationError("confidence must be finite and between 0 and 1")
            if importance is not None and (
                isinstance(importance, bool)
                or not math.isfinite(float(importance))
                or not 0.0 <= float(importance) <= 1.0
            ):
                raise CurationValidationError("importance must be finite and between 0 and 1")
            if confirmed_at is not None:
                require_timestamp(confirmed_at, "confirmed_at")
        except (CurationValidationError, TypeError, ValueError) as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[GovernedFactRecord]:
            row = conn.execute(
                "SELECT * FROM semantic_fact WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            if row is None:
                return StoreResult(OperationStatus.NOT_FOUND)
            if not self._is_mutable_governed_row(row):
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="fact has an unknown or invalid governed contract",
                )
            state = LifecycleState(cast(str, row["state"]))
            if state not in {
                LifecycleState.PENDING_REVIEW,
                LifecycleState.ACTIVE,
                LifecycleState.DISPUTED,
            }:
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="terminal facts cannot be reinforced",
                )
            now = _iso_now()
            inserted, evidence_id = self._insert_evidence(
                conn,
                fact_id,
                evidence,
                created_at=now,
            )
            if not inserted:
                return StoreResult(OperationStatus.NO_CHANGE, self._fact_record(row))
            bounded_confidence = (
                max(
                    float(row["confidence"]) if row["confidence"] is not None else 0.0,
                    float(confidence) if confidence is not None else 0.0,
                )
                if row["confidence"] is not None or confidence is not None
                else None
            )
            bounded_importance = (
                max(
                    float(row["importance"]) if row["importance"] is not None else 0.0,
                    float(importance) if importance is not None else 0.0,
                )
                if row["importance"] is not None or importance is not None
                else None
            )
            cursor = conn.execute(
                """
                UPDATE semantic_fact
                SET reinforcement_count = reinforcement_count + 1,
                    confidence = ?,
                    importance = ?,
                    last_confirmed_at = ?,
                    updated_at = ?,
                    revision = revision + 1
                WHERE fact_id = ?
                  AND state IN ('pending_review', 'active', 'disputed')
                """,
                (
                    bounded_confidence,
                    bounded_importance,
                    confirmed_at or now,
                    now,
                    fact_id,
                ),
            )
            if cursor.rowcount != 1:
                raise _StoreConflictError("fact changed during reinforcement")
            self._insert_event(
                conn,
                fact_id=fact_id,
                event_type="reinforced",
                prior_state=state.value,
                resulting_state=state.value,
                related_fact_id=None,
                reason_code="compatible_evidence",
                occurred_at=now,
                evidence=evidence,
                metadata={"evidence_id": evidence_id},
            )
            self._increment_content_revision(conn)
            updated = conn.execute(
                "SELECT * FROM semantic_fact WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            return StoreResult(OperationStatus.SUCCESS, self._fact_record(updated))

        return cast(StoreResult[GovernedFactRecord], self._run_write(operation))

    def supersede_fact(
        self,
        fact_id: str,
        *,
        related_fact_id: str,
        expected_revision: int,
        evidence: EvidenceInput,
        reason: str = "explicit_supersession",
    ) -> StoreResult[GovernedFactRecord]:
        if fact_id == related_fact_id:
            return StoreResult(
                OperationStatus.INVALID,
                message="a fact cannot supersede itself",
            )
        try:
            self._validate_fact_id(fact_id)
            self._validate_fact_id(related_fact_id, "related_fact_id")
            self._validate_expected_revision(expected_revision)
            self._require_user_action(evidence)
            validate_reason(reason)
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[GovernedFactRecord]:
            original = conn.execute(
                "SELECT * FROM semantic_fact WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            related = conn.execute(
                "SELECT * FROM semantic_fact WHERE fact_id = ?",
                (related_fact_id,),
            ).fetchone()
            if original is None or related is None:
                return StoreResult(OperationStatus.NOT_FOUND)
            if int(original["revision"]) != expected_revision:
                return StoreResult(OperationStatus.CONFLICT, message="stale fact revision")
            if not self._is_mutable_governed_row(original) or not self._is_mutable_governed_row(
                related
            ):
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="supersession requires valid application-owned identities",
                )
            original_state = LifecycleState(cast(str, original["state"]))
            if LifecycleState.SUPERSEDED not in TRANSITION_MATRIX[original_state]:
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="current lifecycle state cannot be superseded",
                )
            if related["state"] != LifecycleState.ACTIVE.value:
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="related superseding fact must be active",
                )
            if original["claim_key"] != related["claim_key"] or original["kind"] != related["kind"]:
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="superseding facts must share application-owned identity",
                )
            cursor_id: str | None = related_fact_id
            visited: set[str] = set()
            while cursor_id is not None:
                if cursor_id == fact_id:
                    return StoreResult(
                        OperationStatus.CONFLICT,
                        message="supersession would create a cycle",
                    )
                if cursor_id in visited:
                    return StoreResult(
                        OperationStatus.CONFLICT,
                        message="existing supersession chain contains a cycle",
                    )
                visited.add(cursor_id)
                chain_row = conn.execute(
                    """
                    SELECT superseded_by_fact_id
                    FROM semantic_fact
                    WHERE fact_id = ?
                    """,
                    (cursor_id,),
                ).fetchone()
                cursor_id = (
                    cast(str | None, chain_row["superseded_by_fact_id"])
                    if chain_row is not None
                    else None
                )
            now = _iso_now()
            inserted, _ = self._insert_evidence(
                conn,
                fact_id,
                evidence,
                created_at=now,
            )
            if not inserted:
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="user-action evidence was already used for this fact",
                )
            conn.execute(
                """
                UPDATE semantic_fact
                SET state = 'superseded',
                    superseded_by_fact_id = ?,
                    updated_at = ?,
                    revision = revision + 1
                WHERE fact_id = ? AND revision = ?
                """,
                (related_fact_id, now, fact_id, expected_revision),
            )
            self._insert_event(
                conn,
                fact_id=fact_id,
                event_type="superseded",
                prior_state=original_state.value,
                resulting_state=LifecycleState.SUPERSEDED.value,
                related_fact_id=related_fact_id,
                reason_code=reason,
                occurred_at=now,
                evidence=evidence,
            )
            self._increment_content_revision(conn)
            updated = conn.execute(
                "SELECT * FROM semantic_fact WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            return StoreResult(OperationStatus.SUCCESS, self._fact_record(updated))

        return cast(StoreResult[GovernedFactRecord], self._run_write(operation))

    def correct_fact(
        self,
        fact_id: str,
        *,
        expected_revision: int,
        replacement: GovernedFactInput,
        evidence: EvidenceInput,
        reason: str = "explicit_user_correction",
    ) -> StoreResult[CorrectionResult]:
        try:
            self._validate_fact_id(fact_id)
            self._validate_expected_revision(expected_revision)
            self._require_user_action(evidence)
            validate_reason(reason)
            if replacement.state is not LifecycleState.ACTIVE:
                raise CurationValidationError("a correction replacement must start active")
            if replacement.evidence_authority is not GovernedEvidenceAuthority.DIRECT_USER_ACTION:
                raise CurationValidationError(
                    "a correction replacement must preserve direct user-action authority"
                )
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[CorrectionResult]:
            original = conn.execute(
                "SELECT * FROM semantic_fact WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            if original is None:
                return StoreResult(OperationStatus.NOT_FOUND)
            if int(original["revision"]) != expected_revision:
                return StoreResult(OperationStatus.CONFLICT, message="stale fact revision")
            if not self._is_mutable_governed_row(original):
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="fact has an unknown or invalid governed contract",
                )
            original_state = LifecycleState(cast(str, original["state"]))
            if LifecycleState.SUPERSEDED not in TRANSITION_MATRIX[original_state]:
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="current lifecycle state cannot be corrected",
                )
            if (
                original["kind"] != replacement.identity.kind.value
                or original["claim_key"] != replacement.identity.claim_key
            ):
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="correction must reuse the application-owned claim identity",
                )
            duplicate_text = conn.execute(
                "SELECT fact_id FROM semantic_fact WHERE text_hash = ?",
                (_get_text_hash(replacement.text),),
            ).fetchone()
            if duplicate_text is not None:
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="replacement text already belongs to another fact",
                )
            other_occupant = conn.execute(
                """
                SELECT fact_id
                FROM semantic_fact
                WHERE claim_key = ?
                  AND fact_id <> ?
                  AND state = 'active'
                LIMIT 1
                """,
                (replacement.identity.claim_key, fact_id),
            ).fetchone()
            if other_occupant is not None:
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="claim identity already has another active occupant",
                )
            now = _iso_now()
            replacement_id = uuid.uuid4().hex
            self._insert_governed_fact_row(
                conn,
                replacement,
                fact_id=replacement_id,
                state=LifecycleState.ACTIVE,
                now=now,
            )
            self._insert_evidence(
                conn,
                replacement_id,
                evidence,
                created_at=now,
            )
            inserted_on_original, _ = self._insert_evidence(
                conn,
                fact_id,
                evidence,
                created_at=now,
            )
            if not inserted_on_original:
                return StoreResult(
                    OperationStatus.CONFLICT,
                    message="user-action evidence was already used for this fact",
                )
            conn.execute(
                """
                UPDATE semantic_fact
                SET state = 'superseded',
                    superseded_by_fact_id = ?,
                    updated_at = ?,
                    revision = revision + 1
                WHERE fact_id = ? AND revision = ?
                """,
                (replacement_id, now, fact_id, expected_revision),
            )
            self._insert_event(
                conn,
                fact_id=fact_id,
                event_type="corrected",
                prior_state=original_state.value,
                resulting_state=LifecycleState.SUPERSEDED.value,
                related_fact_id=replacement_id,
                reason_code=reason,
                occurred_at=now,
                evidence=evidence,
            )
            self._insert_event(
                conn,
                fact_id=replacement_id,
                event_type="correction_replacement",
                prior_state=None,
                resulting_state=LifecycleState.ACTIVE.value,
                related_fact_id=fact_id,
                reason_code=reason,
                occurred_at=now,
                evidence=evidence,
            )
            self._increment_content_revision(conn)
            original_updated = conn.execute(
                "SELECT * FROM semantic_fact WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            replacement_row = conn.execute(
                "SELECT * FROM semantic_fact WHERE fact_id = ?",
                (replacement_id,),
            ).fetchone()
            return StoreResult(
                OperationStatus.SUCCESS,
                CorrectionResult(
                    original=self._fact_record(original_updated),
                    replacement=self._fact_record(replacement_row),
                ),
            )

        return cast(StoreResult[CorrectionResult], self._run_write(operation))

    def update_policy(
        self,
        *,
        automatic_curation_enabled: bool,
        expected_revision: int,
    ) -> StoreResult[MemoryPolicy]:
        try:
            self._validate_expected_revision(expected_revision)
            if not isinstance(automatic_curation_enabled, bool):
                raise CurationValidationError("automatic_curation_enabled must be boolean")
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[MemoryPolicy]:
            row = conn.execute("SELECT * FROM semantic_policy WHERE singleton_id = 1").fetchone()
            if row is None:
                return StoreResult(
                    OperationStatus.UNAVAILABLE,
                    message="semantic policy authority is unavailable",
                )
            if int(row["revision"]) != expected_revision:
                return StoreResult(OperationStatus.CONFLICT, message="stale policy revision")
            current = bool(row["automatic_curation_enabled"])
            if current is automatic_curation_enabled:
                return StoreResult(
                    OperationStatus.NO_CHANGE,
                    MemoryPolicy(
                        automatic_curation_enabled=current,
                        revision=int(row["revision"]),
                        updated_at=cast(str, row["updated_at"]),
                    ),
                )
            now = _iso_now()
            cursor = conn.execute(
                """
                UPDATE semantic_policy
                SET automatic_curation_enabled = ?,
                    revision = revision + 1,
                    updated_at = ?
                WHERE singleton_id = 1 AND revision = ?
                """,
                (int(automatic_curation_enabled), now, expected_revision),
            )
            if cursor.rowcount != 1:
                raise _StoreConflictError("policy revision changed during update")
            if not automatic_curation_enabled:
                conn.execute(
                    """
                    UPDATE semantic_curation_job
                    SET status = 'cancelled',
                        updated_at = ?,
                        cancelled_at = ?,
                        cancel_reason = 'policy_disabled',
                        blocked_reason = NULL
                    WHERE status IN ('pending', 'retry_wait')
                    """,
                    (now, now),
                )
                conn.execute(
                    """
                    UPDATE semantic_curation_job
                    SET cancel_requested_at = ?,
                        updated_at = ?
                    WHERE status = 'processing'
                    """,
                    (now, now),
                )
            updated = conn.execute(
                "SELECT * FROM semantic_policy WHERE singleton_id = 1"
            ).fetchone()
            return StoreResult(
                OperationStatus.SUCCESS,
                MemoryPolicy(
                    automatic_curation_enabled=bool(updated["automatic_curation_enabled"]),
                    revision=int(updated["revision"]),
                    updated_at=cast(str, updated["updated_at"]),
                ),
            )

        return cast(StoreResult[MemoryPolicy], self._run_write(operation))

    def enqueue_curation_job(
        self,
        *,
        session_id: str,
        artifact_ref: str,
        policy_revision: int = 1,
        authorized_at: str | None = None,
    ) -> StoreResult[CurationJob]:
        try:
            validate_job_identity(session_id, artifact_ref)
            self._validate_expected_revision(policy_revision)
            authorized_at = authorized_at or _iso_now()
            require_timestamp(authorized_at, "authorized_at")
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[CurationJob]:
            existing = conn.execute(
                "SELECT * FROM semantic_curation_job WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["session_artifact_path"] != artifact_ref
                    or int(existing["policy_revision"]) != policy_revision
                ):
                    return StoreResult(
                        OperationStatus.CONFLICT,
                        message="session is already queued with different authorization",
                    )
                return StoreResult(OperationStatus.NO_CHANGE, self._job_record(existing))
            now = _iso_now()
            policy = conn.execute(
                """
                SELECT automatic_curation_enabled, revision
                FROM semantic_policy WHERE singleton_id = 1
                """
            ).fetchone()
            authorized = (
                policy is not None
                and bool(policy["automatic_curation_enabled"])
                and int(policy["revision"]) == policy_revision
            )
            initial_status = "pending" if authorized else "cancelled"
            conn.execute(
                """
                INSERT INTO semantic_curation_job (
                    job_id, session_id, session_artifact_path, policy_revision,
                    status, attempt_count, max_attempts, authorized_at,
                    enqueued_at, next_attempt_at, updated_at,
                    cancelled_at, cancel_reason
                ) VALUES (?, ?, ?, ?, ?, 0, 3, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid5(uuid.NAMESPACE_URL, f"jarvis-curation:{session_id}").hex,
                    session_id,
                    artifact_ref,
                    policy_revision,
                    initial_status,
                    authorized_at,
                    now,
                    now,
                    now,
                    None if authorized else now,
                    None if authorized else "policy_revision_changed",
                ),
            )
            row = conn.execute(
                "SELECT * FROM semantic_curation_job WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return StoreResult(OperationStatus.SUCCESS, self._job_record(row))

        return cast(StoreResult[CurationJob], self._run_write(operation))

    def list_curation_jobs(
        self,
        *,
        max_attempts: int = 3,
        limit: int = 50,
        include_terminal: bool = False,
    ) -> StoreResult[tuple[CurationJob, ...]]:
        try:
            validate_list_limit(limit)
            if (
                isinstance(max_attempts, bool)
                or not isinstance(max_attempts, int)
                or max_attempts < 1
            ):
                raise CurationValidationError("max_attempts must be a positive integer")
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))
        if not self._schema_ready:
            return StoreResult(OperationStatus.UNAVAILABLE, message=self.schema_error)
        try:
            with self._get_conn() as conn:
                statuses = (
                    "('pending', 'retry_wait', 'processing', 'succeeded', 'failed', 'cancelled')"
                    if include_terminal
                    else "('pending', 'retry_wait')"
                )
                rows = conn.execute(
                    f"""
                    SELECT *
                    FROM semantic_curation_job
                    WHERE status IN {statuses}
                      AND attempt_count < ?
                    ORDER BY next_attempt_at, enqueued_at, job_id
                    LIMIT ?
                    """,
                    (max_attempts, limit),
                ).fetchall()
            return StoreResult(
                OperationStatus.SUCCESS,
                tuple(self._job_record(row) for row in rows),
            )
        except Exception as exc:
            return StoreResult(OperationStatus.UNAVAILABLE, message=str(exc))

    def claim_curation_job(
        self,
        *,
        worker_id: str,
        max_attempts: int,
        lease_seconds: int,
        boot_id: str | None = None,
        claimed_at: str | None = None,
    ) -> StoreResult[CurationJob]:
        try:
            validate_worker_identity(worker_id)
            boot_id = boot_id or worker_id
            validate_worker_identity(boot_id)
            if (
                isinstance(max_attempts, bool)
                or not isinstance(max_attempts, int)
                or max_attempts < 1
            ):
                raise CurationValidationError("max_attempts must be a positive integer")
            if (
                isinstance(lease_seconds, bool)
                or not isinstance(lease_seconds, int)
                or not 1 <= lease_seconds <= 86_400
            ):
                raise CurationValidationError("lease_seconds must be between 1 and 86400")
            if claimed_at is not None:
                require_timestamp(claimed_at, "claimed_at")
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[CurationJob]:
            now_dt = (
                datetime.fromisoformat(claimed_at).astimezone(UTC)
                if claimed_at is not None
                else datetime.now(UTC)
            )
            now = now_dt.isoformat()
            row = conn.execute(
                """
                SELECT *
                FROM semantic_curation_job
                WHERE status IN ('pending', 'retry_wait')
                  AND attempt_count < ?
                  AND next_attempt_at <= ?
                ORDER BY next_attempt_at, enqueued_at, job_id
                LIMIT 1
                """,
                (max_attempts, now),
            ).fetchone()
            if row is None:
                return StoreResult(OperationStatus.NOT_FOUND)
            claim_token = uuid.uuid4().hex
            lease_expires_at = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
            cursor = conn.execute(
                """
                UPDATE semantic_curation_job
                SET status = 'processing',
                    attempt_count = attempt_count + 1,
                    updated_at = ?,
                    boot_id = ?,
                    claim_token = ?,
                    claimed_at = ?,
                    lease_expires_at = ?,
                    blocked_reason = NULL,
                    last_error_code = NULL,
                    last_error_detail = NULL
                WHERE session_id = ?
                  AND status IN ('pending', 'retry_wait')
                  AND attempt_count < ?
                """,
                (
                    now,
                    boot_id,
                    claim_token,
                    now,
                    lease_expires_at,
                    row["session_id"],
                    max_attempts,
                ),
            )
            if cursor.rowcount != 1:
                raise _StoreConflictError("curation job changed during claim")
            claimed = conn.execute(
                "SELECT * FROM semantic_curation_job WHERE session_id = ?",
                (row["session_id"],),
            ).fetchone()
            return StoreResult(OperationStatus.SUCCESS, self._job_record(claimed))

        return cast(StoreResult[CurationJob], self._run_write(operation))

    def read_curation_job(self, session_id: str) -> StoreResult[CurationJob]:
        try:
            validate_job_identity(session_id)
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM semantic_curation_job WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
            if row is None:
                return StoreResult(OperationStatus.NOT_FOUND)
            return StoreResult(OperationStatus.SUCCESS, self._job_record(row))
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))
        except Exception as exc:
            return StoreResult(OperationStatus.UNAVAILABLE, message=str(exc))

    def record_curation_generation_started(
        self,
        *,
        session_id: str,
        lease_token: str,
        boot_id: str,
        runtime_name: str | None = None,
        model_id: str | None = None,
        serve_profile_id: str | None = None,
        accelerator: str | None = None,
    ) -> StoreResult[CurationJob]:
        try:
            validate_job_identity(session_id)
            validate_worker_identity(lease_token)
            validate_worker_identity(boot_id)
            for label, value in (
                ("runtime_name", runtime_name),
                ("model_id", model_id),
                ("serve_profile_id", serve_profile_id),
                ("accelerator", accelerator),
            ):
                if value is not None:
                    validate_reason(value, label)
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[CurationJob]:
            now = _iso_now()
            cursor = conn.execute(
                """
                UPDATE semantic_curation_job
                SET generation_started_at = ?,
                    updated_at = ?,
                    runtime_name = ?,
                    model_id = ?,
                    serve_profile_id = ?,
                    accelerator = ?
                WHERE session_id = ?
                  AND status = 'processing'
                  AND claim_token = ?
                  AND boot_id = ?
                """,
                (
                    now,
                    now,
                    runtime_name,
                    model_id,
                    serve_profile_id,
                    accelerator,
                    session_id,
                    lease_token,
                    boot_id,
                ),
            )
            if cursor.rowcount != 1:
                return StoreResult(OperationStatus.CONFLICT, message="job claim is stale")
            updated = conn.execute(
                "SELECT * FROM semantic_curation_job WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return StoreResult(OperationStatus.SUCCESS, self._job_record(updated))

        return cast(StoreResult[CurationJob], self._run_write(operation))

    def complete_curation_job(
        self,
        *,
        session_id: str,
        lease_token: str,
        reason: str = "succeeded",
        boot_id: str | None = None,
        generation_duration_ms: float | None = None,
        candidates_proposed: int = 0,
        candidates_rejected: int = 0,
        active_records_created: int = 0,
        pending_review_created: int = 0,
        records_reinforced: int = 0,
        records_superseded_or_disputed: int = 0,
        duplicate_noops: int = 0,
        failure_count: int = 0,
    ) -> StoreResult[CurationJob]:
        try:
            validate_job_identity(session_id)
            validate_worker_identity(lease_token)
            validate_reason(reason)
            if boot_id is not None:
                validate_worker_identity(boot_id)
            result_counts = (
                candidates_proposed,
                candidates_rejected,
                active_records_created,
                pending_review_created,
                records_reinforced,
                records_superseded_or_disputed,
                duplicate_noops,
                failure_count,
            )
            if any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= 3
                for value in result_counts
            ):
                raise CurationValidationError(
                    "curation result counts must be integers between 0 and 3"
                )
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[CurationJob]:
            row = conn.execute(
                "SELECT * FROM semantic_curation_job WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return StoreResult(OperationStatus.NOT_FOUND)
            expected_boot = boot_id or cast(str | None, row["boot_id"])
            if (
                row["status"] != "processing"
                or row["claim_token"] != lease_token
                or row["boot_id"] != expected_boot
            ):
                return StoreResult(OperationStatus.CONFLICT, message="job claim is stale")
            policy = conn.execute(
                "SELECT automatic_curation_enabled, revision FROM semantic_policy WHERE singleton_id = 1"
            ).fetchone()
            now = _iso_now()
            cancelled = (
                policy is None
                or not bool(policy["automatic_curation_enabled"])
                or int(policy["revision"]) != int(row["policy_revision"])
                or row["cancel_requested_at"] is not None
            )
            status = "cancelled" if cancelled else "succeeded"
            cursor = conn.execute(
                """
                UPDATE semantic_curation_job
                SET status = ?,
                    updated_at = ?,
                    generation_finished_at = ?,
                    generation_duration_ms = ?,
                    persisted_at = CASE WHEN ? = 'succeeded' THEN ? ELSE NULL END,
                    completed_at = CASE WHEN ? = 'succeeded' THEN ? ELSE NULL END,
                    cancelled_at = CASE WHEN ? = 'cancelled' THEN ? ELSE cancelled_at END,
                    cancel_reason = CASE WHEN ? = 'cancelled' THEN 'policy_revision_changed'
                                         ELSE cancel_reason END,
                    last_result_reason = ?,
                    result_candidates_proposed = ?,
                    result_candidates_rejected = ?,
                    result_active_records_created = ?,
                    result_pending_review_created = ?,
                    result_records_reinforced = ?,
                    result_records_superseded_or_disputed = ?,
                    result_duplicate_noops = ?,
                    result_failure_count = ?,
                    boot_id = NULL,
                    claim_token = NULL,
                    claimed_at = NULL,
                    lease_expires_at = NULL
                WHERE session_id = ? AND status = 'processing'
                  AND claim_token = ? AND boot_id = ?
                """,
                (
                    status,
                    now,
                    now,
                    generation_duration_ms,
                    status,
                    now,
                    status,
                    now,
                    status,
                    now,
                    status,
                    reason,
                    candidates_proposed,
                    candidates_rejected,
                    active_records_created,
                    pending_review_created,
                    records_reinforced,
                    records_superseded_or_disputed,
                    duplicate_noops,
                    failure_count,
                    session_id,
                    lease_token,
                    expected_boot,
                ),
            )
            if cursor.rowcount != 1:
                return StoreResult(OperationStatus.CONFLICT, message="job claim is stale")
            updated = conn.execute(
                "SELECT * FROM semantic_curation_job WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return StoreResult(OperationStatus.SUCCESS, self._job_record(updated))

        return cast(StoreResult[CurationJob], self._run_write(operation))

    def fail_curation_job(
        self,
        *,
        session_id: str,
        lease_token: str,
        reason: str,
        error: str,
        boot_id: str | None = None,
        retryable: bool = True,
    ) -> StoreResult[CurationJob]:
        try:
            validate_job_identity(session_id)
            validate_worker_identity(lease_token)
            validate_reason(reason)
            validate_error(error)
            if boot_id is not None:
                validate_worker_identity(boot_id)
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[CurationJob]:
            row = conn.execute(
                "SELECT * FROM semantic_curation_job WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return StoreResult(OperationStatus.NOT_FOUND)
            expected_boot = boot_id or cast(str | None, row["boot_id"])
            if (
                row["status"] != "processing"
                or row["claim_token"] != lease_token
                or row["boot_id"] != expected_boot
            ):
                return StoreResult(OperationStatus.CONFLICT, message="job claim is stale")
            attempts = int(row["attempt_count"])
            terminal = not retryable or attempts >= int(row["max_attempts"])
            now_dt = datetime.now(UTC)
            delay = 60 if attempts == 1 else 300
            next_attempt_at = (
                now_dt if terminal else now_dt + timedelta(seconds=delay)
            ).isoformat()
            status = "failed" if terminal else "retry_wait"
            conn.execute(
                """
                UPDATE semantic_curation_job
                SET status = ?,
                    next_attempt_at = ?,
                    updated_at = ?,
                    generation_finished_at = ?,
                    last_error_code = ?,
                    last_error_detail = ?,
                    last_error_at = ?,
                    boot_id = NULL,
                    claim_token = NULL,
                    claimed_at = NULL,
                    lease_expires_at = NULL
                WHERE session_id = ? AND status = 'processing'
                  AND claim_token = ? AND boot_id = ?
                """,
                (
                    status,
                    next_attempt_at,
                    now_dt.isoformat(),
                    now_dt.isoformat(),
                    reason,
                    error,
                    now_dt.isoformat(),
                    session_id,
                    lease_token,
                    expected_boot,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM semantic_curation_job WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return StoreResult(OperationStatus.SUCCESS, self._job_record(updated))

        return cast(StoreResult[CurationJob], self._run_write(operation))

    def cancel_curation_job(
        self,
        *,
        session_id: str,
        lease_token: str,
        reason: str,
        boot_id: str | None = None,
    ) -> StoreResult[CurationJob]:
        try:
            validate_job_identity(session_id)
            validate_worker_identity(lease_token)
            validate_reason(reason)
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[CurationJob]:
            row = conn.execute(
                "SELECT * FROM semantic_curation_job WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return StoreResult(OperationStatus.NOT_FOUND)
            expected_boot = boot_id or cast(str | None, row["boot_id"])
            now = _iso_now()
            cursor = conn.execute(
                """
                UPDATE semantic_curation_job
                SET status = 'cancelled', updated_at = ?, cancelled_at = ?,
                    cancel_reason = ?, boot_id = NULL, claim_token = NULL,
                    claimed_at = NULL, lease_expires_at = NULL
                WHERE session_id = ? AND status = 'processing'
                  AND claim_token = ? AND boot_id = ?
                """,
                (now, now, reason, session_id, lease_token, expected_boot),
            )
            if cursor.rowcount != 1:
                return StoreResult(OperationStatus.CONFLICT, message="job claim is stale")
            updated = conn.execute(
                "SELECT * FROM semantic_curation_job WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return StoreResult(OperationStatus.SUCCESS, self._job_record(updated))

        return cast(StoreResult[CurationJob], self._run_write(operation))

    def return_curation_job_to_pending(
        self,
        *,
        session_id: str,
        lease_token: str,
        reason: str,
        error: str | None = None,
        boot_id: str | None = None,
    ) -> StoreResult[CurationJob]:
        return self.fail_curation_job(
            session_id=session_id,
            lease_token=lease_token,
            reason=reason,
            error=error or reason,
            boot_id=boot_id,
            retryable=True,
        )

    def mark_curation_job_blocked(
        self,
        *,
        session_id: str,
        reason: str,
    ) -> StoreResult[CurationJob]:
        try:
            validate_job_identity(session_id)
            validate_reason(reason)
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[CurationJob]:
            now = _iso_now()
            cursor = conn.execute(
                """
                UPDATE semantic_curation_job
                SET blocked_reason = ?, updated_at = ?
                    , last_result_reason = ?
                WHERE session_id = ? AND status IN ('pending', 'retry_wait')
                """,
                (reason, now, reason, session_id),
            )
            if cursor.rowcount != 1:
                return StoreResult(OperationStatus.CONFLICT, message="job is not queueable")
            row = conn.execute(
                "SELECT * FROM semantic_curation_job WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return StoreResult(OperationStatus.SUCCESS, self._job_record(row))

        return cast(StoreResult[CurationJob], self._run_write(operation))

    def recover_stale_curation_jobs(
        self,
        *,
        recovered_at: str | None = None,
        reason: str = "stale_lease_recovered",
        current_boot_id: str | None = None,
    ) -> StoreResult[int]:
        try:
            cutoff_input = recovered_at or _iso_now()
            require_timestamp(cutoff_input, "recovered_at")
            cutoff = datetime.fromisoformat(cutoff_input).astimezone(UTC).isoformat()
            validate_reason(reason)
            if current_boot_id is not None:
                validate_worker_identity(current_boot_id)
        except CurationValidationError as exc:
            return StoreResult(OperationStatus.INVALID, message=str(exc))

        def operation(conn: sqlite3.Connection) -> StoreResult[int]:
            policy = conn.execute(
                "SELECT automatic_curation_enabled, revision FROM semantic_policy WHERE singleton_id = 1"
            ).fetchone()
            processing_rows = conn.execute(
                """
                SELECT * FROM semantic_curation_job
                WHERE status = 'processing'
                  AND ((? IS NOT NULL AND boot_id <> ?) OR lease_expires_at <= ?)
                """,
                (current_boot_id, current_boot_id, cutoff),
            ).fetchall()
            recovered = 0
            for row in processing_rows:
                policy_changed = (
                    policy is None
                    or not bool(policy["automatic_curation_enabled"])
                    or int(policy["revision"]) != int(row["policy_revision"])
                    or row["cancel_requested_at"] is not None
                )
                attempts = int(row["attempt_count"])
                if policy_changed:
                    status = "cancelled"
                elif attempts >= int(row["max_attempts"]):
                    status = "failed"
                else:
                    status = "retry_wait"
                now = cutoff
                conn.execute(
                    """
                    UPDATE semantic_curation_job
                    SET status = ?, next_attempt_at = ?, updated_at = ?,
                        cancelled_at = CASE WHEN ? = 'cancelled' THEN ? ELSE cancelled_at END,
                        cancel_reason = CASE WHEN ? = 'cancelled' THEN 'policy_revision_changed'
                                             ELSE cancel_reason END,
                        last_error_code = CASE WHEN ? <> 'cancelled' THEN ? ELSE last_error_code END,
                        last_error_detail = CASE WHEN ? <> 'cancelled'
                                                 THEN 'previous process ended during curation'
                                                 ELSE last_error_detail END,
                        last_error_at = CASE WHEN ? <> 'cancelled' THEN ? ELSE last_error_at END,
                        boot_id = NULL, claim_token = NULL,
                        claimed_at = NULL, lease_expires_at = NULL
                    WHERE session_id = ? AND status = 'processing'
                    """,
                    (
                        status,
                        now,
                        now,
                        status,
                        now,
                        status,
                        status,
                        reason,
                        status,
                        status,
                        now,
                        row["session_id"],
                    ),
                )
                recovered += 1
            return StoreResult(OperationStatus.SUCCESS, recovered)

        return cast(StoreResult[int], self._run_write(operation))

    def write_entry(self, entry: SemanticEntry) -> str | None:
        """Writes a fully constructed SemanticEntry to the store, performing deduplication on text_hash."""
        if not self._schema_ready:
            return None

        def operation(conn: sqlite3.Connection) -> StoreResult[str]:
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
                    "SELECT fact_id FROM semantic_fact WHERE text_hash = ?",
                    (entry.text_hash,),
                ).fetchone()
                if existing is None:
                    return StoreResult(OperationStatus.UNAVAILABLE)
                return StoreResult(
                    OperationStatus.NO_CHANGE,
                    cast(str, existing["fact_id"]),
                )

            rowid = cursor.lastrowid
            if self.supports_fts and rowid is not None:
                # A failed FTS insert must abort the enclosing transaction so the
                # fact row and its FTS row commit together or not at all.
                conn.execute(
                    "INSERT INTO semantic_fact_fts (rowid, text) VALUES (?, ?)",
                    (rowid, entry.text),
                )
            self._increment_content_revision(conn)
            return StoreResult(OperationStatus.SUCCESS, entry.fact_id)

        result = self._run_write(operation)
        return cast(str | None, result.value) if result.succeeded else None

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
                    return self._retrieval_entry(conn, row)
            return None
        except Exception:
            return None

    @staticmethod
    def _retrieval_eligibility_sql(alias: str = "semantic_fact") -> str:
        permitted_kinds = ("fact", *(kind.value for kind in GovernedMemoryKind))
        placeholders = ", ".join(f"'{kind}'" for kind in permitted_kinds)
        return (
            f"{alias}.kind IN ({placeholders}) "
            f"AND {alias}.state = 'active' "
            f"AND ({alias}.expires_at IS NULL "
            f"OR julianday({alias}.expires_at) > julianday(?)) "
            f"AND {alias}.superseded_by_fact_id IS NULL"
        )

    @staticmethod
    def _retrieval_evidence_refs(
        conn: sqlite3.Connection,
        fact_id: str,
        *,
        limit: int = 8,
    ) -> tuple[dict[str, str], ...]:
        rows = conn.execute(
            """
            SELECT
                evidence_id, evidence_authority,
                source_session_id, source_turn_id, source_field,
                action_id, action_surface
            FROM semantic_evidence
            WHERE fact_id = ?
            ORDER BY created_at ASC, evidence_id ASC
            LIMIT ?
            """,
            (fact_id, limit),
        ).fetchall()
        refs: list[dict[str, str]] = []
        for row in rows:
            ref = {
                "evidence_id": cast(str, row["evidence_id"]),
                "evidence_authority": cast(str, row["evidence_authority"]),
            }
            for field in (
                "source_session_id",
                "source_turn_id",
                "source_field",
                "action_id",
                "action_surface",
            ):
                value = cast(str | None, row[field])
                if value is not None:
                    ref[field] = value
            refs.append(ref)
        return tuple(refs)

    @classmethod
    def _retrieval_entry(
        cls,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> SemanticEntry:
        evidence_refs = cls._retrieval_evidence_refs(
            conn,
            cast(str, row["fact_id"]),
        )
        if (
            not evidence_refs
            and row["source_session_id"] is not None
            and row["source_turn_id"] is not None
            and row["source_field"] is not None
        ):
            evidence_refs = (
                {
                    "evidence_id": f"legacy:{cast(str, row['fact_id'])}",
                    "evidence_authority": cast(str, row["evidence_authority"]),
                    "source_session_id": cast(str, row["source_session_id"]),
                    "source_turn_id": cast(str, row["source_turn_id"]),
                    "source_field": cast(str, row["source_field"]),
                },
            )
        return SemanticEntry.from_row(
            row,
            evidence_refs=evidence_refs,
        )

    def search_lexical(self, query: str, n: int = 5) -> list[SemanticEntry]:
        """Performs lexical query match using FTS5 (or falling back to LIKE if FTS5 fails or is disabled)."""
        if not self._schema_ready:
            return []
        try:
            results: list[SemanticEntry] = []
            if not query.strip():
                return []

            with self._get_conn() as conn:
                now = _iso_now()
                eligibility = self._retrieval_eligibility_sql("f")
                if self.supports_fts:
                    try:
                        rows = conn.execute(
                            f"""
                            SELECT f.* FROM semantic_fact f
                            JOIN semantic_fact_fts ON f.rowid = semantic_fact_fts.rowid
                            WHERE semantic_fact_fts.text MATCH ?
                              AND {eligibility}
                            ORDER BY bm25(semantic_fact_fts) ASC, f.fact_id ASC
                            LIMIT ?
                            """,
                            (query, now, n),
                        ).fetchall()
                        for row in rows:
                            results.append(self._retrieval_entry(conn, row))
                        return results
                    except sqlite3.OperationalError:
                        # If FTS syntax is invalid or search failed, fallback to LIKE
                        pass

                # Fallback to standard LIKE
                like_pattern = f"%{query}%"
                rows = conn.execute(
                    f"""
                    SELECT f.* FROM semantic_fact f
                    WHERE f.text LIKE ?
                      AND {eligibility}
                    ORDER BY f.fact_id ASC
                    LIMIT ?
                    """,
                    (like_pattern, now, n),
                ).fetchall()
                for row in rows:
                    results.append(self._retrieval_entry(conn, row))
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
                eligibility = self._retrieval_eligibility_sql("f")
                rows = conn.execute(
                    f"""
                    SELECT f.*
                    FROM semantic_fact f
                    WHERE {eligibility}
                    ORDER BY f.fact_id ASC
                    """,
                    (_iso_now(),),
                ).fetchall()
                for row in rows:
                    entry = self._retrieval_entry(conn, row)
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

            candidates.sort(key=lambda item: (-item[1], item[0].fact_id))
            return candidates[:n]
        except Exception:
            return []
