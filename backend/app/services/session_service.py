from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Protocol

import numpy as np

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.personality.schema import PersonalityProfile


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


@dataclass(frozen=True, slots=True)
class WakeMonitorStatus:
    provider: str
    available: bool
    reason: str
    monitoring: bool = False
    last_detected: bool = False
    detection_count: int = 0
    last_error: str | None = None


class WakeRuntime(Protocol):
    def is_available(self) -> bool:
        ...

    def detect(self, audio_chunk: np.ndarray) -> bool:
        ...


class SessionService:
    def __init__(
        self,
        *,
        session_manager: SessionManager,
        engine: TurnEngine,
        engine_factory: Callable[[SessionManager], TurnEngine],
        active: bool = True,
        personality: PersonalityProfile | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._engine = engine
        self._engine_factory = engine_factory
        self._active = active
        self._personality = personality or engine.personality
        self._state = "IDLE"
        self._wake_status = WakeMonitorStatus(
            provider="openwakeword",
            available=False,
            reason="wake readiness has not been configured",
        )

    @property
    def session_manager(self) -> SessionManager:
        return self._session_manager

    def engine(self) -> TurnEngine:
        if not self._active:
            raise RuntimeError("no active resident session")
        return self._engine

    def active_personality(self) -> PersonalityProfile:
        return self._personality

    def select_personality(self, profile: PersonalityProfile) -> PersonalityProfile:
        self._personality = profile
        self._engine.personality = profile
        return self._personality

    def start_session(self, client_id: str | None = None) -> SessionStatus:
        _ = client_id
        self._session_manager = SessionManager()
        self._engine = self._engine_factory(self._session_manager)
        self._engine.personality = self._personality
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

    def configure_wake_status(self, *, provider: str, available: bool, reason: str) -> WakeMonitorStatus:
        if self._wake_status.last_detected or self._wake_status.last_error is not None or "PTT-only fallback" in self._wake_status.reason:
            return self._wake_status
        self._wake_status = WakeMonitorStatus(
            provider=provider,
            available=available,
            reason=reason,
            monitoring=False,
            last_detected=self._wake_status.last_detected,
            detection_count=self._wake_status.detection_count,
            last_error=self._wake_status.last_error,
        )
        return self._wake_status

    def wake_status(self) -> WakeMonitorStatus:
        return self._wake_status

    def process_wake_chunk(self, wake_runtime: WakeRuntime, audio_chunk: np.ndarray) -> WakeMonitorStatus:
        return self.process_wake_chunks(wake_runtime, [audio_chunk])

    def process_wake_chunks(self, wake_runtime: WakeRuntime, audio_chunks: Iterable[np.ndarray]) -> WakeMonitorStatus:
        if not wake_runtime.is_available():
            self._wake_status = WakeMonitorStatus(
                provider=self._wake_status.provider,
                available=False,
                reason="wake runtime is unavailable; PTT-only fallback is active",
                monitoring=False,
                last_detected=False,
                detection_count=self._wake_status.detection_count,
                last_error=None,
            )
            return self._wake_status

        self._wake_status = WakeMonitorStatus(
            provider=self._wake_status.provider,
            available=True,
            reason=self._wake_status.reason,
            monitoring=True,
            last_detected=False,
            detection_count=self._wake_status.detection_count,
            last_error=None,
        )
        try:
            for chunk in audio_chunks:
                if wake_runtime.detect(np.asarray(chunk)):
                    self._wake_status = WakeMonitorStatus(
                        provider=self._wake_status.provider,
                        available=True,
                        reason="wake detected",
                        monitoring=False,
                        last_detected=True,
                        detection_count=self._wake_status.detection_count + 1,
                        last_error=None,
                    )
                    return self._wake_status
        except Exception as exc:
            self._wake_status = WakeMonitorStatus(
                provider=self._wake_status.provider,
                available=False,
                reason="wake detection error; PTT-only fallback is active",
                monitoring=False,
                last_detected=False,
                detection_count=self._wake_status.detection_count,
                last_error=str(exc),
            )
            return self._wake_status

        self._wake_status = WakeMonitorStatus(
            provider=self._wake_status.provider,
            available=True,
            reason="wake not detected",
            monitoring=False,
            last_detected=False,
            detection_count=self._wake_status.detection_count,
            last_error=None,
        )
        return self._wake_status
