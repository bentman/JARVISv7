from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.states import ConversationState
from backend.app.services import voice_service
from backend.app.services.session_service import SessionService, SessionStatus


AudioCapture = Callable[[], tuple[np.ndarray, int]]
EngineProvider = Callable[[], TurnEngine]
BeforeInvocation = Callable[[], object]
AfterInvocation = Callable[[object], object]
EMPTY_TRANSCRIPT_REASON = "STT returned empty transcript"
WAKE_NO_SPEECH_REASON = "No speech detected after wake"


@dataclass(frozen=True, slots=True)
class ResidentInvocationRequest:
    source: str
    audio: np.ndarray | None = None
    sample_rate: int | None = None


class ResidentVoiceInvocationService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        engine_provider: EngineProvider,
        audio_capture: AudioCapture | None = None,
        before_invocation: BeforeInvocation | None = None,
        after_invocation: AfterInvocation | None = None,
    ) -> None:
        self._session_service = session_service
        self._engine_provider = engine_provider
        self._audio_capture = audio_capture or (lambda: voice_service.capture_audio(duration_s=3.0))
        self._before_invocation = before_invocation
        self._after_invocation = after_invocation
        self._queue: queue.Queue[ResidentInvocationRequest] = queue.Queue()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def set_invocation_hooks(self, *, before_invocation: BeforeInvocation, after_invocation: AfterInvocation) -> None:
        self._before_invocation = before_invocation
        self._after_invocation = after_invocation

    def enqueue(
        self,
        source: str,
        audio: np.ndarray | None = None,
        sample_rate: int | None = None,
    ) -> SessionStatus:
        normalized_source = source.strip().lower() or "voice"
        self._queue.put(ResidentInvocationRequest(source=normalized_source, audio=audio, sample_rate=sample_rate))
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
                    if not self._queue.empty():
                        continue
                    if self._worker is threading.current_thread():
                        self._worker = None
                return
            try:
                self._invoke(request)
            finally:
                self._queue.task_done()

    def _invoke(self, request: ResidentInvocationRequest) -> None:
        hook_state: object = None
        try:
            if self._before_invocation is not None:
                hook_state = self._before_invocation()
            self._session_service.begin_voice_invocation(request.source)
            if request.audio is not None and request.sample_rate is not None:
                audio, sample_rate = request.audio, request.sample_rate
            else:
                audio, sample_rate = self._audio_capture()
            self._session_service.mark_voice_state(ConversationState.TRANSCRIBING)
            self._session_service.mark_voice_state(ConversationState.REASONING)
            result = self._engine_provider().run_voice_turn(audio, sample_rate)
            if request.source == "wake" and result.failure_reason == EMPTY_TRANSCRIPT_REASON:
                result = replace(result, failure_reason=WAKE_NO_SPEECH_REASON)
            if result.failure_reason:
                self._session_service.complete_voice_invocation(result, state=ConversationState.FAILED)
                return
            self._session_service.mark_voice_state(ConversationState.RESPONDING)
            if result.response_text:
                self._session_service.mark_voice_state(ConversationState.SPEAKING)
            self._session_service.complete_voice_invocation(result, state=result.final_state)
        except Exception as exc:
            self._session_service.fail_voice_invocation(str(exc))
        finally:
            if self._after_invocation is not None:
                try:
                    self._after_invocation(hook_state)
                except Exception:
                    pass
