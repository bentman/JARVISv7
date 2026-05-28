from __future__ import annotations

import threading
from collections.abc import Callable, Iterable

import numpy as np

from backend.app.runtimes.wake.base import WakeBase
from backend.app.runtimes.wake.openwakeword_runtime import WAKE_CHUNK_SAMPLES
from backend.app.services.session_service import SessionService, WakeMonitorStatus


WakeRuntimeFactory = Callable[[], WakeBase]
WakeChunkSource = Callable[[threading.Event], Iterable[np.ndarray]]


def microphone_chunk_source(stop_event: threading.Event, *, sample_rate: int = 16000, chunk_samples: int = WAKE_CHUNK_SAMPLES) -> Iterable[np.ndarray]:
    try:
        import sounddevice as sd
    except Exception as exc:
        raise RuntimeError("microphone capture is unavailable") from exc

    while not stop_event.is_set():
        audio = sd.rec(chunk_samples, samplerate=sample_rate, channels=1, dtype="int16")
        sd.wait()
        yield np.asarray(audio, dtype=np.int16).reshape(-1)


class WakeMonitorService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        runtime_factory: WakeRuntimeFactory,
        chunk_source: WakeChunkSource = microphone_chunk_source,
        provider: str = "openwakeword",
    ) -> None:
        self._session_service = session_service
        self._runtime_factory = runtime_factory
        self._chunk_source = chunk_source
        self._provider = provider
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

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
            self._stop_event.clear()
        return self._session_service.stop_wake_monitor()

    def toggle(self) -> WakeMonitorStatus:
        status = self._session_service.wake_status()
        if status.active or status.monitoring:
            return self.stop()
        return self.start()

    def _run(self, runtime: WakeBase) -> None:
        try:
            for chunk in self._chunk_source(self._stop_event):
                if self._stop_event.is_set():
                    break
                if runtime.detect(np.asarray(chunk)):
                    self._session_service.record_wake_detection()
                else:
                    self._session_service.record_wake_idle()
        except Exception as exc:
            if not self._stop_event.is_set():
                self._session_service.record_wake_error(exc)
        finally:
            with self._lock:
                if self._thread is threading.current_thread():
                    self._thread = None
