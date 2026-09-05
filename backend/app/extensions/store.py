from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from backend.app.core.paths import DATA_DIR
from backend.app.extensions.contracts import EXTENSION_STATES, ExtensionError


@dataclass(frozen=True, slots=True)
class ExtensionOverlay:
    extension_id: str
    state: str
    trust: str | None
    reason: str | None
    revision: int
    updated_at: str


class ExtensionOverlayConflictError(ExtensionError):
    def __init__(self, message: str, current_revision: int | None = None) -> None:
        super().__init__(message)
        self.current_revision = current_revision


class ExtensionOverlayStore:
    """Persists only what an operator decided and the catalog cannot re-derive."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DATA_DIR / "operator.sqlite"
        self.schema_error: str | None = None
        try:
            # The provider store owns operator.sqlite's schema and migrations.
            from backend.app.services.llm_provider_profiles import LLMProviderProfileStore

            LLMProviderProfileStore(db_path=self.db_path)
        except Exception as exc:
            # A corrupt catalog must degrade with a reason, never kill startup.
            self.schema_error = str(exc)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        return connection

    def available(self) -> bool:
        return self.schema_error is None

    def all_overlays(self) -> dict[str, tuple[str, str | None]]:
        if not self.available():
            return {}
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT extension_id, state, trust FROM extension_overlay"
                ).fetchall()
        except sqlite3.Error:
            return {}
        return {row["extension_id"]: (row["state"], row["trust"]) for row in rows}

    def read(self, extension_id: str) -> ExtensionOverlay | None:
        if not self.available():
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM extension_overlay WHERE extension_id = ?", (extension_id,)
            ).fetchone()
        return _overlay(row) if row is not None else None

    def set_state(
        self,
        *,
        extension_id: str,
        state: str,
        expected_revision: int | None,
        reason: str | None = None,
        trust: str | None = None,
    ) -> ExtensionOverlay:
        if self.schema_error is not None:
            raise ExtensionError(f"extension overlay is unavailable: {self.schema_error}")
        if state not in EXTENSION_STATES:
            raise ExtensionError(f"state must be one of: {', '.join(sorted(EXTENSION_STATES))}")
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM extension_overlay WHERE extension_id = ?", (extension_id,)
            ).fetchone()
            prior_state = row["state"] if row is not None else None
            if row is None:
                if expected_revision not in (None, 0):
                    raise ExtensionOverlayConflictError("extension overlay does not exist yet", None)
                revision = 1
                connection.execute(
                    "INSERT INTO extension_overlay"
                    "(extension_id, state, trust, reason, revision, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (extension_id, state, trust, reason, revision, now),
                )
            else:
                current = int(row["revision"])
                if expected_revision is not None and expected_revision != current:
                    raise ExtensionOverlayConflictError("stale extension overlay revision", current)
                if prior_state == "retired":
                    raise ExtensionError("a retired extension cannot be changed")
                revision = current + 1
                connection.execute(
                    "UPDATE extension_overlay SET state = ?, trust = ?, reason = ?,"
                    " revision = ?, updated_at = ? WHERE extension_id = ? AND revision = ?",
                    (state, trust, reason, revision, now, extension_id, current),
                )
            connection.execute(
                "INSERT INTO extension_event"
                "(extension_id, prior_state, resulting_state, reason, occurred_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (extension_id, prior_state, state, reason, now),
            )
        return ExtensionOverlay(extension_id, state, trust, reason, revision, now)

    def events(self, extension_id: str, *, limit: int = 20) -> list[dict[str, object]]:
        if not self.available():
            return []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT prior_state, resulting_state, reason, occurred_at FROM extension_event"
                " WHERE extension_id = ? ORDER BY event_id DESC LIMIT ?",
                (extension_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]


def _overlay(row: sqlite3.Row) -> ExtensionOverlay:
    return ExtensionOverlay(
        extension_id=row["extension_id"],
        state=row["state"],
        trust=row["trust"],
        reason=row["reason"],
        revision=int(row["revision"]),
        updated_at=row["updated_at"],
    )
