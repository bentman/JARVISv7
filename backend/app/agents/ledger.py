from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from backend.app.conversation.turn_manager import utc_now
from backend.app.core.paths import DATA_DIR
from pydantic import BaseModel, Field

DEFAULT_LEDGER_PATH = DATA_DIR / "agents" / "agent_ledger.sqlite3"
AgentRecordType = Literal[
    "event",
    "plan",
    "outcome",
    "policy_decision",
    "spec_design_requested",
    "spec_created",
    "spec_validated",
    "spec_rejected",
    "spec_policy_denied",
]


class AgentLedgerRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: uuid4().hex)
    trace_id: str
    record_type: AgentRecordType
    payload: dict[str, Any] = Field(default_factory=dict)
    role_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    parent_record_id: str | None = None
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())


class AgentLedger:
    def __init__(self, path: Path = DEFAULT_LEDGER_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def append(self, record: AgentLedgerRecord) -> AgentLedgerRecord:
        payload_json = json.dumps(record.payload, sort_keys=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO agent_ledger_records (
                    record_id, trace_id, session_id, turn_id, role_id, record_type,
                    parent_record_id, created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.trace_id,
                    record.session_id,
                    record.turn_id,
                    record.role_id,
                    record.record_type,
                    record.parent_record_id,
                    record.created_at,
                    payload_json,
                ),
            )
        return record

    def list_by_trace(self, trace_id: str) -> list[AgentLedgerRecord]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT record_id, trace_id, session_id, turn_id, role_id, record_type,
                       parent_record_id, created_at, payload_json
                FROM agent_ledger_records
                WHERE trace_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (trace_id,),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def list_by_turn(self, session_id: str, turn_id: str) -> list[AgentLedgerRecord]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT record_id, trace_id, session_id, turn_id, role_id, record_type,
                       parent_record_id, created_at, payload_json
                FROM agent_ledger_records
                WHERE session_id = ? AND turn_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (session_id, turn_id),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def _initialize(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_ledger_records (
                    record_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    session_id TEXT,
                    turn_id TEXT,
                    role_id TEXT,
                    record_type TEXT NOT NULL,
                    parent_record_id TEXT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_ledger_trace
                ON agent_ledger_records(trace_id, created_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_ledger_turn
                ON agent_ledger_records(session_id, turn_id, created_at)
                """
            )

    def _record_from_row(self, row: tuple[Any, ...]) -> AgentLedgerRecord:
        return AgentLedgerRecord(
            record_id=str(row[0]),
            trace_id=str(row[1]),
            session_id=row[2],
            turn_id=row[3],
            role_id=row[4],
            record_type=row[5],
            parent_record_id=row[6],
            created_at=str(row[7]),
            payload=json.loads(str(row[8])),
        )
