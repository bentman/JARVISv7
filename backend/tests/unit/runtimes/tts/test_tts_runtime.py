from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.runtimes.tts.kokoro_onnx_runtime import KOKORO_SAMPLE_RATE, KokoroOnnxRuntime
from backend.app.runtimes.tts.playback import is_playing, stop
from backend.app.runtimes.tts.tts_runtime import NullTTSRuntime, select_tts_runtime


def test_selector_returns_cpu_runtime_when_readiness_says_cpu():
    preflight = PreflightResult(tokens=["import:kokoro_onnx"], dll_discovery_log=[], probe_errors={})
    profile = HardwareProfile()

    runtime = select_tts_runtime(preflight, profile)

    assert isinstance(runtime, KokoroOnnxRuntime)
    assert runtime.device == "cpu"


def test_selector_returns_null_runtime_when_tts_not_ready():
    preflight = PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={})
    profile = HardwareProfile()

    runtime = select_tts_runtime(preflight, profile)

    assert isinstance(runtime, NullTTSRuntime)
    assert not runtime.is_available()
    assert "kokoro_onnx" in runtime.reason


def test_null_runtime_returns_empty_array_without_raising():
    runtime = NullTTSRuntime(reason="not ready")

    audio = runtime.synthesize("hello world")

    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.size == 0
    assert runtime.sample_rate() == KOKORO_SAMPLE_RATE


def test_kokoro_runtime_accepts_device_parameter():
    runtime = KokoroOnnxRuntime(device="cpu", model_path=Path("unused"))

    assert runtime.device == "cpu"
    with pytest.raises(ValueError, match="unsupported TTS device"):
        KokoroOnnxRuntime(device="qnn", model_path=Path("unused"))


def test_kokoro_runtime_uses_kokoro_helper(monkeypatch, tmp_path):
    model_path = tmp_path / "model"
    model_path.mkdir()
    (model_path / "kokoro-v1.0.onnx").write_text("x", encoding="utf-8")
    (model_path / "voices-v1.0.bin").write_text("x", encoding="utf-8")
    calls = []

    class FakeKokoro:
        def __init__(self, model, voices):
            calls.append((model, voices))

        def create(self, text, *, voice):
            calls.append((text, voice))
            return np.ones(4, dtype=np.float32), 24000

    import sys

    monkeypatch.setitem(sys.modules, "kokoro_onnx", SimpleNamespace(Kokoro=FakeKokoro))
    runtime = KokoroOnnxRuntime(device="cpu", model_path=model_path)

    audio = runtime.synthesize("hello world")

    assert audio.dtype == np.float32
    assert audio.shape == (4,)
    assert runtime.sample_rate() == 24000
    assert calls == [
        (str(model_path / "kokoro-v1.0.onnx"), str(model_path / "voices-v1.0.bin")),
        ("hello world", "af_heart"),
    ]


def test_kokoro_runtime_is_unavailable_when_model_files_missing(tmp_path):
    runtime = KokoroOnnxRuntime(device="cpu", model_path=tmp_path)

    assert not runtime.is_available()
    with pytest.raises(RuntimeError, match="TTS model files"):
        runtime.synthesize("hello world")


def test_catalog_model_path_resolves_existing_tts_catalog():
    runtime = KokoroOnnxRuntime(device="cpu")

    assert runtime.model_path.name == "kokoro-v1.0-onnx"


def test_playback_helpers_fail_only_when_called_if_sounddevice_unavailable(monkeypatch):
    import backend.app.runtimes.tts.playback as playback

    playback._sounddevice = None
    playback._sounddevice_error = RuntimeError("missing")

    with pytest.raises(RuntimeError, match="playback cannot be used"):
        stop()
    with pytest.raises(RuntimeError, match="playback cannot be used"):
        is_playing()

    playback._sounddevice_error = None