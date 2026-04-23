from __future__ import annotations

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.provisioning import resolve_required_extras


def test_resolver_returns_base_plus_arch_for_cpu_only_x64() -> None:
    profile = HardwareProfile(arch="amd64")

    assert resolve_required_extras(profile) == ["hw-cpu-base", "hw-x64-base", "dev"]


def test_resolver_returns_base_plus_arch_for_cpu_only_arm64() -> None:
    profile = HardwareProfile(arch="arm64")

    assert resolve_required_extras(profile) == ["hw-cpu-base", "hw-arm64-base", "dev"]


def test_resolver_adds_cuda_for_nvidia_with_cuda() -> None:
    profile = HardwareProfile(arch="amd64", gpu_available=True, gpu_vendor="nvidia", cuda_available=True)

    assert resolve_required_extras(profile) == [
        "hw-cpu-base",
        "hw-x64-base",
        "hw-gpu-nvidia-cuda",
        "dev",
    ]


def test_resolver_omits_cuda_for_nvidia_without_cuda() -> None:
    profile = HardwareProfile(arch="amd64", gpu_available=True, gpu_vendor="nvidia", cuda_available=False)

    assert resolve_required_extras(profile) == ["hw-cpu-base", "hw-x64-base", "dev"]


def test_resolver_adds_amd_for_amd_gpu() -> None:
    profile = HardwareProfile(arch="amd64", gpu_available=True, gpu_vendor="amd")

    assert resolve_required_extras(profile) == ["hw-cpu-base", "hw-x64-base", "hw-gpu-amd", "dev"]


def test_resolver_adds_intel_for_intel_gpu() -> None:
    profile = HardwareProfile(arch="amd64", gpu_available=True, gpu_vendor="intel")

    assert resolve_required_extras(profile) == ["hw-cpu-base", "hw-x64-base", "hw-gpu-intel", "dev"]


def test_resolver_adds_qnn_for_qualcomm_npu() -> None:
    profile = HardwareProfile(arch="arm64", npu_available=True, npu_vendor="qualcomm")

    assert resolve_required_extras(profile) == [
        "hw-cpu-base",
        "hw-arm64-base",
        "hw-npu-qualcomm-qnn",
        "dev",
    ]


def test_resolver_omits_qnn_for_non_qualcomm_npu() -> None:
    profile = HardwareProfile(arch="arm64", npu_available=True, npu_vendor="intel")

    assert resolve_required_extras(profile) == ["hw-cpu-base", "hw-arm64-base", "dev"]


def test_resolver_never_adds_porcupine_without_opt_in() -> None:
    profile = HardwareProfile(arch="amd64")

    assert "hw-wake-porcupine" not in resolve_required_extras(profile)


def test_resolver_deterministic_order_for_same_profile() -> None:
    profile = HardwareProfile(
        arch="amd64",
        gpu_available=True,
        gpu_vendor="nvidia",
        cuda_available=True,
        npu_available=True,
        npu_vendor="qualcomm",
    )

    first = resolve_required_extras(profile)
    second = resolve_required_extras(profile)

    assert first == second


def test_resolver_dev_extra_always_included() -> None:
    profile = HardwareProfile(arch="amd64")

    assert resolve_required_extras(profile)[-1] == "dev"
