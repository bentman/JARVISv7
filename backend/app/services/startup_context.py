from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.core.capabilities import FullCapabilityReport, HardwareProfile
    from backend.app.hardware.preflight import PreflightResult


ReadinessMap = dict[str, tuple[str, bool, str]]


@dataclass(slots=True)
class ProfileContext:
    report: FullCapabilityReport
    profile: HardwareProfile
    extras: list[str]


@dataclass(slots=True)
class StartupContext:
    report: FullCapabilityReport
    profile: HardwareProfile
    extras: list[str]
    preflight: PreflightResult
    readiness: ReadinessMap


def load_profile_context() -> ProfileContext:
    from backend.app.hardware.profiler import run_profiler
    from backend.app.hardware.provisioning import resolve_required_extras

    report = run_profiler()
    profile = report.profile
    extras = resolve_required_extras(profile)
    return ProfileContext(report=report, profile=profile, extras=extras)


def derive_readiness_map(preflight: PreflightResult, profile: HardwareProfile) -> ReadinessMap:
    from backend.app.hardware.readiness import (
        derive_llm_device_readiness,
        derive_stt_device_readiness,
        derive_tts_device_readiness,
        derive_wake_device_readiness,
    )

    return {
        "stt": derive_stt_device_readiness(preflight, profile),
        "tts": derive_tts_device_readiness(preflight, profile),
        "llm": derive_llm_device_readiness(preflight, profile),
        "wake": derive_wake_device_readiness(preflight, profile),
    }


def complete_startup_context(context: ProfileContext) -> StartupContext:
    from backend.app.hardware.preflight import run_preflight

    preflight = run_preflight(context.profile, context.extras)
    return StartupContext(
        report=context.report,
        profile=context.profile,
        extras=context.extras,
        preflight=preflight,
        readiness=derive_readiness_map(preflight, context.profile),
    )


def load_startup_context() -> StartupContext:
    return complete_startup_context(load_profile_context())


def readiness_summary(context: StartupContext) -> str:
    status = "ready" if not context.preflight.probe_errors else "degraded"
    return f"{status}; tokens={len(context.preflight.tokens)}"


def selected_path_readiness_summary(context: StartupContext) -> str:
    stt_device, stt_ready, _ = context.readiness["stt"]
    _tts_device, tts_ready, _ = context.readiness["tts"]
    _wake_device, wake_ready, _ = context.readiness["wake"]

    selected_path_ready = stt_ready and tts_ready and wake_ready
    stt_path_probe_error = stt_device == "qnn" and any(
        key.startswith("onnxruntime.qnn") or key == "onnxruntime-qnn"
        for key in context.preflight.probe_errors
    )

    status = "ready" if selected_path_ready and not stt_path_probe_error else "degraded"
    return f"{status}; tokens={len(context.preflight.tokens)}"
