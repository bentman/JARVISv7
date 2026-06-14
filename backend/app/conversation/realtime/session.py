from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

import numpy as np

from backend.app.conversation.engine import TurnEngine, TurnResult
from backend.app.conversation.states import ConversationState
from backend.app.conversation.realtime.events import RealtimeEventType
from backend.app.conversation.realtime.interruption import record_interruption_boundary
from backend.app.conversation.realtime.ledger import RealtimeEventLedger
from backend.app.conversation.realtime.response_queue import RealtimeResponseQueue
from backend.app.conversation.realtime.turn_taking import has_committable_audio
from backend.app.services.session_service import SessionService


class AudioCapture(Protocol):
    def __call__(self) -> tuple[np.ndarray, int]:
        ...


EngineProvider = Callable[[], TurnEngine]

EMPTY_TRANSCRIPT_REASON = "STT returned empty transcript"
WAKE_NO_SPEECH_REASON = "No speech detected after wake"


class RealtimeConversationSession:
    def __init__(
        self,
        *,
        session_service: SessionService,
        engine_provider: EngineProvider,
        ledger: RealtimeEventLedger | None = None,
        response_queue: RealtimeResponseQueue | None = None,
    ) -> None:
        self._session_service = session_service
        self._engine_provider = engine_provider
        session_id = session_service.status().session_id
        if session_id is None:
            raise ValueError("realtime session requires an active resident session")
        self.ledger = ledger or RealtimeEventLedger(session_id=session_id)
        self.response_queue = response_queue or RealtimeResponseQueue()

    def run_voice_invocation(
        self,
        *,
        source: str,
        audio_capture: AudioCapture,
        audio: np.ndarray | None = None,
        sample_rate: int | None = None,
    ) -> TurnResult:
        source = source.strip().lower() or "voice"
        self.ledger.append(RealtimeEventType.SESSION_ACTIVE, source=source, state=ConversationState.IDLE)
        self.ledger.append(RealtimeEventType.INVOCATION_RECEIVED, source=source)
        self._session_service.begin_voice_invocation(source)
        try:
            if not has_committable_audio(audio, sample_rate):
                self.ledger.append(RealtimeEventType.AUDIO_CAPTURE_STARTED, source=source, state=ConversationState.LISTENING)
                audio, sample_rate = audio_capture()
            self.ledger.append(
                RealtimeEventType.AUDIO_CAPTURE_COMPLETED,
                source=source,
                state=ConversationState.LISTENING,
                metadata={"sample_rate": sample_rate, "audio_frames": int(np.asarray(audio).size)},
            )
            self.ledger.append(RealtimeEventType.USER_TURN_COMMITTED, source=source)
            self._session_service.mark_voice_state(ConversationState.TRANSCRIBING)
            self.ledger.append(RealtimeEventType.TRANSCRIBING, source=source, state=ConversationState.TRANSCRIBING)
            self._session_service.mark_voice_state(ConversationState.REASONING)
            self.ledger.append(RealtimeEventType.REASONING, source=source, state=ConversationState.REASONING)
            result = self._engine_provider().run_voice_turn(audio, sample_rate)
            if source == "wake" and result.failure_reason == EMPTY_TRANSCRIPT_REASON:
                result = replace(result, failure_reason=WAKE_NO_SPEECH_REASON)
            self._record_result(source, result)
            return result
        except Exception as exc:
            self._session_service.fail_voice_invocation(str(exc))
            self.ledger.append(RealtimeEventType.SESSION_FAILED, source=source, state=ConversationState.FAILED, metadata={"reason": str(exc)})
            raise

    def _record_result(self, source: str, result: TurnResult) -> None:
        if result.failure_reason:
            self._session_service.complete_voice_invocation(result, state=ConversationState.FAILED)
            self.ledger.append(
                RealtimeEventType.SESSION_FAILED,
                source=source,
                turn_id=result.turn_id,
                state=ConversationState.FAILED,
                metadata={"reason": result.failure_reason},
            )
            return

        self._session_service.mark_voice_state(ConversationState.RESPONDING)
        self.ledger.append(RealtimeEventType.RESPONDING, source=source, turn_id=result.turn_id, state=ConversationState.RESPONDING)
        self.response_queue.enqueue(result.response_text)
        if result.response_text:
            self._session_service.mark_voice_state(ConversationState.SPEAKING)
            self.ledger.append(RealtimeEventType.ASSISTANT_SPEECH_STARTED, source=source, turn_id=result.turn_id, state=ConversationState.SPEAKING)
            self.ledger.append(RealtimeEventType.SPEAKING, source=source, turn_id=result.turn_id, state=ConversationState.SPEAKING)
        if result.interrupted:
            record_interruption_boundary(
                self.ledger,
                source=source,
                turn_id=result.turn_id,
                interruption_event=result.interruption_events[0] if result.interruption_events else None,
            )
        self._session_service.complete_voice_invocation(result, state=result.final_state)
        self.ledger.append(RealtimeEventType.TURN_COMPLETED, source=source, turn_id=result.turn_id, state=result.final_state)
        self.ledger.append(RealtimeEventType.SESSION_IDLE, source=source, turn_id=result.turn_id, state=ConversationState.IDLE)
