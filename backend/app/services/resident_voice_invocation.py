from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.realtime.events import RealtimeEvent
from backend.app.conversation.realtime.session import RealtimeConversationSession
from backend.app.runtimes.vad import EnergyVADRuntime
from backend.app.services import voice_service
from backend.app.services.audio_stream import AudioChunk, ResidentAudioStream
from backend.app.services.session_service import SessionService, SessionStatus
from backend.app.services.utterance_segmenter import UtteranceSegmenter


AudioCapture = Callable[[], tuple[np.ndarray, int]]
EngineProvider = Callable[[], TurnEngine]
BeforeInvocation = Callable[[], object]
AfterInvocation = Callable[[object], object]
NO_SPEECH_PTT_REASON = "No speech detected during PTT"
RESIDENT_VOICE_MODES = frozenset({"ptt-only", "ptt+wake", "hands-free", "continuous"})


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
        resident_stream: ResidentAudioStream | None = None,
        utterance_segmenter: UtteranceSegmenter | None = None,
        before_invocation: BeforeInvocation | None = None,
        after_invocation: AfterInvocation | None = None,
    ) -> None:
        self._session_service = session_service
        self._engine_provider = engine_provider
        self._audio_capture = audio_capture or (lambda: voice_service.capture_audio(duration_s=3.0))
        self._resident_stream = resident_stream
        self._utterance_segmenter = utterance_segmenter
        self._before_invocation = before_invocation
        self._after_invocation = after_invocation
        self._queue: queue.Queue[ResidentInvocationRequest] = queue.Queue()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._last_realtime_events: tuple[RealtimeEvent, ...] = ()
        self._mode = "ptt+wake"

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

    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> str:
        normalized = mode.strip().lower()
        if normalized not in RESIDENT_VOICE_MODES:
            raise ValueError(f"unsupported resident voice mode: {mode}")
        self._mode = normalized
        return self._mode

    def last_realtime_events(self) -> tuple[RealtimeEvent, ...]:
        return self._last_realtime_events

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
        realtime_session: RealtimeConversationSession | None = None
        try:
            if self._before_invocation is not None:
                hook_state = self._before_invocation()
            request = self._resolve_ptt_audio(request)
            if request.source == "wake" and request.audio is not None and request.audio.size == 0:
                self._session_service.begin_voice_invocation(request.source)
                self._session_service.fail_voice_invocation("No speech detected after wake")
                return
            if request.source == "ptt" and request.audio is not None and request.audio.size == 0:
                self._session_service.begin_voice_invocation(request.source)
                self._session_service.fail_voice_invocation(NO_SPEECH_PTT_REASON)
                return
            realtime_session = RealtimeConversationSession(
                session_service=self._session_service,
                engine_provider=self._engine_provider,
            )
            result = realtime_session.run_voice_invocation(
                source=request.source,
                audio=request.audio,
                sample_rate=request.sample_rate,
                audio_capture=self._audio_capture,
            )
            if result.interrupted and request.source != "barge_in":
                self._enqueue_barge_in_follow_up()
            if result.failure_reason:
                return
        except Exception as exc:
            self._session_service.fail_voice_invocation(str(exc))
        finally:
            if realtime_session is not None:
                self._last_realtime_events = tuple(realtime_session.ledger.events)
            if self._after_invocation is not None:
                try:
                    self._after_invocation(hook_state)
                except Exception:
                    pass

    def _resolve_ptt_audio(self, request: ResidentInvocationRequest) -> ResidentInvocationRequest:
        if request.source != "ptt" or request.audio is not None:
            return request
        return self._capture_streamed_request(request)

    def _capture_streamed_request(self, request: ResidentInvocationRequest) -> ResidentInvocationRequest:
        if self._resident_stream is None or self._utterance_segmenter is None:
            return request
        if not self._resident_stream.status().running:
            return request

        subscriber = self._resident_stream.subscribe()
        try:
            segment = self._utterance_segmenter.capture(_subscriber_chunks(subscriber))
        finally:
            self._resident_stream.unsubscribe(subscriber)

        if not segment.speech_started or segment.audio.size == 0:
            return ResidentInvocationRequest(source=request.source, audio=np.array([], dtype=np.float32), sample_rate=segment.sample_rate)
        return ResidentInvocationRequest(source=request.source, audio=segment.audio, sample_rate=segment.sample_rate)

    def _enqueue_barge_in_follow_up(self) -> None:
        request = self._capture_streamed_request(ResidentInvocationRequest(source="barge_in"))
        if request.audio is None or request.audio.size == 0 or request.sample_rate is None:
            return
        self.enqueue("barge_in", request.audio, request.sample_rate)


def _subscriber_chunks(subscriber: queue.Queue[AudioChunk]) -> Iterable[AudioChunk]:
    while True:
        yield subscriber.get(timeout=0.1)


def default_utterance_segmenter() -> UtteranceSegmenter:
    return UtteranceSegmenter(vad=EnergyVADRuntime())


def resident_interruption_chunks(resident_stream: ResidentAudioStream | None) -> Iterable[np.ndarray] | None:
    if resident_stream is None or not resident_stream.status().running:
        return None
    return _resident_interruption_chunks(resident_stream)


def _resident_interruption_chunks(resident_stream: ResidentAudioStream) -> Iterable[np.ndarray]:
    subscriber = resident_stream.subscribe()
    try:
        while resident_stream.status().running:
            chunk = subscriber.get(timeout=0.1)
            yield np.asarray(chunk.samples, dtype=np.float32).reshape(-1)
    finally:
        resident_stream.unsubscribe(subscriber)
