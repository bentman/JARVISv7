from __future__ import annotations

from backend.app.core.capabilities import HardwareProfile
from backend.app.models.catalog import get_model_path
from backend.app.hardware.preflight import PreflightResult


def _has_token(preflight: PreflightResult, token: str) -> bool:
    return token in preflight.tokens


def _reason_for_cpu(import_token: str, device_name: str) -> str:
    return f"{import_token} present; selecting {device_name}"


def derive_stt_device_readiness(
    preflight: PreflightResult,
    profile: HardwareProfile,
) -> tuple[str, bool, str]:
    if profile.npu_available and profile.npu_vendor == "qualcomm":
        qnn_tokens_present = all(
            _has_token(preflight, token)
            for token in (
                "import:onnxruntime-qnn",
                "ep:QNNExecutionProvider",
                "dll:QnnHtp",
            )
        )
        if qnn_tokens_present:
            return ("qnn", True, "qnn prerequisites proven; selecting qnn")
        return ("cpu", True, "selecting cpu")

    # x64 NVIDIA path (I.2 normalization, H.4 baseline):
    # prefer CUDA only when vendor/capability/provider evidence all agree.
    if (
        profile.gpu_vendor == "nvidia"
        and profile.cuda_available
        and _has_token(preflight, "ep:CUDAExecutionProvider")
    ):
        return ("cuda", True, "ep:CUDAExecutionProvider proven; selecting cuda")

    # x64 Windows DirectML slot remains defined for deterministic ordering,
    # but current installed provider evidence does not activate it.
    if (
        profile.os_name == "windows"
        and profile.gpu_available
        and _has_token(preflight, "ep:DmlExecutionProvider")
    ):
        return ("directml", True, "ep:DmlExecutionProvider proven; selecting directml")

    # Baseline fallback path after accelerated branches are not proven.
    if _has_token(preflight, "import:onnxruntime"):
        return ("cpu", True, _reason_for_cpu("import:onnxruntime", "cpu"))

    return ("cpu", False, "import:onnxruntime:MISSING; cpu unavailable in slice_a")


def derive_tts_device_readiness(
    preflight: PreflightResult,
    profile: HardwareProfile,
) -> tuple[str, bool, str]:
    if (
        profile.gpu_vendor == "nvidia"
        and profile.cuda_available
        and _has_token(preflight, "ep:CUDAExecutionProvider")
    ):
        return ("cuda", True, "ep:CUDAExecutionProvider proven; selecting cuda")

    if (
        profile.os_name == "windows"
        and profile.gpu_available
        and _has_token(preflight, "ep:DmlExecutionProvider")
    ):
        return ("directml", True, "ep:DmlExecutionProvider proven; selecting directml")

    # QNN on ARM64 boundary preserved: fail closed to CPU
    if profile.npu_available and profile.npu_vendor == "qualcomm":
        return ("cpu", True, "provider-override-missing: QNNExecutionProvider unavailable to kokoro_onnx (boundary preserved)")

    if _has_token(preflight, "import:kokoro_onnx"):
        return ("cpu", True, _reason_for_cpu("import:kokoro_onnx", "cpu"))
    return ("cpu", False, "import:kokoro_onnx:MISSING; cpu unavailable in slice_a")


def derive_llm_device_readiness(
    preflight: PreflightResult,
    profile: HardwareProfile,
) -> tuple[str, bool, str]:
    if (
        profile.os_name == "windows"
        and profile.arch == "arm64"
        and profile.gpu_vendor == "qualcomm"
        and profile.gpu_available
        and _has_token(preflight, "opencl:adreno")
    ):
        return ("gpu.opencl.adreno", True, "opencl:adreno proven; selecting gpu.opencl.adreno")
    if _has_token(preflight, "opencl:adreno:MISSING"):
        return ("cpu", False, "opencl:adreno:MISSING; local runtime unavailable")
    return ("cpu", False, "local runtime unavailable")


def derive_wake_device_readiness(
    preflight: PreflightResult,
    profile: HardwareProfile,
) -> tuple[str, bool, str]:
    if _has_token(preflight, "import:openwakeword"):
        return ("cpu", True, _reason_for_cpu("import:openwakeword", "cpu"))
    return ("cpu", False, "import:openwakeword:MISSING; cpu unavailable in slice_a")
