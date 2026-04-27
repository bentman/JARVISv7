from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from backend.app.services.voice_service import AudioCaptureError, capture_audio


def test_capture_audio_wraps_sounddevice(monkeypatch):
    calls = []

    def fake_rec(frames, samplerate, channels, dtype):
        calls.append((frames, samplerate, channels, dtype))
        return np.zeros((frames, channels), dtype=np.float32)

    fake_sounddevice = SimpleNamespace(rec=fake_rec, wait=lambda: calls.append("wait"))
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    audio, sample_rate = capture_audio(0.1, sample_rate=16000)

    assert sample_rate == 16000
    assert audio.shape == (1600,)
    assert calls == [(1600, 16000, 1, "float32"), "wait"]


def test_capture_audio_raises_audio_capture_error(monkeypatch):
    def fake_rec(*args, **kwargs):
        raise RuntimeError("device unavailable")

    fake_sounddevice = SimpleNamespace(rec=fake_rec, wait=lambda: None)
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    with pytest.raises(AudioCaptureError, match="device unavailable"):
        capture_audio(0.1)