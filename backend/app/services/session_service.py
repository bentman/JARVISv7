from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager


@dataclass(frozen=True, slots=True)
class SessionStatus:
    session_id: str | None
    active: bool
    state: str
    turn_count: int


@dataclass(frozen=True, slots=True)
class SessionCloseResult:
    session_id: str
    closed: bool
    artifact_path: Path


class SessionService:
    def __init__(
        self,
        *,
        session_manager: SessionManager,
        engine: TurnEngine,
        engine_factory: Callable[[SessionManager], TurnEngine],
        active: bool = True,
    ) -> None:
        self._session_manager = session_manager
        self._engine = engine
        self._engine_factory = engine_factory
        self._active = active
        self._state = "IDLE"

    @property
    def session_manager(self) -> SessionManager:
        return self._session_manager

    def engine(self) -> TurnEngine:
        if not self._active:
            raise RuntimeError("no active resident session")
        return self._engine

    def start_session(self, client_id: str | None = None) -> SessionStatus:
        _ = client_id
        self._session_manager = SessionManager()
        self._engine = self._engine_factory(self._session_manager)
        self._active = True
        self._state = "IDLE"
        return self.status()

    def end_session(self, session_id: str, final_state: str = "IDLE") -> SessionCloseResult:
        self.assert_active_session(session_id)
        artifact_path = self._session_manager.close_session(final_state)
        self._active = False
        self._state = final_state
        return SessionCloseResult(session_id=self._session_manager.session_id, closed=True, artifact_path=artifact_path)

    def status(self) -> SessionStatus:
        return SessionStatus(
            session_id=self._session_manager.session_id if self._active else None,
            active=self._active,
            state=self._state,
            turn_count=len(self._session_manager.turn_artifacts),
        )

    def is_session_active(self) -> bool:
        return self._active

    def assert_active_session(self, session_id: str | None = None) -> None:
        if not self._active:
            raise ValueError("no active resident session")
        if session_id is not None and session_id != self._session_manager.session_id:
            raise ValueError("session_id is not active")
