from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.runtimes.wake.base import WakeBase
from backend.app.runtimes.wake.openwakeword_runtime import OpenWakeWordRuntime, WAKE_CHUNK_SAMPLES
from backend.app.runtimes.wake.porcupine_runtime import PorcupineRuntime
from backend.app.runtimes.wake.wake_runtime import NullWakeRuntime, select_wake_runtime


def test_selector_returns_openwakeword_runtime_when_ready():
    preflight = PreflightResult(tokens=["import:openwakeword"], dll_discovery_log=[], probe_errors={})

    runtime = select_wake_runtime(preflight, HardwareProfile())

    assert isinstance(runtime, OpenWakeWordRuntime)
    assert runtime.device == "cpu"


def test_selector_returns_null_runtime_when_wake_not_ready():
    preflight = PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={})

    runtime = select_wake_runtime(preflight, HardwareProfile())

    assert isinstance(runtime, NullWakeRuntime)
    assert runtime.detect(np.zeros(WAKE_CHUNK_SAMPLES, dtype=np.int16)) is False
    assert "openwakeword" in runtime.reason


def test_wake_base_raises_on_non_cpu_device():
    class ConcreteWake(WakeBase):
        def detect(self, audio_chunk: np.ndarray) -> bool:
            return False

        def is_available(self) -> bool:
            return True

    with pytest.raises(ValueError, match="cpu"):
        ConcreteWake(device="cuda", model_path=Path("unused"))


def test_openwakeword_runtime_is_available_false_when_model_missing(tmp_path):
    runtime = OpenWakeWordRuntime(model_path=tmp_path)

    assert not runtime.is_available()
    with pytest.raises(RuntimeError, match="wake model files"):
        runtime.detect(np.zeros(WAKE_CHUNK_SAMPLES, dtype=np.int16))


def test_openwakeword_runtime_streams_chunks_and_detects(monkeypatch, tmp_path):
    for filename in ("hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx"):
        (tmp_path / filename).write_text("x", encoding="utf-8")
    calls = []

    class FakeModel:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def predict(self, chunk):
            calls.append(chunk.shape[0])
            return {"hey_jarvis_v0.1": 0.7 if chunk.shape[0] else 0.0}

    import sys

    monkeypatch.setitem(sys.modules, "openwakeword", SimpleNamespace(Model=FakeModel))
    runtime = OpenWakeWordRuntime(model_path=tmp_path, threshold=0.5)

    assert runtime.detect(np.zeros(WAKE_CHUNK_SAMPLES * 2, dtype=np.int16)) is True
    assert runtime.last_score == 0.7
    assert calls[1:] == [WAKE_CHUNK_SAMPLES, WAKE_CHUNK_SAMPLES]


def test_porcupine_runtime_is_available_false_when_no_access_key(monkeypatch):
    monkeypatch.delenv("PICOVOICE_ACCESS_KEY", raising=False)
    runtime = PorcupineRuntime()

    assert runtime.is_available() is False
    assert "PICOVOICE_ACCESS_KEY" in runtime.reason
    with pytest.raises(RuntimeError, match="structural only"):
        runtime.detect(np.zeros(WAKE_CHUNK_SAMPLES, dtype=np.int16))


def test_porcupine_runtime_is_structurally_available_with_access_key(monkeypatch):
    monkeypatch.setenv("PICOVOICE_ACCESS_KEY", "test-key")
    runtime = PorcupineRuntime()

    assert runtime.is_available() is True


def test_null_wake_runtime_detect_always_returns_false():
    runtime = NullWakeRuntime(reason="not ready")

    assert not runtime.is_available()
    assert runtime.detect(np.ones(WAKE_CHUNK_SAMPLES, dtype=np.int16)) is False