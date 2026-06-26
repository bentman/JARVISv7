from __future__ import annotations

from typing import Any
import threading

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
        default_device = getattr(sd, "default").device
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
