from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.actions.boundaries import ActionOperation
from backend.app.services.capability_service import utc_now_iso
from backend.app.services.llm_provider_profiles import LLMProviderProfileStore


class ExtensionRuns:
    def __init__(self, db_path: Path | None = None) -> None:
        self.store = LLMProviderProfileStore(db_path=db_path)
        self._lock = threading.RLock()
        self._answers: dict[str, tuple[threading.Event, dict[str, Any]]] = {}
        for row in self.list():
            if row["status"] in {"running", "awaiting_input", "awaiting_approval"}:
                self.update(row["run_id"], status="interrupted", request=None)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.store.db_path, timeout=10)

    def create(self, extension_id: str, operation: ActionOperation) -> str:
        run_id = uuid4().hex
        payload = {
            "run_id": run_id, "extension_id": extension_id,
            "session_id": operation.session_id, "turn_id": operation.turn_id,
            "proposal_id": operation.proposal_id, "status": "running",
            "started_at": utc_now_iso(), "updated_at": utc_now_iso(),
            "events": [], "request": None,
        }
        with self._connect() as connection:
            connection.execute("INSERT INTO extension_run VALUES (?, ?)", (run_id, json.dumps(payload)))
        return run_id

    def read(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM extension_run WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("unknown extension run")
        return json.loads(row[0])

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM extension_run ORDER BY rowid DESC LIMIT 100").fetchall()
        return [json.loads(row[0]) for row in rows]

    def update(self, run_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            payload = self.read(run_id)
            payload.update(fields, updated_at=utc_now_iso())
            with self._connect() as connection:
                connection.execute("UPDATE extension_run SET payload = ? WHERE run_id = ?", (json.dumps(payload), run_id))
            return payload

    def event(self, run_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            payload = self.read(run_id)
            encoded = json.dumps(event, default=str)
            if len(encoded.encode()) > 4000:
                event = {"type": "output_truncated"}
            self.update(run_id, events=(payload["events"] + [event])[-40:])

    def request(self, run_id: str, request: dict[str, Any], operation: ActionOperation) -> dict[str, Any]:
        if not operation.interactive_input_allowed:
            raise ValueError(
                "this extension needs operator input; run it from the Extensions panel"
            )
        request_id = uuid4().hex
        signal = threading.Event()
        answer: dict[str, Any] = {}
        with self._lock:
            self._answers[request_id] = (signal, answer)
        self.update(run_id, status="awaiting_input", request={**request, "request_id": request_id})
        try:
            while not signal.wait(0.05):
                operation.check()
            operation.check()
            return dict(answer)
        finally:
            with self._lock:
                self._answers.pop(request_id, None)
            self.update(run_id, status="running", request=None)

    def answer(self, run_id: str, request_id: str, answer: dict[str, Any]) -> None:
        with self._lock:
            request = self.read(run_id).get("request")
            if not request or request["request_id"] != request_id or request_id not in self._answers:
                raise ValueError("request is no longer pending")
            signal, result = self._answers[request_id]
            if signal.is_set():
                raise ValueError("request already answered")
            result.update(answer)
            signal.set()


class McpSnapshots:
    """Durable MCP discovery snapshots.

    Discovered tools, resources, and prompts become capability-backed operations, so losing
    them on restart would silently retract capabilities an operator had already discovered.
    Health is not stored: it is derived per read so a stale row cannot claim to be healthy.
    """

    def __init__(self, db_path: Path | None = None, store: Any = None) -> None:
        self.store = store or LLMProviderProfileStore(db_path=db_path)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.store.db_path, timeout=10)

    def save(self, extension_id: str, snapshot: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO mcp_discovery_snapshot VALUES (?, ?, ?) "
                "ON CONFLICT(extension_id) DO UPDATE SET payload = excluded.payload, "
                "discovered_at = excluded.discovered_at",
                (extension_id, json.dumps(snapshot), utc_now_iso()),
            )

    def all(self) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT extension_id, payload, discovered_at FROM mcp_discovery_snapshot"
            ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for extension_id, payload, discovered_at in rows:
            snapshot = json.loads(payload)
            snapshot["discovered_at"] = discovered_at
            # The connection has not been contacted in this process, so the stored health
            # is history, not a live claim. The operations remain usable; readiness is
            # re-established by the next discovery.
            snapshot["health"] = "unknown"
            result[extension_id] = snapshot
        return result

    def delete(self, extension_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM mcp_discovery_snapshot WHERE extension_id = ?", (extension_id,)
            )
