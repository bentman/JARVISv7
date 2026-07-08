from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import time

import numpy as np
import pytest

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.runtimes.tts.kokoro_onnx_runtime import KOKORO_SAMPLE_RATE, KokoroOnnxRuntime
from backend.app.runtimes.tts.playback import describe_output_device, is_playing, stop
from backend.app.runtimes.tts.tts_runtime import NullTTSRuntime, select_tts_runtime, validate_tts_voice


def test_selector_returns_cpu_runtime_when_readiness_says_cpu():
    preflight = PreflightResult(tokens=["import:kokoro_onnx"], dll_discovery_log=[], probe_errors={})
    profile = HardwareProfile()

    runtime = select_tts_runtime(preflight, profile)

    assert isinstance(runtime, KokoroOnnxRuntime)
    assert runtime.device == "cpu"
    assert runtime.voice == "bf_isabella"


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


def test_tts_device_slot_accepts_cuda_string():
    runtime = KokoroOnnxRuntime(device="cuda", model_path=Path("unused"))
    assert runtime.device == "cuda"


def test_tts_device_slot_accepts_directml_string():
    runtime = KokoroOnnxRuntime(device="directml", model_path=Path("unused"))
    assert runtime.device == "directml"


def test_tts_device_slot_accepts_qnn_string():
    runtime = KokoroOnnxRuntime(device="qnn", model_path=Path("unused"))
    assert runtime.device == "qnn"


def test_kokoro_runtime_reports_provider_override_missing_for_accelerated_device(tmp_path):
    model_path = tmp_path / "model"
    model_path.mkdir()
    (model_path / "kokoro-v1.0.onnx").write_text("x", encoding="utf-8")
    (model_path / "voices-v1.0.bin").write_text("x", encoding="utf-8")

    runtime = KokoroOnnxRuntime(device="cuda", model_path=model_path)

    with pytest.raises(RuntimeError, match="provider-override-missing"):
        runtime.synthesize("hello world")


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


def test_selector_uses_configured_yaml_voice_for_kokoro_runtime():
    preflight = PreflightResult(tokens=["import:kokoro_onnx"], dll_discovery_log=[], probe_errors={})
    profile = HardwareProfile()

    runtime = select_tts_runtime(preflight, profile)

    assert isinstance(runtime, KokoroOnnxRuntime)
    assert runtime.voice == "bf_isabella"


def test_validate_tts_voice_uses_supported_config_without_rewriting_yaml():
    config_path = Path("config/models/tts.yaml")
    before = config_path.read_text(encoding="utf-8")

    assert validate_tts_voice("af_bella") == "af_bella"
    with pytest.raises(ValueError, match="unsupported tts voice"):
        validate_tts_voice("not_a_voice")

    assert config_path.read_text(encoding="utf-8") == before


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


def test_is_playing_uses_sounddevice_stream_active_state(monkeypatch):
    import backend.app.runtimes.tts.playback as playback

    stream = SimpleNamespace(active=False)
    playback._sounddevice = SimpleNamespace(get_stream=lambda: stream)
    playback._sounddevice_error = None

    assert playback.is_playing() is False

    stream.active = True

    assert playback.is_playing() is True


def test_is_playing_uses_sounddevice_stream_stopped_state_when_active_missing(monkeypatch):
    import backend.app.runtimes.tts.playback as playback

    stream = SimpleNamespace(stopped=True)
    playback._sounddevice = SimpleNamespace(get_stream=lambda: stream)
    playback._sounddevice_error = None

    assert playback.is_playing() is False

    stream.stopped = False

    assert playback.is_playing() is True


def test_playback_records_default_output_device(monkeypatch):
    import backend.app.runtimes.tts.playback as playback

    class Default:
        device = [2, 7]

    calls = []
    fake_sounddevice = SimpleNamespace(
        default=Default(),
        query_devices=lambda index, kind: {"name": f"{kind}-{index}"},
        play=lambda audio, samplerate: calls.append((audio.shape, samplerate)),
        wait=lambda: None,
    )
    playback._sounddevice = fake_sounddevice
    playback._sounddevice_error = None
    playback._last_output_device = None

    playback.play(np.zeros(4, dtype=np.float32), 24000)

    assert playback.last_output_device() == "7: output-7"
    assert calls == [((4,), 24000)]


def test_playback_wait_is_bounded_when_sounddevice_wait_blocks(monkeypatch):
    import backend.app.runtimes.tts.playback as playback

    class Default:
        device = [2, 7]

    calls: list[str] = []

    def blocking_wait():
        time.sleep(5.0)

    fake_sounddevice = SimpleNamespace(
        default=Default(),
        query_devices=lambda index, kind: {"name": f"{kind}-{index}"},
        play=lambda audio, samplerate: calls.append("play"),
        wait=blocking_wait,
        stop=lambda: calls.append("stop"),
    )
    playback._sounddevice = fake_sounddevice
    playback._sounddevice_error = None
    playback._last_output_device = None

    started = time.monotonic()
    playback.play(np.zeros(4, dtype=np.float32), 24000)

    assert time.monotonic() - started < 2.0
    assert calls == ["play", "stop"]


def test_playback_wait_error_is_propagated(monkeypatch):
    import backend.app.runtimes.tts.playback as playback

    class Default:
        device = [2, 7]

    fake_sounddevice = SimpleNamespace(
        default=Default(),
        query_devices=lambda index, kind: {"name": f"{kind}-{index}"},
        play=lambda audio, samplerate: None,
        wait=lambda: (_ for _ in ()).throw(RuntimeError("playback wait failed")),
    )
    playback._sounddevice = fake_sounddevice
    playback._sounddevice_error = None
    playback._last_output_device = None

    with pytest.raises(RuntimeError, match="playback wait failed"):
        playback.play(np.zeros(4, dtype=np.float32), 24000)


def test_describe_output_device_falls_back_when_default_is_unavailable():
    fake_sounddevice = SimpleNamespace(default=SimpleNamespace(device=[None, -1]))

    assert describe_output_device(fake_sounddevice) == "sounddevice default output"
