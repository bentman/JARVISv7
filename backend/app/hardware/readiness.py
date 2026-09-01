from __future__ import annotations

from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.core.settings import Settings, load_settings
from backend.app.hardware.preflight import PreflightResult

LLM_DEFAULT_ROUTE = "voice_chat"


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

    # CUDA selection requires matching vendor, capability, and provider evidence.
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

    # QNN on ARM64 Activation:
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
        return ("cpu", True, "provider-override-missing: QNNExecutionProvider unavailable to kokoro_onnx (boundary preserved)")

    if _has_token(preflight, "import:kokoro_onnx"):
        return ("cpu", True, _reason_for_cpu("import:kokoro_onnx", "cpu"))
    return ("cpu", False, "import:kokoro_onnx:MISSING; cpu unavailable in slice_a")


def _custom_llm_provider_reason(settings: Settings) -> tuple[str, str] | None:
    """Detect an operator-customized LLM provider that supersedes llm.yaml.

    Returns (device_label, reason) when a non-catalog provider is configured,
    or None when the llm.yaml catalog applies.
    """
    if not settings.use_local_model:
        return ("disabled", "local model disabled (USE_LOCAL_MODEL=false); llm.yaml catalog not applicable")
    if (
        settings.llama_cpp_managed_explicit
        and not settings.llama_cpp_managed
        and settings.llama_cpp_base_url_explicit
        and settings.llama_cpp_base_url.strip()
    ):
        return (
            "custom",
            f"external llama.cpp endpoint configured ({settings.llama_cpp_base_url}); "
            "llm.yaml catalog not applicable, reported as custom",
        )
    if settings.use_ollama:
        return (
            "custom",
            f"ollama provider configured ({settings.ollama_base_url}); "
            "llm.yaml catalog not applicable, reported as custom",
        )
    return None


def derive_llm_device_readiness(
    preflight: PreflightResult,
    profile: HardwareProfile,
    *,
    settings: Settings | None = None,
    flags: CapabilityFlags | None = None,
) -> tuple[str, bool, str]:
    from backend.app.hardware.profiler import derive_capability_flags
    from backend.app.models.catalog import ModelCatalogError
    from backend.app.models.llm_profiles import resolve_llm_serve_profile
    from backend.app.models.llm_selection import select_llm_model

    resolved_settings = settings or load_settings()

    custom = _custom_llm_provider_reason(resolved_settings)
    if custom is not None:
        device, reason = custom
        return (device, False, reason)

    resolved_flags = flags or derive_capability_flags(profile)
    try:
        model_selection = select_llm_model(LLM_DEFAULT_ROUTE, profile, settings=resolved_settings)
        resolution = resolve_llm_serve_profile(
            LLM_DEFAULT_ROUTE,
            profile,
            preflight,
            settings=resolved_settings,
            flags=resolved_flags,
            model_name=model_selection.model_id,
        )
    except ModelCatalogError as exc:
        return ("cpu", False, str(exc))

    if resolution.degraded_reason:
        return ("cpu", False, resolution.degraded_reason)
    return (resolution.accelerator, True, resolution.selected_reason)


def derive_wake_device_readiness(
    preflight: PreflightResult,
    profile: HardwareProfile,
) -> tuple[str, bool, str]:
    if _has_token(preflight, "import:openwakeword"):
        return ("cpu", True, _reason_for_cpu("import:openwakeword", "cpu"))
    return ("cpu", False, "import:openwakeword:MISSING; cpu unavailable in slice_a")
