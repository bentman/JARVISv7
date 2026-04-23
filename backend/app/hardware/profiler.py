from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone

from backend.app.core.capabilities import CapabilityFlags, FullCapabilityReport, HardwareProfile
from backend.app.hardware.detectors.cpu_detector import detect_cpu_info
from backend.app.hardware.detectors.cuda_detector import detect_cuda_info
from backend.app.hardware.detectors.gpu_detector import detect_gpu_info
from backend.app.hardware.detectors.memory_detector import detect_memory_info
from backend.app.hardware.detectors.npu_detector import detect_npu_info
from backend.app.hardware.detectors.os_detector import detect_os_info


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _unknown_profile() -> HardwareProfile:
    return HardwareProfile()


def _merge_profile(profile: HardwareProfile, payload: dict[str, object]) -> HardwareProfile:
    data = asdict(profile)
    for key, value in payload.items():
        if key in data:
            data[key] = value
    return HardwareProfile(**data)


def _build_profile_id(profile: HardwareProfile) -> str:
    canonical = asdict(profile).copy()
    canonical.pop("profile_id", None)
    canonical.pop("profiled_at", None)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"profile-{digest}"


def derive_capability_flags(profile: HardwareProfile) -> CapabilityFlags:
    known_platform = profile.os_name in {"windows", "linux", "darwin"}
    cpu_cores = profile.cpu_physical_cores or 0
    memory_total = profile.memory_total_gb or 0.0
    has_gpu = bool(profile.gpu_available)
    has_cuda = bool(profile.cuda_available)
    qnn_available = bool(profile.npu_available and profile.npu_vendor == "qualcomm")
    directml_candidate = profile.os_name == "windows" and has_gpu

    supports_local_stt = known_platform and memory_total >= 4.0
    supports_local_tts = known_platform and memory_total >= 4.0
    supports_local_llm = known_platform and cpu_cores >= 4 and memory_total >= 8.0
    supports_gpu_llm = has_gpu
    supports_cuda_llm = has_cuda
    supports_wake_word = known_platform
    supports_realtime_voice = supports_local_stt and supports_local_tts
    supports_desktop_shell = known_platform
    requires_degraded_mode = not (
        supports_local_llm and supports_local_stt and supports_local_tts and supports_wake_word
    )

    return CapabilityFlags(
        supports_local_llm=supports_local_llm,
        supports_gpu_llm=supports_gpu_llm,
        supports_cuda_llm=supports_cuda_llm,
        supports_local_stt=supports_local_stt,
        supports_local_tts=supports_local_tts,
        supports_wake_word=supports_wake_word,
        supports_realtime_voice=supports_realtime_voice,
        supports_desktop_shell=supports_desktop_shell,
        requires_degraded_mode=requires_degraded_mode,
        qnn_available=qnn_available,
        directml_candidate=directml_candidate,
    )


def run_profiler() -> FullCapabilityReport:
    profile = _unknown_profile()

    detector_payloads = [
        detect_os_info,
        detect_cpu_info,
        detect_memory_info,
        detect_gpu_info,
        detect_cuda_info,
        detect_npu_info,
    ]

    for detector in detector_payloads:
        try:
            payload = detector()
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            profile = _merge_profile(profile, payload)

    profile.profiled_at = _utc_timestamp()
    profile.profile_id = _build_profile_id(profile)
    flags = derive_capability_flags(profile)
    return FullCapabilityReport(profile=profile, flags=flags)
