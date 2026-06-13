from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Iterable, Iterator

import numpy as np

from backend.app.runtimes.wake.base import WakeBase
from backend.app.runtimes.wake.openwakeword_runtime import WAKE_CHUNK_SAMPLES
from backend.app.services.session_service import SessionService, WakeMonitorStatus
from backend.app.services.voice_service import wake_chunk_source


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
        provider: str = "openwakeword",
    ) -> None:
        self._session_service = session_service
        self._runtime_factory = runtime_factory
        self._chunk_source = chunk_source
        self._invocation_callback = invocation_callback
        self._provider = provider
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._runtime: WakeBase | None = None

    def status(self) -> WakeMonitorStatus:
        return self._session_service.wake_status()

    def start(self) -> WakeMonitorStatus:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self._session_service.wake_status()
            try:
                runtime = self._runtime_factory()
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
        try:
            pre_roll: deque[np.ndarray] = deque(maxlen=_chunk_count(WAKE_PREROLL_SECONDS))
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
                        command_chunks.extend(self._collect_post_wake_chunks(source))
                        self._invocation_callback("wake", _chunks_to_stt_audio(command_chunks), WAKE_SAMPLE_RATE)
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
            with self._lock:
                if self._thread is threading.current_thread():
                    self._thread = None

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
