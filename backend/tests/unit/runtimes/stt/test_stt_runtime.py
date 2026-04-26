from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.runtimes.stt.barge_in import BargeInDetector
from backend.app.runtimes.stt.onnx_asr_runtime import OnnxAsrRuntime
from backend.app.runtimes.stt.onnx_whisper_runtime import (
    QNN_STT_DEFERRED_REASON,
    OnnxWhisperRuntime,
    providers_for_device,
)
from backend.app.runtimes.stt.stt_runtime import DegradedSTTRuntime, select_stt_runtime


def test_selector_returns_cpu_runtime_when_readiness_says_cpu():
    preflight = PreflightResult(tokens=["import:onnxruntime"], dll_discovery_log=[], probe_errors={})
    profile = HardwareProfile()

    runtime = select_stt_runtime(preflight, profile)

    assert isinstance(runtime, OnnxWhisperRuntime)
    assert runtime.device == "cpu"


def test_selector_returns_cuda_runtime_when_cuda_ep_proven():
    preflight = PreflightResult(
        tokens=["import:onnxruntime", "ep:CUDAExecutionProvider"],
        dll_discovery_log=[],
        probe_errors={},
    )
    profile = HardwareProfile(gpu_vendor="nvidia", cuda_available=True)

    runtime = select_stt_runtime(preflight, profile)

    assert isinstance(runtime, OnnxWhisperRuntime)
    assert runtime.device == "cuda"
    assert runtime.providers == ["CUDAExecutionProvider", "CPUExecutionProvider"]


def test_selector_returns_directml_runtime_when_dml_ep_proven():
    preflight = PreflightResult(
        tokens=["import:onnxruntime", "ep:DmlExecutionProvider"],
        dll_discovery_log=[],
        probe_errors={},
    )
    profile = HardwareProfile(os_name="windows", gpu_available=True, gpu_vendor="amd")

    runtime = select_stt_runtime(preflight, profile)

    assert isinstance(runtime, OnnxWhisperRuntime)
    assert runtime.device == "directml"
    assert runtime.providers == ["DmlExecutionProvider", "CPUExecutionProvider"]


def test_selector_returns_degraded_runtime_when_device_not_ready():
    preflight = PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={})
    profile = HardwareProfile()

    runtime = select_stt_runtime(preflight, profile)

    assert isinstance(runtime, DegradedSTTRuntime)
    assert not runtime.is_available()
    with pytest.raises(RuntimeError, match="onnxruntime"):
        runtime.transcribe(np.zeros(16000, dtype=np.float32), 16000)


def test_qnn_branch_raises_not_implemented_without_loading_session():
    runtime = OnnxWhisperRuntime(device="qnn", model_path=Path("unused"))

    assert not runtime.is_available()
    assert runtime._model is None
    with pytest.raises(NotImplementedError, match="H.2"):
        runtime.transcribe(np.zeros(16000, dtype=np.float32), 16000)
    assert runtime._model is None
    assert QNN_STT_DEFERRED_REASON.endswith("H.2")


def test_onnx_whisper_runtime_accepts_device_parameter():
    assert OnnxWhisperRuntime(device="cpu", model_path=Path("unused")).providers == [
        "CPUExecutionProvider"
    ]
    assert providers_for_device("cuda") == ["CUDAExecutionProvider", "CPUExecutionProvider"]
    assert providers_for_device("directml") == ["DmlExecutionProvider", "CPUExecutionProvider"]


def test_onnx_whisper_runtime_uses_onnx_asr_helper(monkeypatch, tmp_path):
    model_path = tmp_path / "model"
    model_path.mkdir()
    for filename in (
        "encoder_model.onnx",
        "decoder_model_merged.onnx",
        "config.json",
        "generation_config.json",
        "preprocessor_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "vocab.json",
        "merges.txt",
        "normalizer.json",
        "added_tokens.json",
    ):
        (model_path / filename).write_text("x", encoding="utf-8")

    calls = []

    class FakeModel:
        def recognize(self, waveform, *, sample_rate):
            calls.append((waveform.dtype, sample_rate))
            return "hello world"

    def fake_load_model(model, *, path, providers):
        assert model == "onnx-community/whisper-small"
        assert path == model_path
        assert providers == ["CPUExecutionProvider"]
        return FakeModel()

    import sys

    monkeypatch.setitem(sys.modules, "onnx_asr", SimpleNamespace(load_model=fake_load_model))
    runtime = OnnxWhisperRuntime(device="cpu", model_path=model_path)

    assert runtime.transcribe(np.zeros(16000), 16000) == "hello world"
    assert calls == [(np.dtype("float32"), 16000)]


def test_catalog_model_path_resolves_existing_stt_catalog():
    runtime = OnnxWhisperRuntime(device="cpu")

    assert runtime.model_path.name == "whisper-small-onnx"


def test_barge_in_detector_stub_always_returns_false():
    assert BargeInDetector().detect(np.ones(160, dtype=np.float32)) is False


def test_secondary_onnx_asr_runtime_boundary_is_unavailable():
    runtime = OnnxAsrRuntime(device="cpu")

    assert not runtime.is_available()
    with pytest.raises(RuntimeError, match="boundary-only"):
        runtime.transcribe(np.zeros(16000, dtype=np.float32), 16000)