from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Iterable, Iterator

import numpy as np
from backend.app.runtimes.wake.base import WakeBase
from backend.app.runtimes.wake.openwakeword_runtime import WAKE_CHUNK_SAMPLES
from backend.app.services.audio_stream import AudioChunk, ResidentAudioStream
from backend.app.services.session_service import SessionService
from backend.app.services.utterance_segmenter import UtteranceSegmenter
from backend.app.services.voice_service import wake_chunk_source
from backend.app.services.wake_status import WakeMonitorStatus

WakeRuntimeFactory = Callable[[], WakeBase]
WakeChunkSource = Callable[[threading.Event], Iterable[np.ndarray]]
InvocationCallback = Callable[[str, np.ndarray | None, int | None], object]
WAKE_SAMPLE_RATE = 16000
WAKE_PREROLL_SECONDS = 1.0
WAKE_COMMAND_SECONDS = 3.0


def _runtime_score(runtime: WakeBase) -> float | None:
    return getattr(runtime, "last_score", None)


def _runtime_threshold(runtime: WakeBase) -> float | None:
    return getattr(runtime, "threshold", None)


def _chunk_count(duration_s: float) -> int:
    samples = int(WAKE_SAMPLE_RATE * duration_s)
    return max(1, (samples + WAKE_CHUNK_SAMPLES - 1) // WAKE_CHUNK_SAMPLES)


def _chunks_to_stt_audio(chunks: list[np.ndarray]) -> np.ndarray:
    if not chunks:
        return np.asarray([], dtype=np.float32)
    audio = np.concatenate([np.asarray(chunk, dtype=np.int16).reshape(-1) for chunk in chunks])
    return audio.astype(np.float32) / 32768.0


class WakeMonitorService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        runtime_factory: WakeRuntimeFactory,
        chunk_source: WakeChunkSource = wake_chunk_source,
        invocation_callback: InvocationCallback | None = None,
        resident_stream: ResidentAudioStream | None = None,
        utterance_segmenter: UtteranceSegmenter | None = None,
        provider: str = "openwakeword",
    ) -> None:
        self._session_service = session_service
        self._runtime_factory = runtime_factory
        self._chunk_source = chunk_source
        self._invocation_callback = invocation_callback
        self._resident_stream = resident_stream
        self._utterance_segmenter = utterance_segmenter
        self._provider = provider
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._runtime: WakeBase | None = None

    def status(self) -> WakeMonitorStatus:
        return self._session_service.wake_status()

    def warmup(self) -> None:
        """Eagerly initialize and warm up the wake word runtime."""
        with self._lock:
            if self._runtime is None:
                try:
                    self._runtime = self._runtime_factory()
                    self._runtime.warmup()
                except Exception:
                    pass

    def start(self) -> WakeMonitorStatus:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self._session_service.wake_status()
            if self._resident_stream is not None and not self._resident_stream.status().running:
                return self._session_service.record_wake_unavailable(
                    "resident audio stream is stopped; start resident voice stream before wake monitoring"
                )
            try:
                if self._runtime is None:
                    self._runtime = self._runtime_factory()
                runtime = self._runtime
                available = runtime.is_available()
            except Exception as exc:
                return self._session_service.record_wake_error(exc, reason="wake runtime initialization failed; PTT-only fallback is active")
            if not available:
                return self._session_service.record_wake_unavailable()
            self._stop_event.clear()
            self._runtime = runtime
            self._session_service.start_wake_monitor(provider=self._provider, available=True, reason="wake monitoring active")
            self._thread = threading.Thread(target=self._run, args=(runtime,), name="jarvis-wake-monitor", daemon=True)
            self._thread.start()
            return self._session_service.wake_status()

    def stop(self) -> WakeMonitorStatus:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        with self._lock:
            if self._thread is thread:
                self._thread = None
                self._runtime = None
            self._stop_event.clear()
        return self._session_service.stop_wake_monitor()

    def pause_for_voice_invocation(self) -> bool:
        with self._lock:
            status = self._session_service.wake_status()
            should_resume = status.active or status.monitoring
            self._stop_event.set()
            thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        with self._lock:
            if self._thread is thread:
                self._thread = None
            self._stop_event.clear()
        if should_resume:
            self._session_service.pause_wake_monitor()
        return should_resume

    def resume_after_voice_invocation(self, should_resume: bool) -> WakeMonitorStatus:
        if not should_resume:
            return self._session_service.wake_status()
        return self.start()

    def toggle(self) -> WakeMonitorStatus:
        status = self._session_service.wake_status()
        if status.active or status.monitoring:
            return self.stop()
        return self.start()

    def _run(self, runtime: WakeBase) -> None:
        subscriber = None
        try:
            pre_roll: deque[np.ndarray] = deque(maxlen=_chunk_count(WAKE_PREROLL_SECONDS))
            if self._resident_stream is not None and self._resident_stream.status().running:
                subscriber = self._resident_stream.subscribe()
                source = _resident_wake_chunks(subscriber, self._stop_event)
            else:
                source = iter(self._chunk_source(self._stop_event))
            for chunk in source:
                if self._stop_event.is_set():
                    break
                chunk_audio = np.asarray(chunk, dtype=np.int16).reshape(-1)
                pre_roll.append(chunk_audio)
                if runtime.detect(chunk_audio):
                    self._session_service.record_wake_detection(
                        last_score=_runtime_score(runtime),
                        threshold=_runtime_threshold(runtime),
                    )
                    if self._invocation_callback is not None:
                        command_chunks = list(pre_roll)
                        command_audio = self._collect_command_audio(source)
                        if command_audio is None:
                            command_audio = np.asarray([], dtype=np.float32)
                        else:
                            command_chunks.append(command_audio)
                            command_audio = _chunks_to_stt_audio(command_chunks)
                        self._invocation_callback("wake", command_audio, WAKE_SAMPLE_RATE)
                else:
                    self._session_service.record_wake_idle(
                        last_score=_runtime_score(runtime),
                        threshold=_runtime_threshold(runtime),
                    )
        except Exception as exc:
            if not self._stop_event.is_set():
                self._session_service.record_wake_error(
                    exc,
                    last_score=_runtime_score(runtime),
                    threshold=_runtime_threshold(runtime),
                )
        finally:
            if subscriber is not None and self._resident_stream is not None:
                self._resident_stream.unsubscribe(subscriber)
            with self._lock:
                if self._thread is threading.current_thread():
                    self._thread = None

    def _collect_command_audio(self, source: Iterator[np.ndarray]) -> np.ndarray | None:
        if self._utterance_segmenter is None:
            return _chunks_to_stt_audio(self._collect_post_wake_chunks(source))
        segment = self._utterance_segmenter.capture(_wake_audio_chunks(source))
        self._session_service.record_voice_capture_diagnostics(
            source="wake",
            stage="segment",
            diagnostics=segment.diagnostics.as_dict(),
        )
        if not segment.speech_started or segment.audio.size == 0:
            return None
        return _float_to_int16(segment.audio)

    def _collect_post_wake_chunks(self, source: Iterator[np.ndarray]) -> list[np.ndarray]:
        chunks: list[np.ndarray] = []
        for _ in range(_chunk_count(WAKE_COMMAND_SECONDS)):
            if self._stop_event.is_set():
                break
            try:
                chunk = next(source)
            except StopIteration:
                break
            chunks.append(np.asarray(chunk, dtype=np.int16).reshape(-1))
        return chunks


def _resident_wake_chunks(subscriber, stop_event: threading.Event) -> Iterator[np.ndarray]:
    while not stop_event.is_set():
        try:
            chunk = subscriber.get(timeout=0.1)
        except Exception:
            continue
        yield _float_to_int16(chunk.samples)


def _wake_audio_chunks(source: Iterator[np.ndarray]) -> Iterator[AudioChunk]:
    for sequence, chunk in enumerate(source, start=1):
        samples = np.asarray(chunk, dtype=np.int16).reshape(-1).astype(np.float32) / 32768.0
        yield AudioChunk(samples=samples, sample_rate=WAKE_SAMPLE_RATE, sequence=sequence, captured_at=0.0)


def _float_to_int16(samples: np.ndarray) -> np.ndarray:
    audio = np.asarray(samples).reshape(-1)
    if np.issubdtype(audio.dtype, np.integer):
        return audio.astype(np.int16, copy=False)
    clipped = np.clip(audio.astype(np.float32, copy=False), -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16)
