from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Protocol

import numpy as np

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.personality.schema import PersonalityProfile


@dataclass(frozen=True, slots=True)
class SessionStatus:
    session_id: str | None
    active: bool
    state: str
    turn_count: int
    last_transcript: str | None = None
    last_response: str | None = None
    failure_reason: str | None = None
    invocation_source: str | None = None


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
    active: bool = False
    enabled: bool = False
    monitoring: bool = False
    last_detected: str | None = None
    detection_count: int = 0
    last_error: str | None = None
    last_score: float | None = None
    threshold: float | None = None


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
        self._last_transcript: str | None = None
        self._last_response: str | None = None
        self._failure_reason: str | None = None
        self._invocation_source: str | None = None
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
        self._failure_reason = None
        self._invocation_source = None
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
            last_transcript=self._last_transcript,
            last_response=self._last_response,
            failure_reason=self._failure_reason,
            invocation_source=self._invocation_source,
        )

    def is_session_active(self) -> bool:
        return self._active

    def assert_active_session(self, session_id: str | None = None) -> None:
        if not self._active:
            raise ValueError("no active resident session")
        if session_id is not None and session_id != self._session_manager.session_id:
            raise ValueError("session_id is not active")

    def begin_voice_invocation(self, source: str) -> SessionStatus:
        self._state = ConversationState.LISTENING.value
        self._failure_reason = None
        self._invocation_source = source
        return self.status()

    def mark_voice_state(self, state: ConversationState) -> SessionStatus:
        self._state = state.value
        return self.status()

    def complete_voice_invocation(self, result, *, state: ConversationState | None = None) -> SessionStatus:
        self._last_transcript = result.transcript
        self._last_response = result.response_text
        self._failure_reason = result.failure_reason
        self._state = (state or result.final_state).value
        if self._state != ConversationState.FAILED.value:
            self._state = ConversationState.IDLE.value
        return self.status()

    def fail_voice_invocation(self, reason: str) -> SessionStatus:
        self._failure_reason = reason
        self._state = ConversationState.FAILED.value
        return self.status()

    def configure_wake_status(self, *, provider: str, available: bool, reason: str) -> WakeMonitorStatus:
        if self._wake_status.active or self._wake_status.last_detected is not None or self._wake_status.last_error is not None or "PTT-only fallback" in self._wake_status.reason:
            return self._wake_status
        self._wake_status = WakeMonitorStatus(
            provider=provider,
            available=available,
            reason=reason,
            active=self._wake_status.active,
            enabled=self._wake_status.enabled,
            monitoring=False,
            last_detected=self._wake_status.last_detected,
            detection_count=self._wake_status.detection_count,
            last_error=self._wake_status.last_error,
            last_score=self._wake_status.last_score,
            threshold=self._wake_status.threshold,
        )
        return self._wake_status

    def wake_status(self) -> WakeMonitorStatus:
        return self._wake_status

    def start_wake_monitor(self, *, provider: str, available: bool, reason: str) -> WakeMonitorStatus:
        if not available:
            return self.record_wake_unavailable(reason or "wake runtime is unavailable; PTT-only fallback is active")
        self._wake_status = WakeMonitorStatus(
            provider=provider,
            available=True,
            reason=reason,
            active=True,
            enabled=True,
            monitoring=True,
            last_detected=self._wake_status.last_detected,
            detection_count=self._wake_status.detection_count,
            last_error=None,
            last_score=self._wake_status.last_score,
            threshold=self._wake_status.threshold,
        )
        return self._wake_status

    def stop_wake_monitor(self, reason: str = "wake monitoring stopped; manual PTT is active") -> WakeMonitorStatus:
        self._wake_status = WakeMonitorStatus(
            provider=self._wake_status.provider,
            available=self._wake_status.available,
            reason=reason,
            active=False,
            enabled=False,
            monitoring=False,
            last_detected=self._wake_status.last_detected,
            detection_count=self._wake_status.detection_count,
            last_error=self._wake_status.last_error,
            last_score=self._wake_status.last_score,
            threshold=self._wake_status.threshold,
        )
        return self._wake_status

    def record_wake_detection(self, *, last_score: float | None = None, threshold: float | None = None) -> WakeMonitorStatus:
        self._wake_status = WakeMonitorStatus(
            provider=self._wake_status.provider,
            available=True,
            reason="wake detected",
            active=self._wake_status.active,
            enabled=self._wake_status.enabled,
            monitoring=self._wake_status.monitoring,
            last_detected=datetime.now(timezone.utc).isoformat(),
            detection_count=self._wake_status.detection_count + 1,
            last_error=None,
            last_score=last_score if last_score is not None else self._wake_status.last_score,
            threshold=threshold if threshold is not None else self._wake_status.threshold,
        )
        return self._wake_status

    def record_wake_idle(self, reason: str = "wake listening", *, last_score: float | None = None, threshold: float | None = None) -> WakeMonitorStatus:
        self._wake_status = WakeMonitorStatus(
            provider=self._wake_status.provider,
            available=True,
            reason=reason,
            active=self._wake_status.active,
            enabled=self._wake_status.enabled,
            monitoring=self._wake_status.monitoring,
            last_detected=self._wake_status.last_detected,
            detection_count=self._wake_status.detection_count,
            last_error=None,
            last_score=last_score if last_score is not None else self._wake_status.last_score,
            threshold=threshold if threshold is not None else self._wake_status.threshold,
        )
        return self._wake_status

    def record_wake_unavailable(self, reason: str = "wake runtime is unavailable; PTT-only fallback is active") -> WakeMonitorStatus:
        self._wake_status = WakeMonitorStatus(
            provider=self._wake_status.provider,
            available=False,
            reason=reason,
            active=False,
            enabled=False,
            monitoring=False,
            last_detected=self._wake_status.last_detected,
            detection_count=self._wake_status.detection_count,
            last_error=None,
            last_score=self._wake_status.last_score,
            threshold=self._wake_status.threshold,
        )
        return self._wake_status

    def record_wake_error(
        self,
        error: Exception | str,
        reason: str = "wake detection error; PTT-only fallback is active",
        *,
        last_score: float | None = None,
        threshold: float | None = None,
    ) -> WakeMonitorStatus:
        self._wake_status = WakeMonitorStatus(
            provider=self._wake_status.provider,
            available=False,
            reason=reason,
            active=False,
            enabled=False,
            monitoring=False,
            last_detected=self._wake_status.last_detected,
            detection_count=self._wake_status.detection_count,
            last_error=str(error),
            last_score=last_score if last_score is not None else self._wake_status.last_score,
            threshold=threshold if threshold is not None else self._wake_status.threshold,
        )
        return self._wake_status

    def process_wake_chunk(self, wake_runtime: WakeRuntime, audio_chunk: np.ndarray) -> WakeMonitorStatus:
        return self.process_wake_chunks(wake_runtime, [audio_chunk])

    def process_wake_chunks(self, wake_runtime: WakeRuntime, audio_chunks: Iterable[np.ndarray]) -> WakeMonitorStatus:
        if not wake_runtime.is_available():
            return self.record_wake_unavailable()

        self._wake_status = WakeMonitorStatus(
            provider=self._wake_status.provider,
            available=True,
            reason=self._wake_status.reason,
            active=self._wake_status.active,
            enabled=self._wake_status.enabled,
            monitoring=True,
            last_detected=self._wake_status.last_detected,
            detection_count=self._wake_status.detection_count,
            last_error=None,
            last_score=self._wake_status.last_score,
            threshold=self._wake_status.threshold,
        )
        try:
            for chunk in audio_chunks:
                if wake_runtime.detect(np.asarray(chunk)):
                    self.record_wake_detection(
                        last_score=getattr(wake_runtime, "last_score", None),
                        threshold=getattr(wake_runtime, "threshold", None),
                    )
                    self._wake_status = WakeMonitorStatus(
                        provider=self._wake_status.provider,
                        available=self._wake_status.available,
                        reason=self._wake_status.reason,
                        active=self._wake_status.active,
                        enabled=self._wake_status.enabled,
                        monitoring=False,
                        last_detected=self._wake_status.last_detected,
                        detection_count=self._wake_status.detection_count,
                        last_error=self._wake_status.last_error,
                        last_score=self._wake_status.last_score,
                        threshold=self._wake_status.threshold,
                    )
                    return self._wake_status
                self.record_wake_idle(
                    last_score=getattr(wake_runtime, "last_score", None),
                    threshold=getattr(wake_runtime, "threshold", None),
                )
        except Exception as exc:
            return self.record_wake_error(
                exc,
                last_score=getattr(wake_runtime, "last_score", None),
                threshold=getattr(wake_runtime, "threshold", None),
            )

        self._wake_status = WakeMonitorStatus(
            provider=self._wake_status.provider,
            available=True,
            reason="wake not detected",
            active=self._wake_status.active,
            enabled=self._wake_status.enabled,
            monitoring=False,
            last_detected=self._wake_status.last_detected,
            detection_count=self._wake_status.detection_count,
            last_error=None,
            last_score=self._wake_status.last_score,
            threshold=self._wake_status.threshold,
        )
        return self._wake_status
