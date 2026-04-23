from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.core.capabilities import HardwareProfile


_REQUIREMENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]+")


_EXTRA_REQUIREMENT_NAMES: dict[str, tuple[str, ...]] = {
    "hw-cpu-base": (),
    "hw-x64-base": ("onnxruntime", "onnx-asr", "kokoro-onnx", "openwakeword"),
    "hw-arm64-base": ("onnxruntime", "onnx-asr", "kokoro-onnx", "openwakeword"),
    "hw-gpu-nvidia-cuda": ("onnxruntime-gpu",),
    "hw-gpu-amd": ("onnxruntime-directml",),
    "hw-gpu-intel": ("onnxruntime-directml",),
    "hw-npu-qualcomm-qnn": ("onnxruntime-qnn",),
    "hw-wake-porcupine": (),
    "dev": ("pytest", "pytest-cov", "pytest-asyncio", "ruff", "mypy", "pre-commit"),
}


def _requirement_name(requirement: str) -> str:
    candidate = requirement.split(";", 1)[0].strip()
    match = _REQUIREMENT_NAME_PATTERN.match(candidate)
    if match is None:
        return candidate
    name = match.group(0)
    return name.split("[", 1)[0].strip().lower()


def _extra_reason(profile: HardwareProfile, extra: str) -> str:
    if extra == "hw-cpu-base":
        return "cpu baseline always included"
    if extra == "hw-x64-base":
        return f"arch={profile.arch}"
    if extra == "hw-arm64-base":
        return f"arch={profile.arch}"
    if extra == "hw-gpu-nvidia-cuda":
        return "nvidia gpu with cuda available"
    if extra == "hw-gpu-amd":
        return "amd gpu present"
    if extra == "hw-gpu-intel":
        return "intel gpu present"
    if extra == "hw-npu-qualcomm-qnn":
        return "qualcomm npu present"
    if extra == "hw-wake-porcupine":
        return "operator opt-in"
    if extra == "dev":
        return "developer tooling baseline"
    return "selected by resolver"


def resolve_required_extras(
    profile: HardwareProfile,
    include_porcupine: bool = False,
) -> list[str]:
    extras: list[str] = ["hw-cpu-base"]

    if profile.arch == "arm64":
        extras.append("hw-arm64-base")
    elif profile.arch == "amd64":
        extras.append("hw-x64-base")

    if profile.gpu_available and profile.gpu_vendor == "nvidia" and profile.cuda_available:
        extras.append("hw-gpu-nvidia-cuda")
    if profile.gpu_available and profile.gpu_vendor == "amd":
        extras.append("hw-gpu-amd")
    if profile.gpu_available and profile.gpu_vendor == "intel":
        extras.append("hw-gpu-intel")
    if profile.npu_available and profile.npu_vendor == "qualcomm":
        extras.append("hw-npu-qualcomm-qnn")
    if include_porcupine:
        extras.append("hw-wake-porcupine")

    extras.append("dev")
    return extras


def explain_required_extras(
    profile: HardwareProfile,
    include_porcupine: bool = False,
) -> list[tuple[str, str]]:
    return [
        (extra, _extra_reason(profile, extra))
        for extra in resolve_required_extras(profile, include_porcupine)
    ]


def resolve_required_requirement_names(
    profile: HardwareProfile,
    include_porcupine: bool = False,
) -> list[str]:
    requirement_names: list[str] = []
    for extra in resolve_required_extras(profile, include_porcupine):
        for requirement in _EXTRA_REQUIREMENT_NAMES.get(extra, ()):
            requirement_name = _requirement_name(requirement)
            if requirement_name not in requirement_names:
                requirement_names.append(requirement_name)
    return requirement_names
