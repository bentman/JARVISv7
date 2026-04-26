from __future__ import annotations

from typing import Any

import numpy as np


_sounddevice: Any | None = None
_sounddevice_error: Exception | None = None


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


def play(audio: np.ndarray, sample_rate: int) -> None:
    sounddevice = _load_sounddevice()
    sounddevice.play(audio, samplerate=sample_rate)
    sounddevice.wait()


def stop() -> None:
    sounddevice = _load_sounddevice()
    sounddevice.stop()


def is_playing() -> bool:
    sounddevice = _load_sounddevice()
    return bool(getattr(sounddevice, "get_stream", lambda: None)())