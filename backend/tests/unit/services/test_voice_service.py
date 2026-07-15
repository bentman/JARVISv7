from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import ClassVar

import numpy as np
import pytest
from backend.app.runtimes.wake.openwakeword_runtime import WAKE_CHUNK_SAMPLES
from backend.app.services.voice_service import (
    AudioCaptureError,
    capture_audio,
    describe_input_device,
    diagnose_audio_ingress,
    wake_chunk_source,
)


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


def test_wake_chunk_source_uses_persistent_sounddevice_stream(monkeypatch) -> None:
    stream_calls: list[tuple[int, int, str, int]] = []
    read_calls: list[int] = []

    class FakeStream:
        def __init__(self, *, samplerate: int, channels: int, dtype: str, blocksize: int) -> None:
            stream_calls.append((samplerate, channels, dtype, blocksize))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def read(self, chunk_samples: int):
            read_calls.append(chunk_samples)
            return np.zeros((chunk_samples, 1), dtype=np.int16), False

    fake_sounddevice = SimpleNamespace(InputStream=FakeStream)
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    stop_event = type("StopEvent", (), {"is_set": lambda self: len(read_calls) > 0})()
    chunk = next(iter(wake_chunk_source(stop_event)))

    assert stream_calls == [(16000, 1, "int16", WAKE_CHUNK_SAMPLES)]
    assert read_calls == [WAKE_CHUNK_SAMPLES]
    assert chunk.shape == (WAKE_CHUNK_SAMPLES,)
    assert chunk.dtype == np.int16


def test_diagnose_audio_ingress_reports_usable_non_silent_capture(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    def fake_capture_audio(duration_s, sample_rate):
        assert duration_s == 1.0
        assert sample_rate == 16000
        return np.array([0.0, 0.25, -0.25], dtype=np.float32), 16000

    monkeypatch.setattr("backend.app.services.voice_service.capture_audio", fake_capture_audio)
    monkeypatch.setattr("backend.app.services.voice_service.describe_input_device", lambda: "3: USB mic")

    result = diagnose_audio_ingress(1.0)

    assert result.usable is True
    assert result.sample_rate == 16000
    assert result.sample_count == 3
    assert result.dtype == "float32"
    assert result.input_device == "3: USB mic"
    assert result.rms > 0
    assert result.peak == 0.25
    assert result.reason == "capture succeeded with non-silent audio"
    assert result.resident_speech_rms_threshold > 0
    assert result.rms >= result.resident_speech_rms_threshold
    assert result.resident_vad_speech is True


def test_diagnose_audio_ingress_reports_below_resident_speech_threshold(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "backend.app.services.voice_service.capture_audio",
        lambda duration_s, sample_rate: (np.full(1600, 0.001, dtype=np.float32), sample_rate),
    )
    monkeypatch.setattr("backend.app.services.voice_service.describe_input_device", lambda: "default input")

    result = diagnose_audio_ingress(1.0)

    assert result.usable is False
    assert result.sample_count == 1600
    assert result.rms < result.resident_speech_rms_threshold
    assert result.peak == pytest.approx(0.001)
    assert result.resident_vad_speech is False
    assert result.reason == "capture succeeded but is below resident speech threshold"


def test_diagnose_audio_ingress_reports_empty_capture(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.voice_service.capture_audio",
        lambda duration_s, sample_rate: (np.array([], dtype=np.float32), sample_rate),
    )
    monkeypatch.setattr("backend.app.services.voice_service.describe_input_device", lambda: "default input")

    result = diagnose_audio_ingress(1.0)

    assert result.usable is False
    assert result.sample_count == 0
    assert result.reason == "capture returned empty audio"


def test_diagnose_audio_ingress_reports_silent_capture(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.voice_service.capture_audio",
        lambda duration_s, sample_rate: (np.zeros(1600, dtype=np.float32), sample_rate),
    )
    monkeypatch.setattr("backend.app.services.voice_service.describe_input_device", lambda: "default input")

    result = diagnose_audio_ingress(1.0)

    assert result.usable is False
    assert result.sample_count == 1600
    assert result.rms == 0.0
    assert result.peak == 0.0
    assert result.reason == "capture succeeded but audio is silent"
    assert result.resident_vad_speech is False


def test_diagnose_audio_ingress_reports_capture_exception(monkeypatch):
    def fail_capture_audio(duration_s, sample_rate):
        raise AudioCaptureError("audio capture failed: device unavailable")

    monkeypatch.setattr("backend.app.services.voice_service.capture_audio", fail_capture_audio)
    monkeypatch.setattr("backend.app.services.voice_service.describe_input_device", lambda: "default input")

    result = diagnose_audio_ingress(5.0)

    assert result.usable is False
    assert result.sample_rate == 16000
    assert result.sample_count == 0
    assert result.duration == 2.0
    assert result.reason == "capture failed: audio capture failed: device unavailable"


def test_describe_input_device_uses_sounddevice_default_input():
    class Default:
        device: ClassVar[list[int]] = [4, 8]

    fake_sounddevice = SimpleNamespace(
        default=Default(),
        query_devices=lambda index, kind: {"name": f"{kind}-{index}"},
    )

    assert describe_input_device(fake_sounddevice) == "4: input-4"
