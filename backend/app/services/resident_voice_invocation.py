from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.states import ConversationState
from backend.app.services import voice_service
from backend.app.services.session_service import SessionService, SessionStatus


AudioCapture = Callable[[], tuple[np.ndarray, int]]
EngineProvider = Callable[[], TurnEngine]


@dataclass(frozen=True, slots=True)
class ResidentInvocationRequest:
    source: str


class ResidentVoiceInvocationService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        engine_provider: EngineProvider,
        audio_capture: AudioCapture | None = None,
    ) -> None:
        self._session_service = session_service
        self._engine_provider = engine_provider
        self._audio_capture = audio_capture or (lambda: voice_service.capture_audio(duration_s=3.0))
        self._queue: queue.Queue[ResidentInvocationRequest] = queue.Queue()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def enqueue(self, source: str) -> SessionStatus:
        normalized_source = source.strip().lower() or "voice"
        self._queue.put(ResidentInvocationRequest(source=normalized_source))
        self._ensure_worker()
        return self._session_service.status()

    def ptt(self) -> SessionStatus:
        return self.enqueue("ptt")

    def status(self) -> SessionStatus:
        return self._session_service.status()

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._run, name="jarvis-resident-voice", daemon=True)
            self._worker.start()

    def _run(self) -> None:
        while True:
            try:
                request = self._queue.get_nowait()
            except queue.Empty:
                with self._lock:
                    if self._worker is threading.current_thread():
                        self._worker = None
                return
            try:
                self._invoke(request.source)
            finally:
                self._queue.task_done()

    def _invoke(self, source: str) -> None:
        try:
            self._session_service.begin_voice_invocation(source)
            audio, sample_rate = self._audio_capture()
            self._session_service.mark_voice_state(ConversationState.TRANSCRIBING)
            result = self._engine_provider().run_voice_turn(audio, sample_rate)
            if result.failure_reason:
                self._session_service.complete_voice_invocation(result, state=ConversationState.FAILED)
                return
            self._session_service.mark_voice_state(ConversationState.RESPONDING)
            if result.response_text:
                self._session_service.mark_voice_state(ConversationState.SPEAKING)
            self._session_service.complete_voice_invocation(result, state=result.final_state)
        except Exception as exc:
            self._session_service.fail_voice_invocation(str(exc))
