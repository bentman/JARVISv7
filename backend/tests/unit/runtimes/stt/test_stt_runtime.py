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
    ONNX_WHISPER_QNN_NOT_WIRED_REASON,
    OnnxWhisperRuntime,
    QnnWhisperRuntime,
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


def test_selector_returns_qnn_runtime_when_qnn_tokens_proven():
    preflight = PreflightResult(
        tokens=["import:onnxruntime-qnn", "ep:QNNExecutionProvider", "dll:QnnHtp"],
        dll_discovery_log=[],
        probe_errors={},
    )
    profile = HardwareProfile(npu_available=True, npu_vendor="qualcomm")

    runtime = select_stt_runtime(preflight, profile)

    assert isinstance(runtime, QnnWhisperRuntime)
    assert runtime.device == "qnn"
    assert runtime.model_name == "whisper-base-en-qnn-snapdragon-x-elite"


def test_selector_returns_degraded_runtime_when_device_not_ready():
    preflight = PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={})
    profile = HardwareProfile()

    runtime = select_stt_runtime(preflight, profile)

    assert isinstance(runtime, DegradedSTTRuntime)
    assert not runtime.is_available()
    with pytest.raises(RuntimeError, match="onnxruntime"):
        runtime.transcribe(np.zeros(16000, dtype=np.float32), 16000)


def test_qnn_runtime_is_available_when_model_files_present_recursively(tmp_path):
    model_path = tmp_path / "qnn-model"
    nested = model_path / "artifact" / "inner"
    nested.mkdir(parents=True)
    (nested / "encoder.onnx").write_text("x", encoding="utf-8")
    (nested / "decoder.onnx").write_text("x", encoding="utf-8")

    runtime = QnnWhisperRuntime(model_path=model_path)

    assert runtime.is_available()


def test_qnn_runtime_is_not_available_when_model_files_absent(tmp_path):
    model_path = tmp_path / "qnn-model"
    model_path.mkdir(parents=True)

    runtime = QnnWhisperRuntime(model_path=model_path)

    assert not runtime.is_available()


def test_qnn_runtime_ensure_preprocessors_imports_transformers_boundary(monkeypatch, tmp_path):
    import sys

    calls: list[tuple[str, str] | tuple[str, str, dict[str, object]]] = []

    class FakeWhisperFeatureExtractor:
        @classmethod
        def from_pretrained(cls, model_name: str):
            calls.append(("feature_extractor", model_name))
            return SimpleNamespace(kind="feature_extractor")

    class FakeWhisperTokenizer:
        @classmethod
        def from_pretrained(cls, model_name: str, **kwargs):
            calls.append(("tokenizer", model_name, kwargs))
            return SimpleNamespace(kind="tokenizer")

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            WhisperFeatureExtractor=FakeWhisperFeatureExtractor,
            WhisperTokenizer=FakeWhisperTokenizer,
        ),
    )

    runtime = QnnWhisperRuntime(model_path=tmp_path)

    runtime._ensure_preprocessors()

    assert calls == [
        ("feature_extractor", "openai/whisper-base"),
        (
            "tokenizer",
            "openai/whisper-base",
            {"language": "english", "task": "transcribe", "predict_timestamps": False},
        ),
    ]
    assert runtime._feature_extractor.kind == "feature_extractor"
    assert runtime._tokenizer.kind == "tokenizer"


def test_qnn_runtime_uses_configured_language_for_tokenizer_prefix(monkeypatch, tmp_path):
    import sys

    calls: list[dict[str, object]] = []

    class FakeWhisperFeatureExtractor:
        @classmethod
        def from_pretrained(cls, model_name: str):
            return SimpleNamespace(kind="feature_extractor")

    class FakeWhisperTokenizer:
        @classmethod
        def from_pretrained(cls, model_name: str, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(kind="tokenizer", prefix_tokens=[10, 11, 12])

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            WhisperFeatureExtractor=FakeWhisperFeatureExtractor,
            WhisperTokenizer=FakeWhisperTokenizer,
        ),
    )
    monkeypatch.setattr(
        "backend.app.runtimes.stt.onnx_whisper_runtime.load_settings",
        lambda: SimpleNamespace(jarvis_language="es"),
    )
    runtime = QnnWhisperRuntime(model_path=tmp_path)

    runtime._ensure_preprocessors()

    assert calls == [{"language": "es", "task": "transcribe", "predict_timestamps": False}]


def test_qnn_runtime_primes_decoder_with_full_tokenizer_prefix(monkeypatch, tmp_path):
    model_path = tmp_path / "qnn-model"
    model_path.mkdir()
    (model_path / "encoder.onnx").write_text("x", encoding="utf-8")
    (model_path / "decoder.onnx").write_text("x", encoding="utf-8")

    class FakePreprocessor:
        def __call__(self, waveform, *, sampling_rate, return_tensors):
            return SimpleNamespace(input_features=np.zeros((1, 80, 3000), dtype=np.float32))

    class FakeTokenizer:
        prefix_tokens = [10, 11, 12]

        def decode(self, token_ids, *, skip_special_tokens):
            return "ok"

    class FakeEncoder:
        def get_providers(self):
            return ["QNNExecutionProvider"]

        def get_inputs(self):
            return [SimpleNamespace(name="input_features")]

        def get_outputs(self):
            return []

        def run(self, output_names, feed):
            return []

    class FakeDecoder:
        def __init__(self):
            self.input_ids: list[int] = []
            self.position_ids: list[int] = []

        def get_providers(self):
            return ["QNNExecutionProvider"]

        def get_inputs(self):
            return [
                SimpleNamespace(name="input_ids", shape=[1, 1], type="tensor(int32)"),
                SimpleNamespace(name="position_ids", shape=[1], type="tensor(int32)"),
            ]

        def get_outputs(self):
            return [SimpleNamespace(name="logits")]

        def run(self, output_names, feed):
            self.input_ids.append(int(feed["input_ids"][0][0]))
            self.position_ids.append(int(feed["position_ids"][0]))
            logits = np.zeros((1, 50258, 1, 1), dtype=np.float32)
            logits[0, 50257, 0, 0] = 1.0
            return [logits]

    decoder = FakeDecoder()
    runtime = QnnWhisperRuntime(model_path=model_path)
    runtime._feature_extractor = FakePreprocessor()
    runtime._tokenizer = FakeTokenizer()
    monkeypatch.setattr(runtime, "_load_encoder_session", lambda: FakeEncoder())
    monkeypatch.setattr(runtime, "_load_decoder_session", lambda: decoder)

    assert runtime.transcribe(np.zeros(16000, dtype=np.float32), 16000) == "ok"
    assert decoder.input_ids == [10, 11, 12]
    assert decoder.position_ids == [0, 1, 2]


def test_qnn_runtime_real_transformers_preprocessor_import_boundary():
    transformers = pytest.importorskip("transformers")

    from transformers import WhisperFeatureExtractor, WhisperTokenizer

    assert WhisperFeatureExtractor is transformers.WhisperFeatureExtractor
    assert WhisperTokenizer is transformers.WhisperTokenizer


def test_onnx_whisper_qnn_guard_does_not_expose_slice_reference():
    assert "H.3.2" not in ONNX_WHISPER_QNN_NOT_WIRED_REASON
    assert "not wired through OnnxWhisperRuntime" in ONNX_WHISPER_QNN_NOT_WIRED_REASON


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


def test_barge_in_detector_uses_rms_threshold_and_guard_time():
    now = 100.0

    def time_source() -> float:
        return now

    detector = BargeInDetector(
        energy_threshold=0.02,
        guard_time_s=0.5,
        time_source=time_source,
    )

    assert detector.detect(np.ones(160, dtype=np.float32)) is True
    assert detector.detect(np.full(160, 0.01, dtype=np.float32)) is False
    assert detector.detect(np.array([], dtype=np.float32)) is False

    detector.reset()
    assert detector.detect(np.ones(160, dtype=np.float32)) is False

    now = 100.6
    assert detector.detect(np.ones(160, dtype=np.float32)) is True


def test_secondary_onnx_asr_runtime_boundary_is_unavailable():
    runtime = OnnxAsrRuntime(device="cpu")

    assert not runtime.is_available()
    with pytest.raises(RuntimeError, match="boundary-only"):
        runtime.transcribe(np.zeros(16000, dtype=np.float32), 16000)
