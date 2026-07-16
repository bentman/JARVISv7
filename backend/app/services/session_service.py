from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import numpy as np
from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.core.paths import DATA_DIR
from backend.app.personality.schema import PersonalityProfile
from backend.app.services.wake_status import WakeMonitorStatus, WakeRuntime, WakeStatusStore
from backend.app.memory.semantic import SemanticMemory


@dataclass(frozen=True, slots=True)
class LatestTurnStatus:
    turn_id: str
    session_id: str
    input_modality: str
    final_state: str
    failure_reason: str | None = None
    degraded_reason: str | None = None
    tts_output_device: str | None = None
    raw_audio_path: str | None = None
    artifact_path: str | None = None
    runtime_context: dict[str, object] | None = None
    phase_durations_ms: dict[str, float] | None = None
    failure_phase: str | None = None


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
    tts_output_device: str | None = None
    latest_turn: LatestTurnStatus | None = None
    voice_capture_diagnostics: dict[str, object] | None = None
    failure_phase: str | None = None


@dataclass(frozen=True, slots=True)
class SessionCloseResult:
    session_id: str
    closed: bool
    artifact_path: Path


class SessionService:
    _VOICE_TRANSIENT_STATES: ClassVar[set[ConversationState]] = {
        ConversationState.TRANSCRIBING,
        ConversationState.REASONING,
        ConversationState.ACTING,
        ConversationState.RESPONDING,
        ConversationState.SPEAKING,
    }

    def __init__(
        self,
        *,
        session_manager: SessionManager,
        engine: TurnEngine,
        engine_factory: Callable[[SessionManager], TurnEngine],
        active: bool = True,
        personality: PersonalityProfile | None = None,
        semantic_memory: SemanticMemory | None = None,
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
        self._tts_output_device: str | None = None
        self._voice_capture_diagnostics: dict[str, object] | None = None
        self._failure_phase: str | None = None
        self._semantic_memory = semantic_memory
        self._wake_status_store = WakeStatusStore(
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

    def replace_engine(self, engine: TurnEngine) -> TurnEngine:
        engine.personality = self._personality
        self._engine = engine
        return self._engine

    def active_personality(self) -> PersonalityProfile:
        return self._personality

    def select_personality(self, profile: PersonalityProfile) -> PersonalityProfile:
        previous_profile_id = self._personality.profile_id
        self._personality = profile
        self._engine.personality = profile
        if profile.profile_id != previous_profile_id:
            self._session_manager.mark_profile_switch(profile.profile_id)
        return self._personality

    def start_session(self, client_id: str | None = None) -> SessionStatus:
        _ = client_id
        self._session_manager = SessionManager()
        self._engine = self._engine_factory(self._session_manager)
        self._engine.personality = self._personality
        self._active = True
        self._state = "IDLE"
        self._failure_reason = None
        self._failure_phase = None
        self._invocation_source = None
        return self.status()

    def end_session(self, session_id: str, final_state: str = "IDLE") -> SessionCloseResult:
        self.assert_active_session(session_id)
        try:
            self._consolidate_semantic_memory()
        except Exception:
            pass
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
            tts_output_device=self._tts_output_device,
            latest_turn=self._latest_turn_status(),
            voice_capture_diagnostics=self._voice_capture_diagnostics,
            failure_phase=self._failure_phase,
        )

    def _latest_turn_status(self) -> LatestTurnStatus | None:
        if not self._session_manager.turn_artifacts:
            return None
        latest = self._session_manager.turn_artifacts[-1]
        degraded_reason = latest.tts_degraded_reason if latest.tts_degraded else None
        turns_base_dir = getattr(self._session_manager, "turns_base_dir", DATA_DIR / "turns")
        artifact_path = _turn_artifact_display_path(
            turns_base_dir,
            latest.session_id,
            latest.turn_id,
        )
        return LatestTurnStatus(
            turn_id=latest.turn_id,
            session_id=latest.session_id,
            input_modality=latest.input_modality,
            final_state=latest.final_state,
            failure_reason=latest.failure_reason,
            degraded_reason=degraded_reason,
            tts_output_device=latest.tts_output_device,
            raw_audio_path=latest.raw_audio_path,
            artifact_path=str(artifact_path),
            runtime_context=dict(latest.runtime_context),
            phase_durations_ms=dict(latest.phase_durations_ms),
            failure_phase=latest.failure_phase,
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
        self._last_transcript = None
        self._last_response = None
        self._failure_reason = None
        self._failure_phase = None
        self._invocation_source = source
        self._tts_output_device = None
        self._voice_capture_diagnostics = None
        return self.status()

    def mark_voice_transient_state(self, state: ConversationState) -> SessionStatus:
        if state not in self._VOICE_TRANSIENT_STATES:
            raise ValueError(f"state is not a transient voice snapshot state: {state.value}")
        self._state = state.value
        return self.status()

    def complete_voice_invocation(self, result, *, state: ConversationState | None = None) -> SessionStatus:
        self._last_transcript = result.transcript
        self._last_response = result.response_text
        self._failure_reason = result.failure_reason
        self._failure_phase = getattr(result, "failure_phase", None)
        self._tts_output_device = getattr(result, "tts_output_device", None)
        self._state = (state or result.final_state).value
        if self._state != ConversationState.FAILED.value:
            self._state = ConversationState.IDLE.value
        return self.status()

    def fail_voice_invocation(self, reason: str) -> SessionStatus:
        self._failure_reason = reason
        self._failure_phase = "capture" if self._voice_capture_diagnostics is not None else "turn-state"
        self._state = ConversationState.FAILED.value
        return self.status()

    def record_voice_capture_diagnostics(
        self,
        *,
        source: str,
        stage: str,
        diagnostics: dict[str, object],
    ) -> SessionStatus:
        self._voice_capture_diagnostics = {
            "source": source,
            "stage": stage,
            **diagnostics,
        }
        return self.status()

    def configure_wake_status(self, *, provider: str, available: bool, reason: str) -> WakeMonitorStatus:
        return self._wake_status_store.configure(provider=provider, available=available, reason=reason)

    def wake_status(self) -> WakeMonitorStatus:
        return self._wake_status_store.status()

    def start_wake_monitor(self, *, provider: str, available: bool, reason: str) -> WakeMonitorStatus:
        return self._wake_status_store.start_monitor(provider=provider, available=available, reason=reason)

    def stop_wake_monitor(self, reason: str = "wake monitoring stopped; manual PTT is active") -> WakeMonitorStatus:
        return self._wake_status_store.stop_monitor(reason)

    def pause_wake_monitor(self, reason: str = "wake monitoring paused for resident voice invocation") -> WakeMonitorStatus:
        return self._wake_status_store.pause_monitor(reason)

    def record_wake_detection(self, *, last_score: float | None = None, threshold: float | None = None) -> WakeMonitorStatus:
        return self._wake_status_store.record_detection(last_score=last_score, threshold=threshold)

    def record_wake_idle(self, reason: str = "wake listening", *, last_score: float | None = None, threshold: float | None = None) -> WakeMonitorStatus:
        return self._wake_status_store.record_idle(reason, last_score=last_score, threshold=threshold)

    def record_wake_unavailable(self, reason: str = "wake runtime is unavailable; PTT-only fallback is active") -> WakeMonitorStatus:
        return self._wake_status_store.record_unavailable(reason)

    def record_wake_error(
        self,
        error: Exception | str,
        reason: str = "wake detection error; PTT-only fallback is active",
        *,
        last_score: float | None = None,
        threshold: float | None = None,
    ) -> WakeMonitorStatus:
        return self._wake_status_store.record_error(error, reason, last_score=last_score, threshold=threshold)

    def process_wake_chunk(self, wake_runtime: WakeRuntime, audio_chunk: np.ndarray) -> WakeMonitorStatus:
        return self._wake_status_store.process_chunk(wake_runtime, audio_chunk)

    def process_wake_chunks(self, wake_runtime: WakeRuntime, audio_chunks: Iterable[np.ndarray]) -> WakeMonitorStatus:
        return self._wake_status_store.process_chunks(wake_runtime, audio_chunks)

    def _consolidate_semantic_memory(self) -> None:
        if self._semantic_memory is None:
            return

        policy = getattr(self._engine, "write_policy", None)
        if policy is None or not getattr(policy, "write_to_semantic_memory", False):
            return
        if not getattr(policy, "semantic_consolidate_on_close", False):
            return

        written_count = 0
        for artifact in self._session_manager.turn_artifacts:
            if getattr(policy, "episodic_skip_failed_turns", True) and artifact.failure_reason is not None:
                continue

            text: str | None = None
            source_field: str | None = None

            if artifact.response_text and artifact.response_text.strip():
                candidate = artifact.response_text.strip()
                if len(candidate) >= getattr(policy, "semantic_min_text_length", 10):
                    text = candidate
                    source_field = "response_text"

            if text is None and artifact.transcript and artifact.transcript.strip():
                candidate = artifact.transcript.strip()
                if len(candidate) >= getattr(policy, "semantic_min_text_length", 10):
                    text = candidate
                    source_field = "transcript"

            if text is not None and source_field is not None:
                if written_count >= getattr(policy, "semantic_max_entries_per_session", 10):
                    break

                from backend.app.memory.semantic import text_to_vector
                q_vec = text_to_vector(text)
                sim_results = self._semantic_memory.search_vector(q_vec, n=1)
                
                # similarity deduplication check
                if sim_results:
                    _best_match, similarity = sim_results[0]
                    if similarity >= getattr(policy, "semantic_similarity_dedupe_threshold", 0.95):
                        continue

                fact_id = self._semantic_memory.write_fact(
                    text=text,
                    vector=q_vec,
                    vectorizer_id="local_hashing_trick_v1_128",
                    source_session_id=artifact.session_id,
                    source_turn_id=artifact.turn_id,
                    source_field=source_field,
                    kind="fact",
                )
                if fact_id is not None:
                    written_count += 1


def _turn_artifact_display_path(turns_base_dir: Path, session_id: str, turn_id: str) -> Path:
    artifact_path = turns_base_dir / session_id / f"{turn_id}.json"
    try:
        if turns_base_dir.resolve() == (DATA_DIR / "turns").resolve():
            return Path("data") / "turns" / session_id / f"{turn_id}.json"
    except OSError:
        pass
    return artifact_path
