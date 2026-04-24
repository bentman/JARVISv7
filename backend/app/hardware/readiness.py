from __future__ import annotations

from backend.app.core.capabilities import HardwareProfile
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
            return ("cpu", True, "qnn proven but inference runtime pending (slice H.2); selecting cpu")
        return ("cpu", True, "qnn defined; STT QNN inference pending H.2")

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

    if _has_token(preflight, "import:onnxruntime"):
        return ("cpu", True, _reason_for_cpu("import:onnxruntime", "cpu"))

    return ("cpu", False, "import:onnxruntime:MISSING; cpu unavailable in slice_a")


def derive_tts_device_readiness(
    preflight: PreflightResult,
    profile: HardwareProfile,
) -> tuple[str, bool, str]:
    if _has_token(preflight, "import:kokoro_onnx"):
        return ("cpu", True, _reason_for_cpu("import:kokoro_onnx", "cpu"))
    return ("cpu", False, "import:kokoro_onnx:MISSING; cpu unavailable in slice_a")


def derive_llm_device_readiness(
    preflight: PreflightResult,
    profile: HardwareProfile,
) -> tuple[str, bool, str]:
    if _has_token(preflight, "import:onnxruntime"):
        return ("cpu", False, "llm runtime deferred in slice_a; import:onnxruntime present")
    return ("cpu", False, "llm runtime deferred in slice_a; import:onnxruntime:MISSING")


def derive_wake_device_readiness(
    preflight: PreflightResult,
    profile: HardwareProfile,
) -> tuple[str, bool, str]:
    if _has_token(preflight, "import:openwakeword"):
        return ("cpu", True, _reason_for_cpu("import:openwakeword", "cpu"))
    return ("cpu", False, "import:openwakeword:MISSING; cpu unavailable in slice_a")
