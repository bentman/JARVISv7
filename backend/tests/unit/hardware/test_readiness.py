from __future__ import annotations

from types import SimpleNamespace

from backend.app.core.capabilities import HardwareProfile
from backend.app.core.settings import Settings
from backend.app.hardware.preflight import PreflightResult
from backend.app.hardware.readiness import (
    derive_llm_device_readiness,
    derive_stt_device_readiness,
    derive_tts_device_readiness,
    derive_wake_device_readiness,
)


def _llm_settings(**overrides) -> Settings:
    defaults = dict(
        use_local_model=True,
        llama_cpp_managed_explicit=False,
        llama_cpp_managed=False,
        llama_cpp_base_url_explicit=False,
        use_ollama=False,
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _profile(**overrides) -> HardwareProfile:
    return HardwareProfile(**overrides)


def _preflight(*tokens: str) -> PreflightResult:
    return PreflightResult(tokens=list(tokens), dll_discovery_log=[], probe_errors={})


def test_stt_readiness_selects_cpu_on_arm64_when_onnxruntime_imported() -> None:
    selected_device, ready, reason = derive_stt_device_readiness(
        _preflight("import:onnxruntime"),
        _profile(os_name="windows", arch="arm64"),
    )

    assert (selected_device, ready) == ("cpu", True)
    assert "import:onnxruntime" in reason


def test_stt_readiness_selects_cuda_on_nvidia_when_cuda_ep_proven() -> None:
    selected_device, ready, reason = derive_stt_device_readiness(
        _preflight("import:onnxruntime", "ep:CUDAExecutionProvider"),
        _profile(
            os_name="windows",
            arch="amd64",
            gpu_available=True,
            gpu_vendor="nvidia",
            cuda_available=True,
        ),
    )

    assert (selected_device, ready) == ("cuda", True)
    assert "ep:CUDAExecutionProvider" in reason


def test_stt_readiness_selects_cpu_with_reason_when_cuda_ep_missing() -> None:
    selected_device, ready, reason = derive_stt_device_readiness(
        _preflight("import:onnxruntime"),
        _profile(
            os_name="windows",
            arch="amd64",
            gpu_available=True,
            gpu_vendor="nvidia",
            cuda_available=True,
        ),
    )

    assert (selected_device, ready) == ("cpu", True)
    assert "import:onnxruntime" in reason


def test_tts_readiness_selects_cpu_when_kokoro_onnx_imported() -> None:
    selected_device, ready, reason = derive_tts_device_readiness(
        _preflight("import:kokoro_onnx"),
        _profile(os_name="linux", arch="amd64"),
    )

    assert (selected_device, ready) == ("cpu", True)
    assert "import:kokoro_onnx" in reason


def test_tts_readiness_selects_cuda_for_cuda_candidate() -> None:
    selected_device, ready, reason = derive_tts_device_readiness(
        _preflight("import:kokoro_onnx", "ep:CUDAExecutionProvider"),
        _profile(
            os_name="windows",
            arch="amd64",
            gpu_available=True,
            gpu_vendor="nvidia",
            cuda_available=True,
        ),
    )

    assert (selected_device, ready) == ("cuda", True)
    assert "ep:CUDAExecutionProvider" in reason


def test_stt_readiness_selects_qnn_when_qnn_ep_proven() -> None:
    selected_device, ready, reason = derive_stt_device_readiness(
        _preflight("import:onnxruntime-qnn", "ep:QNNExecutionProvider", "dll:QnnHtp"),
        _profile(
            os_name="windows",
            arch="arm64",
            npu_available=True,
            npu_vendor="qualcomm",
        ),
    )

    assert (selected_device, ready) == ("qnn", True)
    assert "qnn prerequisites proven" in reason


def test_stt_readiness_falls_back_to_cpu_when_qnn_ep_missing_on_npu() -> None:
    selected_device, ready, reason = derive_stt_device_readiness(
        _preflight("import:onnxruntime"),
        _profile(
            os_name="windows",
            arch="arm64",
            npu_available=True,
            npu_vendor="qualcomm",
        ),
    )

    assert (selected_device, ready) == ("cpu", True)
    assert "selecting cpu" in reason


def test_tts_readiness_reports_not_ready_when_kokoro_onnx_missing() -> None:
    selected_device, ready, reason = derive_tts_device_readiness(
        _preflight(),
        _profile(os_name="linux", arch="amd64"),
    )

    assert (selected_device, ready) == ("cpu", False)
    assert "import:kokoro_onnx:MISSING" in reason


def test_tts_readiness_selects_directml_for_directml_candidate() -> None:
    selected_device, ready, reason = derive_tts_device_readiness(
        _preflight("import:kokoro_onnx", "ep:DmlExecutionProvider"),
        _profile(os_name="windows", arch="amd64", gpu_available=True),
    )

    assert (selected_device, ready) == ("directml", True)
    assert "ep:DmlExecutionProvider" in reason


def test_llm_readiness_reports_disabled_when_local_model_disabled() -> None:
    selected_device, ready, reason = derive_llm_device_readiness(
        _preflight(),
        _profile(os_name="linux", arch="amd64"),
        settings=_llm_settings(use_local_model=False),
    )

    assert (selected_device, ready) == ("disabled", False)
    assert "llm.yaml catalog not applicable" in reason


def test_llm_readiness_reports_custom_when_external_llama_cpp_configured() -> None:
    selected_device, ready, reason = derive_llm_device_readiness(
        _preflight(),
        _profile(os_name="linux", arch="amd64"),
        settings=_llm_settings(
            llama_cpp_managed_explicit=True,
            llama_cpp_managed=False,
            llama_cpp_base_url_explicit=True,
            llama_cpp_base_url="http://localhost:9000",
        ),
    )

    assert selected_device == "custom"
    assert ready is False
    assert "external llama.cpp" in reason


def test_llm_readiness_reports_custom_when_ollama_configured() -> None:
    selected_device, ready, reason = derive_llm_device_readiness(
        _preflight(),
        _profile(os_name="linux", arch="amd64"),
        settings=_llm_settings(use_ollama=True),
    )

    assert selected_device == "custom"
    assert ready is False
    assert "ollama" in reason


def test_llm_readiness_delegates_to_catalog_when_nothing_customized(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.models.llm_selection.select_llm_model",
        lambda route, profile, settings=None: SimpleNamespace(model_id="fake-model"),
    )
    monkeypatch.setattr(
        "backend.app.models.llm_profiles.resolve_llm_serve_profile",
        lambda *args, **kwargs: SimpleNamespace(
            accelerator="gpu.cuda",
            degraded_reason=None,
            selected_reason="selected current-host gpu.cuda serve profile",
        ),
    )

    selected_device, ready, reason = derive_llm_device_readiness(
        _preflight(),
        _profile(os_name="windows", arch="amd64", gpu_vendor="nvidia", gpu_available=True, cuda_available=True),
        settings=_llm_settings(),
    )

    assert (selected_device, ready) == ("gpu.cuda", True)
    assert reason == "selected current-host gpu.cuda serve profile"


def test_llm_readiness_reports_catalog_degraded_reason(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.models.llm_selection.select_llm_model",
        lambda route, profile, settings=None: SimpleNamespace(model_id="fake-model"),
    )
    monkeypatch.setattr(
        "backend.app.models.llm_profiles.resolve_llm_serve_profile",
        lambda *args, **kwargs: SimpleNamespace(
            accelerator="gpu.opencl.adreno",
            degraded_reason="Degraded-no-local-model-artifact",
            selected_reason="selected current-host gpu.opencl.adreno serve profile",
        ),
    )

    selected_device, ready, reason = derive_llm_device_readiness(
        _preflight(),
        _profile(os_name="windows", arch="arm64", gpu_vendor="qualcomm", gpu_available=True),
        settings=_llm_settings(),
    )

    assert (selected_device, ready) == ("cpu", False)
    assert reason == "Degraded-no-local-model-artifact"


def test_llm_readiness_reports_catalog_error(monkeypatch) -> None:
    from backend.app.models.catalog import ModelCatalogError

    def _raise(*args, **kwargs):
        raise ModelCatalogError("llm catalog is misconfigured")

    monkeypatch.setattr("backend.app.models.llm_selection.select_llm_model", _raise)

    selected_device, ready, reason = derive_llm_device_readiness(
        _preflight(),
        _profile(os_name="linux", arch="amd64"),
        settings=_llm_settings(),
    )

    assert (selected_device, ready, reason) == ("cpu", False, "llm catalog is misconfigured")


def test_wake_readiness_selects_cpu_when_openwakeword_imported() -> None:
    selected_device, ready, reason = derive_wake_device_readiness(
        _preflight("import:openwakeword"),
        _profile(os_name="windows", arch="amd64"),
    )

    assert (selected_device, ready) == ("cpu", True)
    assert "import:openwakeword" in reason


def test_linux_wake_readiness_degrades_when_openwakeword_import_is_missing() -> None:
    selected_device, ready, reason = derive_wake_device_readiness(
        _preflight(),
        _profile(os_name="linux", arch="amd64"),
    )

    assert (selected_device, ready) == ("cpu", False)
    assert reason == "import:openwakeword:MISSING; cpu unavailable in slice_a"


def test_readiness_reason_strings_cite_evidence_tokens_verbatim() -> None:
    selected_device, ready, reason = derive_stt_device_readiness(
        _preflight("import:onnxruntime", "ep:DmlExecutionProvider"),
        _profile(os_name="windows", arch="amd64", gpu_available=True),
    )

    assert selected_device == "directml"
    assert ready is True
    assert "ep:DmlExecutionProvider" in reason


def test_tts_readiness_selects_qnn_when_qnn_ep_proven() -> None:
    selected_device, ready, reason = derive_tts_device_readiness(
        _preflight("import:onnxruntime-qnn", "ep:QNNExecutionProvider", "dll:QnnHtp"),
        _profile(
            os_name="windows",
            arch="arm64",
            npu_available=True,
            npu_vendor="qualcomm",
        ),
    )

    assert (selected_device, ready) == ("qnn", True)
    assert "qnn prerequisites proven" in reason


def test_tts_readiness_falls_back_to_cpu_when_qnn_ep_missing_on_npu() -> None:
    selected_device, ready, reason = derive_tts_device_readiness(
        _preflight("import:kokoro_onnx"),
        _profile(
            os_name="windows",
            arch="arm64",
            npu_available=True,
            npu_vendor="qualcomm",
        ),
    )

    assert (selected_device, ready) == ("cpu", True)
    assert "provider-override-missing" in reason
