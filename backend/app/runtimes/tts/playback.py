from __future__ import annotations

import queue
import threading
import time
from typing import Any

import numpy as np

_sounddevice: Any | None = None
_sounddevice_error: Exception | None = None
_last_output_device: str | None = None


def _load_sounddevice() -> Any:
    global _sounddevice, _sounddevice_error
    if _sounddevice is not None:
        return _sounddevice
    if _sounddevice_error is not None:
        raise RuntimeError("sounddevice is unavailable; playback cannot be used") from _sounddevice_error
    try:
        import sounddevice
    except Exception as exc:  # pragma: no cover - host dependency failure path
        _sounddevice_error = exc
        raise RuntimeError("sounddevice is unavailable; playback cannot be used") from exc
    _sounddevice = sounddevice
    return _sounddevice


def start(audio: np.ndarray, sample_rate: int) -> None:
    global _last_output_device
    sounddevice = _load_sounddevice()
    _last_output_device = describe_output_device(sounddevice)
    sounddevice.play(audio, samplerate=sample_rate)


def play(audio: np.ndarray, sample_rate: int) -> None:
    sounddevice = _load_sounddevice()
    start(audio, sample_rate)
    _bounded_wait(sounddevice, audio, sample_rate)


def stop() -> None:
    sounddevice = _load_sounddevice()
    sounddevice.stop()


def is_playing() -> bool:
    sounddevice = _load_sounddevice()
    stream = getattr(sounddevice, "get_stream", lambda: None)()
    if stream is None:
        return False
    active = getattr(stream, "active", None)
    if active is not None:
        return bool(active)
    stopped = getattr(stream, "stopped", None)
    if stopped is not None:
        return not bool(stopped)
    return True


def last_output_device() -> str | None:
    return _last_output_device


def describe_output_device(sounddevice: Any | None = None) -> str:
    sd = sounddevice or _load_sounddevice()
    try:
        default_device = sd.default.device
        output_index = default_device[1] if isinstance(default_device, (list, tuple)) else default_device
        if output_index is None or output_index == -1:
            return "sounddevice default output"
        info = sd.query_devices(output_index, "output")
        name = info.get("name") if isinstance(info, dict) else getattr(info, "name", None)
        return f"{output_index}: {name}" if name else str(output_index)
    except Exception as exc:
        return f"sounddevice output device unknown: {exc}"


def _bounded_wait(sounddevice: Any, audio: np.ndarray, sample_rate: int) -> None:
    wait = getattr(sounddevice, "wait", None)
    if not callable(wait):
        return
    done = threading.Event()
    error: list[BaseException] = []

    def run_wait() -> None:
        try:
            wait()
        except BaseException as exc:
            error.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=run_wait, name="jarvis-tts-playback-wait", daemon=True)
    thread.start()
    timeout_s = _playback_timeout_s(audio, sample_rate)
    if not done.wait(timeout_s):
        stop_fn = getattr(sounddevice, "stop", None)
        if callable(stop_fn):
            stop_fn()
        return
    if error:
        raise error[0]


def _playback_timeout_s(audio: np.ndarray, sample_rate: int) -> float:
    samples = int(np.asarray(audio).reshape(-1).size)
    rate = max(1, int(sample_rate))
    duration_s = samples / float(rate)
    return max(0.5, duration_s + 0.5)


class IterablePlayer:
    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self.sounddevice = _load_sounddevice()
        self.q: queue.Queue[np.ndarray | None] = queue.Queue()
        self.active = True
        self.total_samples = 0
        self._input_done = False
        self._current_chunk = np.array([], dtype=np.float32)
        self._current_idx = 0
        self._stream: Any | None = None
        global _last_output_device
        _last_output_device = describe_output_device(self.sounddevice)

    def _callback(self, outdata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        outdata.fill(0)
        filled = 0
        while filled < frames and self.active:
            if self._current_idx >= len(self._current_chunk):
                try:
                    next_chunk = self.q.get_nowait()
                    if next_chunk is None:
                        self.active = False
                        break
                    self._current_chunk = next_chunk.reshape(-1)
                    self._current_idx = 0
                except Exception:
                    break

            chunk_left = len(self._current_chunk) - self._current_idx
            frames_needed = frames - filled
            to_write = min(chunk_left, frames_needed)

            outdata[filled:filled+to_write, 0] = self._current_chunk[self._current_idx : self._current_idx+to_write]
            self._current_idx += to_write
            filled += to_write

        if not self.active:
            raise self.sounddevice.CallbackStop

    def start(self) -> None:
        self._stream = self.sounddevice.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            callback=self._callback,
            dtype='float32'
        )
        self._stream.start()

    def put(self, chunk: np.ndarray | None) -> None:
        if chunk is None:
            self._input_done = True
        else:
            self.total_samples += chunk.size
        self.q.put(chunk)

    def stop(self) -> None:
        self.active = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def is_playing(self) -> bool:
        if not self.active:
            return False
        if self._stream is None:
            return False
        return bool(self._stream.active)

    def wait(self, timeout_s: float | None = None) -> None:
        start_time = time.time()
        while self.active:
            if self._input_done and self.q.empty() and self._current_idx >= len(self._current_chunk):
                break
            if timeout_s is not None:
                deadline = timeout_s
            else:
                # Recompute against samples enqueued so far: a momentary
                # synthesis underrun must not be mistaken for end-of-playback
                # (that would truncate the remainder of the response). While
                # the producer is still streaming, allow a generous stall
                # grace instead of the drain grace.
                grace = 0.5 if self._input_done else 5.0
                deadline = (self.total_samples / self.sample_rate) + grace
            if time.time() - start_time > deadline:
                break
            time.sleep(0.01)
        self.stop()
