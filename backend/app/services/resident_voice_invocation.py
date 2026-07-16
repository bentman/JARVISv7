from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass

import numpy as np
from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.realtime.events import RealtimeEvent
from backend.app.conversation.realtime.session import RealtimeConversationSession
from backend.app.core.settings import load_settings
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
RESIDENT_STREAM_STOPPED_PTT_REASON = "resident audio stream is stopped; start resident voice stream before PTT"
RESIDENT_VOICE_MODES = frozenset({"ptt-only", "ptt+wake", "hands-free", "continuous"})
RESIDENT_FOLLOW_UP_SOURCES = frozenset({"hands_free", "barge_in"})
RESIDENT_BARGE_IN_DISABLED_MODES = frozenset({"ptt-only", "ptt+wake"})


@dataclass(frozen=True, slots=True)
class ResidentInvocationRequest:
    source: str
    audio: np.ndarray | None = None
    sample_rate: int | None = None
    capture_diagnostics: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ResidentFollowUpStatus:
    listening: bool
    source: str | None
    continuous_active: bool


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
        self._mode = "ptt-only"
        self._follow_up_listening = False
        self._follow_up_source: str | None = None
        self._continuous_active = False

    def set_invocation_hooks(self, *, before_invocation: BeforeInvocation, after_invocation: AfterInvocation) -> None:
        self._before_invocation = before_invocation
        self._after_invocation = after_invocation

    def enqueue(
        self,
        source: str,
        audio: np.ndarray | None = None,
        sample_rate: int | None = None,
        capture_diagnostics: dict[str, object] | None = None,
    ) -> SessionStatus:
        normalized_source = source.strip().lower() or "voice"
        self._queue.put(
            ResidentInvocationRequest(
                source=normalized_source,
                audio=audio,
                sample_rate=sample_rate,
                capture_diagnostics=dict(capture_diagnostics) if capture_diagnostics is not None else None,
            )
        )
        self._ensure_worker()
        return self._session_service.status()

    def ptt(self) -> SessionStatus:
        status = self._session_service.begin_voice_invocation("ptt")
        self._queue.put(ResidentInvocationRequest(source="ptt"))
        self._ensure_worker()
        return status

    def status(self) -> SessionStatus:
        return self._session_service.status()

    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> str:
        normalized = mode.strip().lower()
        if normalized not in RESIDENT_VOICE_MODES:
            raise ValueError(f"unsupported resident voice mode: {mode}")
        self._mode = normalized
        self._continuous_active = normalized == "continuous"
        return self._mode

    def last_realtime_events(self) -> tuple[RealtimeEvent, ...]:
        return self._last_realtime_events

    def follow_up_status(self) -> ResidentFollowUpStatus:
        return ResidentFollowUpStatus(
            listening=self._follow_up_listening,
            source=self._follow_up_source,
            continuous_active=self._continuous_active,
        )

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
        engine: TurnEngine | None = None
        previous_barge_in_detector: object = None
        previous_interruption_audio_chunks: object = None
        try:
            if self._before_invocation is not None:
                hook_state = self._before_invocation()
            if self._requires_running_resident_stream(request):
                self._session_service.begin_voice_invocation(request.source)
                self._session_service.fail_voice_invocation(RESIDENT_STREAM_STOPPED_PTT_REASON)
                return
            request = self._resolve_ptt_audio(request)
            if request.source == "wake" and request.audio is not None and request.audio.size == 0:
                self._session_service.begin_voice_invocation(request.source)
                self._record_capture_diagnostics(request)
                self._session_service.fail_voice_invocation("No speech detected after wake")
                return
            if request.source == "ptt" and request.audio is not None and request.audio.size == 0:
                self._session_service.begin_voice_invocation(request.source)
                self._record_capture_diagnostics(request)
                self._session_service.fail_voice_invocation(NO_SPEECH_PTT_REASON)
                return
            engine_provider = self._engine_provider
            if self._mode in RESIDENT_BARGE_IN_DISABLED_MODES:
                engine = self._engine_provider()
                previous_barge_in_detector = getattr(engine, "barge_in_detector", None)
                previous_interruption_audio_chunks = getattr(engine, "interruption_audio_chunks", None)
                engine.barge_in_detector = None
                engine.interruption_audio_chunks = None

                def engine_provider() -> TurnEngine:
                    return engine

            realtime_session = RealtimeConversationSession(
                session_service=self._session_service,
                engine_provider=engine_provider,
            )
            result = realtime_session.run_voice_invocation(
                source=request.source,
                audio=request.audio,
                sample_rate=request.sample_rate,
                audio_capture=self._audio_capture,
                capture_diagnostics=request.capture_diagnostics,
            )
            if result.interrupted and request.source != "barge_in" and self._mode not in RESIDENT_BARGE_IN_DISABLED_MODES:
                self._enqueue_barge_in_follow_up()
            if result.failure_reason:
                return
            self._enqueue_mode_follow_up(request)
        except Exception as exc:
            self._session_service.fail_voice_invocation(str(exc))
        finally:
            if realtime_session is not None:
                self._last_realtime_events = tuple(realtime_session.ledger.events)
            if engine is not None:
                engine.barge_in_detector = previous_barge_in_detector
                engine.interruption_audio_chunks = previous_interruption_audio_chunks
            if self._after_invocation is not None:
                with suppress(Exception):
                    self._after_invocation(hook_state)

    def _resolve_ptt_audio(self, request: ResidentInvocationRequest) -> ResidentInvocationRequest:
        if request.source != "ptt" or request.audio is not None:
            return request
        return self._capture_streamed_request(request)

    def _requires_running_resident_stream(self, request: ResidentInvocationRequest) -> bool:
        if request.source != "ptt" or request.audio is not None:
            return False
        if self._mode == "ptt-only":
            return False
        if self._resident_stream is None or self._utterance_segmenter is None:
            return False
        return not self._resident_stream.is_running()

    def _capture_streamed_request(self, request: ResidentInvocationRequest) -> ResidentInvocationRequest:
        if self._resident_stream is None or self._utterance_segmenter is None:
            return request
        if not self._resident_stream.is_running():
            return request

        subscriber = self._resident_stream.subscribe(include_buffer=request.source == "ptt")
        try:
            capture_started = time.monotonic()
            segment = self._utterance_segmenter.capture(_subscriber_chunks(subscriber, self._resident_stream))
            capture_ms = (time.monotonic() - capture_started) * 1000.0
        finally:
            self._resident_stream.unsubscribe(subscriber)
        diagnostics = _capture_diagnostics_with_timing(segment.diagnostics.as_dict(), capture_ms)
        if not segment.speech_started or segment.audio.size == 0:
            return ResidentInvocationRequest(
                source=request.source,
                audio=np.array([], dtype=np.float32),
                sample_rate=segment.sample_rate,
                capture_diagnostics=diagnostics,
            )
        return ResidentInvocationRequest(
            source=request.source,
            audio=segment.audio,
            sample_rate=segment.sample_rate,
            capture_diagnostics=diagnostics,
        )

    def _record_capture_diagnostics(self, request: ResidentInvocationRequest) -> None:
        if request.capture_diagnostics is None:
            return
        self._session_service.record_voice_capture_diagnostics(
            source=request.source,
            stage="segment",
            diagnostics=request.capture_diagnostics,
        )

    def _enqueue_barge_in_follow_up(self) -> None:
        request = self._capture_streamed_request(ResidentInvocationRequest(source="barge_in"))
        if request.audio is None or request.audio.size == 0 or request.sample_rate is None:
            return
        self.enqueue("barge_in", request.audio, request.sample_rate)

    def _enqueue_mode_follow_up(self, completed_request: ResidentInvocationRequest) -> None:
        if completed_request.source in RESIDENT_FOLLOW_UP_SOURCES:
            return
        if self._mode == "hands-free":
            self._capture_and_enqueue_follow_up("hands_free")
            return
        if self._mode == "continuous":
            self._capture_and_enqueue_follow_up("continuous")

    def _capture_and_enqueue_follow_up(self, source: str) -> None:
        self._follow_up_listening = True
        self._follow_up_source = source
        try:
            request = self._capture_streamed_request(ResidentInvocationRequest(source=source))
        finally:
            self._follow_up_listening = False
            self._follow_up_source = None
        if request.audio is None or request.audio.size == 0 or request.sample_rate is None:
            return
        self.enqueue(source, request.audio, request.sample_rate)


def _subscriber_chunks(subscriber: queue.Queue[AudioChunk], resident_stream: ResidentAudioStream) -> Iterable[AudioChunk]:
    while resident_stream.is_running():
        try:
            yield subscriber.get(timeout=0.5)
        except queue.Empty:
            break


def _capture_diagnostics_with_timing(diagnostics: dict[str, object], capture_ms: float) -> dict[str, object]:
    return {**diagnostics, "capture_ms": max(0.0, capture_ms)}


def default_utterance_segmenter() -> UtteranceSegmenter:
    settings = load_settings()
    return UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=settings.resident_voice_speech_rms_threshold),
        sample_rate=16000,
        pre_roll_s=settings.resident_voice_pre_roll_seconds,
        min_speech_s=settings.resident_voice_min_speech_seconds,
        silence_end_s=settings.resident_voice_silence_end_seconds,
        max_duration_s=settings.resident_voice_max_duration_seconds,
        no_speech_timeout_s=settings.resident_voice_no_speech_timeout_seconds,
    )


def resident_interruption_chunks(resident_stream: ResidentAudioStream | None) -> Iterable[np.ndarray] | None:
    if resident_stream is None or not resident_stream.is_running():
        return None
    return _resident_interruption_chunks(resident_stream)


def _resident_interruption_chunks(resident_stream: ResidentAudioStream) -> Iterable[np.ndarray]:
    subscriber = resident_stream.subscribe()
    try:
        while resident_stream.is_running():
            try:
                chunk = subscriber.get(timeout=0.1)
            except queue.Empty:
                continue
            yield np.asarray(chunk.samples, dtype=np.float32).reshape(-1)
    finally:
        resident_stream.unsubscribe(subscriber)
