from __future__ import annotations

import queue
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class AudioChunk:
    samples: np.ndarray
    sample_rate: int
    sequence: int
    captured_at: float


@dataclass(frozen=True, slots=True)
class ResidentAudioStreamStatus:
    running: bool
    sample_rate: int
    chunk_samples: int
    buffer_chunks: int
    subscribers: int
    sequence: int
    dropped_chunks: int
    last_error: str | None


class ResidentAudioStream:
    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        chunk_samples: int = 1280,
        buffer_chunks: int = 32,
        subscriber_queue_size: int = 16,
        chunk_source_factory: Callable[[threading.Event], Iterable[np.ndarray]] | None = None,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.chunk_samples = int(chunk_samples)
        self._buffer: deque[AudioChunk] = deque(maxlen=max(1, int(buffer_chunks)))
        self._subscriber_queue_size = max(1, int(subscriber_queue_size))
        self._chunk_source_factory = chunk_source_factory or self._sounddevice_chunk_source
        self._subscribers: list[queue.Queue[AudioChunk]] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._sequence = 0
        self._dropped_chunks = 0
        self._last_error: str | None = None

    def start(self) -> ResidentAudioStreamStatus:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            self._stop_event.clear()
            self._last_error = None
            self._thread = threading.Thread(target=self._run, name="resident-audio-stream", daemon=True)
            self._thread.start()
            return self.status()

    def stop(self, timeout_s: float = 1.0) -> ResidentAudioStreamStatus:
        thread = self._thread
        self._stop_event.set()
        if thread is not None:
            thread.join(timeout=timeout_s)
        with self._lock:
            if self._thread is thread:
                self._thread = None
            return self.status()

    def status(self) -> ResidentAudioStreamStatus:
        thread = self._thread
        return ResidentAudioStreamStatus(
            running=thread is not None and thread.is_alive(),
            sample_rate=self.sample_rate,
            chunk_samples=self.chunk_samples,
            buffer_chunks=len(self._buffer),
            subscribers=len(self._subscribers),
            sequence=self._sequence,
            dropped_chunks=self._dropped_chunks,
            last_error=self._last_error,
        )

    def buffered_chunks(self) -> list[AudioChunk]:
        with self._lock:
            return list(self._buffer)

    def subscribe(self, *, include_buffer: bool = False) -> queue.Queue[AudioChunk]:
        subscriber: queue.Queue[AudioChunk] = queue.Queue(maxsize=self._subscriber_queue_size)
        with self._lock:
            if include_buffer:
                for chunk in list(self._buffer)[-self._subscriber_queue_size :]:
                    subscriber.put_nowait(chunk)
            self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[AudioChunk]) -> None:
        with self._lock:
            self._subscribers = [candidate for candidate in self._subscribers if candidate is not subscriber]

    def publish_for_test(self, samples: np.ndarray) -> AudioChunk:
        return self._publish(samples)

    def _run(self) -> None:
        try:
            for samples in self._chunk_source_factory(self._stop_event):
                if self._stop_event.is_set():
                    break
                self._publish(samples)
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)

    def _publish(self, samples: np.ndarray) -> AudioChunk:
        array = np.asarray(samples).reshape(-1)
        with self._lock:
            self._sequence += 1
            chunk = AudioChunk(
                samples=array.copy(),
                sample_rate=self.sample_rate,
                sequence=self._sequence,
                captured_at=time.monotonic(),
            )
            self._buffer.append(chunk)
            for subscriber in list(self._subscribers):
                self._put_or_drop(subscriber, chunk)
            return chunk

    def _put_or_drop(self, subscriber: queue.Queue[AudioChunk], chunk: AudioChunk) -> None:
        try:
            subscriber.put_nowait(chunk)
        except queue.Full:
            self._dropped_chunks += 1

    def _sounddevice_chunk_source(self, stop_event: threading.Event) -> Iterable[np.ndarray]:
        try:
            import sounddevice as sd
        except Exception as exc:
            raise RuntimeError("microphone capture is unavailable") from exc

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.chunk_samples,
        ) as stream:
            while not stop_event.is_set():
                data, _ = stream.read(self.chunk_samples)
                yield np.asarray(data, dtype=np.float32).reshape(-1)
