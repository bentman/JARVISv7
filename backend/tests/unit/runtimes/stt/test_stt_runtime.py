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


def test_selector_returns_qnn_runtime_when_qnn_tokens_are_present():
    preflight = PreflightResult(
        tokens=["import:onnxruntime-qnn", "ep:QNNExecutionProvider", "dll:QnnHtp"],
        dll_discovery_log=[],
        probe_errors={},
    )
    profile = HardwareProfile(npu_available=True, npu_vendor="qualcomm")

    runtime = select_stt_runtime(preflight, profile)

    assert isinstance(runtime, QnnWhisperRuntime)
    assert runtime.device == "qnn"


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


def test_qnn_runtime_is_available_with_configured_side_by_side_model_files(tmp_path):
    model_path = tmp_path / "qnn-model"
    encoder_dir = model_path / "encoder"
    decoder_dir = model_path / "decoder"
    encoder_dir.mkdir(parents=True)
    decoder_dir.mkdir(parents=True)
    (encoder_dir / "model.onnx").write_text("x", encoding="utf-8")
    (decoder_dir / "model.onnx").write_text("x", encoding="utf-8")

    runtime = QnnWhisperRuntime(model_path=model_path)
    runtime._model_config = {
        "model_files": {
            "encoder": "encoder/model.onnx",
            "decoder": "decoder/model.onnx",
        }
    }

    assert runtime.is_available()
    assert runtime._configured_model_file("encoder", "encoder.onnx") == encoder_dir / "model.onnx"
    assert runtime._configured_model_file("decoder", "decoder.onnx") == decoder_dir / "model.onnx"


def test_qnn_runtime_is_not_available_when_configured_model_file_is_absent(tmp_path):
    model_path = tmp_path / "qnn-model"
    (model_path / "encoder").mkdir(parents=True)
    (model_path / "encoder" / "model.onnx").write_text("x", encoding="utf-8")

    runtime = QnnWhisperRuntime(model_path=model_path)
    runtime._model_config = {
        "model_files": {
            "encoder": "encoder/model.onnx",
            "decoder": "decoder/model.onnx",
        }
    }

    assert not runtime.is_available()


def test_qnn_runtime_is_not_available_when_model_files_absent(tmp_path):
    model_path = tmp_path / "qnn-model"
    model_path.mkdir(parents=True)

    runtime = QnnWhisperRuntime(model_path=model_path)

    assert not runtime.is_available()


def test_qnn_runtime_ensure_preprocessors_imports_transformers_boundary(monkeypatch, tmp_path):
    import sys

    calls: list[tuple[str, str] | tuple[str, str, dict[str, object]]] = []

    class FakeWhisperConfig:
        return_dict = True
        tie_word_embeddings = True

        @classmethod
        def from_pretrained(cls, model_name: str):
            calls.append(("config", model_name))
            return cls()

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
            WhisperConfig=FakeWhisperConfig,
            WhisperFeatureExtractor=FakeWhisperFeatureExtractor,
            WhisperTokenizer=FakeWhisperTokenizer,
        ),
    )

    runtime = QnnWhisperRuntime(model_path=tmp_path)

    runtime._ensure_preprocessors()

    assert calls == [
        ("feature_extractor", "openai/whisper-base"),
        ("tokenizer", "openai/whisper-base", {}),
        ("config", "openai/whisper-base"),
    ]
    assert runtime._feature_extractor.kind == "feature_extractor"
    assert runtime._tokenizer.kind == "tokenizer"
    assert runtime._whisper_config.return_dict is False
    assert runtime._whisper_config.tie_word_embeddings is False
    assert runtime._whisper_config.mask_neg == -100.0


def test_qnn_runtime_uses_base_tokenizer_without_forced_prefix(monkeypatch, tmp_path):
    import sys

    calls: list[dict[str, object]] = []

    class FakeWhisperConfig:
        @classmethod
        def from_pretrained(cls, model_name: str):
            return SimpleNamespace(return_dict=True, tie_word_embeddings=True)

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
            WhisperConfig=FakeWhisperConfig,
            WhisperFeatureExtractor=FakeWhisperFeatureExtractor,
            WhisperTokenizer=FakeWhisperTokenizer,
        ),
    )
    runtime = QnnWhisperRuntime(model_path=tmp_path)

    runtime._ensure_preprocessors()

    assert calls == [{}]


def test_qnn_runtime_uses_artifact_safe_decode_token_limit(tmp_path):
    runtime = QnnWhisperRuntime(model_path=tmp_path)
    runtime._model_config = {"decode": {"max_new_tokens": 448}}

    assert runtime._decode_config()["max_new_tokens"] == 196


def test_qnn_runtime_uses_qualcomm_decode_loop(monkeypatch, tmp_path):
    model_path = tmp_path / "qnn-model"
    model_path.mkdir()
    (model_path / "encoder.onnx").write_text("x", encoding="utf-8")
    (model_path / "decoder.onnx").write_text("x", encoding="utf-8")

    class FakePreprocessor:
        def __call__(self, waveform, *, sampling_rate, return_tensors):
            return SimpleNamespace(input_features=np.zeros((1, 80, 3000), dtype=np.float32))

    class FakeTokenizer:
        def decode(self, token_ids, *, skip_special_tokens):
            assert token_ids == [50258, 42, 50257]
            return "ok"

    fake_config = SimpleNamespace(
        decoder_start_token_id=50258,
        eos_token_id=50257,
        mask_neg=-100.0,
    )

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
            self.attention_masks: list[np.ndarray] = []

        def get_providers(self):
            return ["QNNExecutionProvider"]

        def get_inputs(self):
            return [
                SimpleNamespace(name="input_ids", shape=[1, 1], type="tensor(int32)"),
                SimpleNamespace(name="attention_mask", shape=[1, 1, 1, 4], type="tensor(float16)"),
                SimpleNamespace(name="position_ids", shape=[1], type="tensor(int32)"),
            ]

        def get_outputs(self):
            return [SimpleNamespace(name="logits")]

        def run(self, output_names, feed):
            self.input_ids.append(int(feed["input_ids"][0][0]))
            self.position_ids.append(int(feed["position_ids"][0]))
            self.attention_masks.append(feed["attention_mask"].copy())
            logits = np.zeros((1, 50258, 1, 1), dtype=np.float32)
            logits[0, 42 if len(self.input_ids) == 1 else 50257, 0, 0] = 1.0
            return [logits]

    decoder = FakeDecoder()
    runtime = QnnWhisperRuntime(model_path=model_path)
    runtime._feature_extractor = FakePreprocessor()
    runtime._tokenizer = FakeTokenizer()
    runtime._whisper_config = fake_config
    monkeypatch.setattr(runtime, "_load_encoder_session", lambda: FakeEncoder())
    monkeypatch.setattr(runtime, "_load_decoder_session", lambda: decoder)

    assert runtime.transcribe(np.zeros(16000, dtype=np.float32), 16000) == "ok"
    assert decoder.input_ids == [50258, 42]
    assert decoder.position_ids == [0, 1]
    np.testing.assert_array_equal(
        decoder.attention_masks[0],
        np.array([[[[-100.0, -100.0, -100.0, 0.0]]]], dtype=np.float16),
    )
    np.testing.assert_array_equal(
        decoder.attention_masks[1],
        np.array([[[[-100.0, -100.0, 0.0, 0.0]]]], dtype=np.float16),
    )


def test_qnn_runtime_reports_non_silent_empty_transcript_with_decode_context(monkeypatch, tmp_path):
    model_path = tmp_path / "qnn-model"
    model_path.mkdir()
    (model_path / "encoder.onnx").write_text("x", encoding="utf-8")
    (model_path / "decoder.onnx").write_text("x", encoding="utf-8")

    class FakePreprocessor:
        def __call__(self, waveform, *, sampling_rate, return_tensors):
            return SimpleNamespace(input_features=np.zeros((1, 80, 3000), dtype=np.float32))

    class FakeTokenizer:
        def decode(self, token_ids, *, skip_special_tokens):
            return ""

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
        def get_providers(self):
            return ["QNNExecutionProvider"]

        def get_inputs(self):
            return [
                SimpleNamespace(name="input_ids", shape=[1, 1], type="tensor(int32)"),
                SimpleNamespace(name="attention_mask", shape=[1, 1, 1, 4], type="tensor(float16)"),
                SimpleNamespace(name="position_ids", shape=[1], type="tensor(int32)"),
            ]

        def get_outputs(self):
            return [SimpleNamespace(name="logits")]

        def run(self, output_names, feed):
            logits = np.zeros((1, 50258, 1, 1), dtype=np.float32)
            logits[0, 50257, 0, 0] = 1.0
            return [logits]

    runtime = QnnWhisperRuntime(model_path=model_path)
    runtime._feature_extractor = FakePreprocessor()
    runtime._tokenizer = FakeTokenizer()
    runtime._whisper_config = SimpleNamespace(
        decoder_start_token_id=50258,
        eos_token_id=50257,
        mask_neg=-100.0,
    )
    monkeypatch.setattr(runtime, "_load_encoder_session", lambda: FakeEncoder())
    monkeypatch.setattr(runtime, "_load_decoder_session", lambda: FakeDecoder())

    with pytest.raises(RuntimeError, match="QNN STT returned empty transcript for non-silent audio"):
        runtime.transcribe(np.full(16000, 0.1, dtype=np.float32), 16000)


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
        min_speech_s=0.0,
        time_source=time_source,
    )

    assert detector.detect(np.ones(160, dtype=np.float32)) is True
    assert detector.detect(np.full(160, 0.01, dtype=np.float32)) is False
    assert detector.detect(np.array([], dtype=np.float32)) is False

    detector.reset()
    assert detector.detect(np.ones(160, dtype=np.float32)) is False

    now = 100.6
    assert detector.detect(np.ones(160, dtype=np.float32)) is True


def test_barge_in_detector_requires_minimum_speech_duration_with_vad() -> None:
    class AlwaysSpeechVAD:
        def detect(self, samples: np.ndarray, sample_rate: int):
            _ = samples, sample_rate
            return SimpleNamespace(speech=True)

    detector = BargeInDetector(
        guard_time_s=0.0,
        min_speech_s=0.02,
        sample_rate=1000,
        vad=AlwaysSpeechVAD(),  # type: ignore[arg-type]
        time_source=lambda: 1.0,
    )
    detector.reset()

    assert detector.detect(np.ones(10, dtype=np.float32)) is False
    assert detector.detect(np.ones(10, dtype=np.float32)) is True


def test_barge_in_detector_requires_consecutive_speech_chunks_when_configured() -> None:
    detector = BargeInDetector(
        energy_threshold=0.02,
        guard_time_s=0.0,
        min_speech_s=0.0,
        min_speech_chunks=2,
        sample_rate=1000,
        time_source=lambda: 1.0,
    )

    assert detector.detect(np.full(10, 0.1, dtype=np.float32)) is False
    assert detector.detect(np.full(10, 0.0, dtype=np.float32)) is False
    assert detector.detect(np.full(10, 0.1, dtype=np.float32)) is False
    assert detector.detect(np.full(10, 0.1, dtype=np.float32)) is True


def test_barge_in_detector_resets_speech_accumulator_on_non_speech() -> None:
    class SequencedVAD:
        def __init__(self) -> None:
            self.decisions = [True, False, True, True]

        def detect(self, samples: np.ndarray, sample_rate: int):
            _ = samples, sample_rate
            return SimpleNamespace(speech=self.decisions.pop(0))

    detector = BargeInDetector(
        guard_time_s=0.0,
        min_speech_s=0.02,
        sample_rate=1000,
        vad=SequencedVAD(),  # type: ignore[arg-type]
        time_source=lambda: 1.0,
    )

    assert detector.detect(np.ones(10, dtype=np.float32)) is False
    assert detector.detect(np.ones(10, dtype=np.float32)) is False
    assert detector.detect(np.ones(10, dtype=np.float32)) is False
    assert detector.detect(np.ones(10, dtype=np.float32)) is True


def test_secondary_onnx_asr_runtime_boundary_is_unavailable():
    runtime = OnnxAsrRuntime(device="cpu")

    assert not runtime.is_available()
    with pytest.raises(RuntimeError, match="boundary-only"):
        runtime.transcribe(np.zeros(16000, dtype=np.float32), 16000)


def test_onnx_whisper_runtime_transcribe_avoids_repeated_file_probes(monkeypatch):
    class FakeModel:
        def recognize(self, waveform, sample_rate):
            return "recognized text"

    runtime = OnnxWhisperRuntime(model_path=Path("fake_path"))
    runtime._model = FakeModel()

    # Track calls to Path.is_file
    is_file_calls = 0
    original_is_file = Path.is_file

    def mock_is_file(self):
        nonlocal is_file_calls
        if "fake_path" in str(self):
            is_file_calls += 1
            return True
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", mock_is_file)

    # transcribe first time
    res = runtime.transcribe(np.zeros(160, dtype=np.float32), 16000)
    assert res == "recognized text"
    assert is_file_calls == 0


def test_qnn_whisper_runtime_transcribe_avoids_repeated_file_probes(monkeypatch):
    runtime = QnnWhisperRuntime(model_path=Path("fake_path"))
    runtime._encoder_session = SimpleNamespace(
        get_providers=lambda: ["QNNExecutionProvider"],
        get_inputs=lambda: [SimpleNamespace(name="input_features")],
        get_outputs=lambda: [SimpleNamespace(name="cross_0")],
    )
    runtime._encoder_session.run = lambda output_names, feed_dict: [np.zeros((1, 1500, 512), dtype=np.float16)]

    runtime._decoder_session = SimpleNamespace(
        get_providers=lambda: ["QNNExecutionProvider"],
        get_inputs=lambda: [
            SimpleNamespace(name="input_ids"),
            SimpleNamespace(name="attention_mask", shape=[1, 1, 1, 2], type="tensor(int32)"),
            SimpleNamespace(name="position_ids"),
        ],
        get_outputs=lambda: [SimpleNamespace(name="logits_0")],
    )
    runtime._decoder_session.run = lambda output_names, feed_dict: [np.zeros((1, 50258, 1, 1), dtype=np.float16)]

    runtime._feature_extractor = lambda waveform, sampling_rate, return_tensors: SimpleNamespace(
        input_features=np.zeros((1, 80, 3000), dtype=np.float16)
    )

    class FakeTokenizer:
        def decode(self, token_ids, skip_special_tokens):
            return "qnn recognized"

    runtime._tokenizer = FakeTokenizer()
    runtime._whisper_config = SimpleNamespace(decoder_start_token_id=50258, eos_token_id=50257)

    # Track calls to Path.is_file
    is_file_calls = 0
    original_is_file = Path.is_file

    def mock_is_file(self):
        nonlocal is_file_calls
        if "fake_path" in str(self):
            is_file_calls += 1
            return True
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", mock_is_file)

    # transcribe first time
    res = runtime.transcribe(np.zeros(160, dtype=np.float32), 16000)
    assert res == "qnn recognized"
    assert is_file_calls == 0
