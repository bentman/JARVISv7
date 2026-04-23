from __future__ import annotations

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.hardware.readiness import (
    derive_llm_device_readiness,
    derive_stt_device_readiness,
    derive_tts_device_readiness,
    derive_wake_device_readiness,
)


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


def test_llm_readiness_is_pending_in_slice_a_reports_unavailable_with_reason() -> None:
    selected_device, ready, reason = derive_llm_device_readiness(
        _preflight("import:onnxruntime"),
        _profile(os_name="linux", arch="amd64"),
    )

    assert (selected_device, ready) == ("cpu", False)
    assert "deferred in slice_a" in reason


def test_wake_readiness_selects_cpu_when_openwakeword_imported() -> None:
    selected_device, ready, reason = derive_wake_device_readiness(
        _preflight("import:openwakeword"),
        _profile(os_name="windows", arch="amd64"),
    )

    assert (selected_device, ready) == ("cpu", True)
    assert "import:openwakeword" in reason


def test_readiness_reason_strings_cite_evidence_tokens_verbatim() -> None:
    selected_device, ready, reason = derive_stt_device_readiness(
        _preflight("import:onnxruntime", "ep:DmlExecutionProvider"),
        _profile(os_name="windows", arch="amd64", gpu_available=True),
    )

    assert selected_device == "directml"
    assert ready is True
    assert "ep:DmlExecutionProvider" in reason
