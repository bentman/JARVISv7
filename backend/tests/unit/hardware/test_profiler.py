from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.hardware import profiler as profiler_module
from backend.app.hardware.detectors import cpu_detector, cuda_detector, gpu_detector, memory_detector, npu_detector, os_detector


def test_os_detector_returns_required_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os_detector.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_detector.platform, "version", lambda: "10.0.22631")
    monkeypatch.setattr(os_detector.psutil, "sensors_battery", lambda: None)
    monkeypatch.setattr(os_detector, "_run_command", lambda command: "")

    result = os_detector.detect_os_info()

    assert result["os_name"] == "windows"
    assert result["os_version"] == "10.0.22631"
    assert result["device_class"] == "unknown"


@pytest.mark.parametrize(
    ("machine", "expected"),
    [
        ("AMD64", "amd64"),
        ("x86_64", "amd64"),
        ("ARM64", "arm64"),
        ("aarch64", "arm64"),
    ],
)
def test_cpu_detector_normalizes_arch_aliases(
    monkeypatch: pytest.MonkeyPatch, machine: str, expected: str
) -> None:
    monkeypatch.setattr(cpu_detector.platform, "machine", lambda: machine)
    monkeypatch.setattr(cpu_detector.platform, "processor", lambda: "Test CPU")
    monkeypatch.setattr(cpu_detector.psutil, "cpu_count", lambda logical=True: 8 if logical else 4)
    monkeypatch.setattr(cpu_detector.psutil, "cpu_freq", lambda: SimpleNamespace(max=4200.0))

    result = cpu_detector.detect_cpu_info()

    assert result["arch"] == expected
    assert result["cpu_name"] == "Test CPU"
    assert result["cpu_physical_cores"] == 4
    assert result["cpu_logical_cores"] == 8


def test_memory_detector_returns_positive_totals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        memory_detector.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=16 * 1024**3, available=10 * 1024**3),
    )

    result = memory_detector.detect_memory_info()

    assert result["memory_total_gb"] == 16.0
    assert result["memory_available_gb"] == 10.0


def test_gpu_detector_returns_not_available_when_no_vendor_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gpu_detector, "_run_command", lambda command: "")
    monkeypatch.setattr(gpu_detector.platform, "system", lambda: "Windows")

    result = gpu_detector.detect_gpu_info()

    assert result["gpu_available"] is False
    assert result["gpu_vendor"] is None


def test_cuda_detector_returns_false_when_nvidia_smi_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cuda_detector, "_run_command", lambda command: "")

    result = cuda_detector.detect_cuda_info()

    assert result["cuda_available"] is False
    assert result["cuda_version"] is None


def test_npu_detector_returns_false_when_no_npu_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(npu_detector.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(npu_detector.platform, "processor", lambda: "Generic CPU")
    monkeypatch.setattr(npu_detector.platform, "system", lambda: "Windows")
    monkeypatch.setattr(npu_detector, "_run_command", lambda command: "")

    result = npu_detector.detect_npu_info()

    assert result["npu_available"] is False
    assert result["npu_vendor"] is None
    assert result["npu_tops"] is None


def test_profiler_composes_all_detectors_into_full_report(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(profiler_module, "_utc_timestamp", lambda: "2026-04-23T15:00:00Z")
    monkeypatch.setattr(
        profiler_module,
        "detect_os_info",
        lambda: {"os_name": "windows", "os_version": "11", "device_class": "desktop"},
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_cpu_info",
        lambda: {
            "cpu_name": "Test CPU",
            "cpu_physical_cores": 8,
            "cpu_logical_cores": 16,
            "cpu_max_freq_mhz": 4200.0,
            "arch": "amd64",
        },
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_memory_info",
        lambda: {"memory_total_gb": 32.0, "memory_available_gb": 24.0},
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_gpu_info",
        lambda: {
            "gpu_available": True,
            "gpu_name": "NVIDIA RTX",
            "gpu_vendor": "nvidia",
            "gpu_vram_gb": 8.0,
            "gpu_vram_source": "nvidia-smi",
        },
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_cuda_info",
        lambda: {"cuda_available": True, "cuda_version": "550.54"},
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_npu_info",
        lambda: {"npu_available": False, "npu_vendor": None, "npu_tops": None},
    )

    report = profiler_module.run_profiler()

    assert report.profile.os_name == "windows"
    assert report.profile.arch == "amd64"
    assert report.profile.profiled_at == "2026-04-23T15:00:00Z"
    assert report.profile.profile_id.startswith("profile-")
    assert report.flags.supports_cuda_llm is True
    assert report.flags.supports_gpu_llm is True
    assert report.flags.supports_local_llm is True
    assert report.flags.qnn_available is False


def test_profiler_substitutes_unknown_values_on_detector_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(profiler_module, "_utc_timestamp", lambda: "2026-04-23T15:00:00Z")
    monkeypatch.setattr(profiler_module, "detect_os_info", lambda: {"os_name": "windows"})
    monkeypatch.setattr(profiler_module, "detect_cpu_info", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(
        profiler_module,
        "detect_memory_info",
        lambda: {"memory_total_gb": 8.0, "memory_available_gb": 4.0},
    )
    monkeypatch.setattr(profiler_module, "detect_gpu_info", lambda: {})
    monkeypatch.setattr(profiler_module, "detect_cuda_info", lambda: {})
    monkeypatch.setattr(profiler_module, "detect_npu_info", lambda: {})

    report = profiler_module.run_profiler()

    assert report.profile.os_name == "windows"
    assert report.profile.arch == "unknown"
    assert report.profile.cpu_name == "unknown"
    assert report.profile.gpu_available is False
    assert report.profile.profile_id.startswith("profile-")


def test_profiler_capability_flags_for_synthetic_cuda_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(profiler_module, "_utc_timestamp", lambda: "2026-04-23T15:00:00Z")
    monkeypatch.setattr(
        profiler_module,
        "detect_os_info",
        lambda: {"os_name": "windows", "os_version": "11", "device_class": "desktop"},
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_cpu_info",
        lambda: {
            "cpu_name": "Test CPU",
            "cpu_physical_cores": 8,
            "cpu_logical_cores": 16,
            "cpu_max_freq_mhz": 4200.0,
            "arch": "amd64",
        },
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_memory_info",
        lambda: {"memory_total_gb": 32.0, "memory_available_gb": 24.0},
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_gpu_info",
        lambda: {
            "gpu_available": True,
            "gpu_name": "NVIDIA RTX",
            "gpu_vendor": "nvidia",
            "gpu_vram_gb": 8.0,
            "gpu_vram_source": "nvidia-smi",
        },
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_cuda_info",
        lambda: {"cuda_available": True, "cuda_version": "550.54"},
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_npu_info",
        lambda: {"npu_available": False, "npu_vendor": None, "npu_tops": None},
    )

    report = profiler_module.run_profiler()

    assert report.flags.supports_cuda_llm is True
    assert report.flags.supports_gpu_llm is True
    assert report.flags.directml_candidate is True
    assert report.flags.qnn_available is False
    assert report.flags.requires_degraded_mode is False


def test_profiler_capability_flags_for_synthetic_arm64_qualcomm_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(profiler_module, "_utc_timestamp", lambda: "2026-04-23T15:00:00Z")
    monkeypatch.setattr(
        profiler_module,
        "detect_os_info",
        lambda: {"os_name": "windows", "os_version": "11", "device_class": "laptop"},
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_cpu_info",
        lambda: {
            "cpu_name": "Test ARM CPU",
            "cpu_physical_cores": 8,
            "cpu_logical_cores": 8,
            "cpu_max_freq_mhz": 3000.0,
            "arch": "arm64",
        },
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_memory_info",
        lambda: {"memory_total_gb": 16.0, "memory_available_gb": 12.0},
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_gpu_info",
        lambda: {
            "gpu_available": False,
            "gpu_name": None,
            "gpu_vendor": None,
            "gpu_vram_gb": None,
            "gpu_vram_source": None,
        },
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_cuda_info",
        lambda: {"cuda_available": False, "cuda_version": None},
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_npu_info",
        lambda: {"npu_available": True, "npu_vendor": "qualcomm", "npu_tops": 45.0},
    )

    report = profiler_module.run_profiler()

    assert report.profile.arch == "arm64"
    assert report.flags.qnn_available is True
    assert report.flags.supports_cuda_llm is False
    assert report.flags.directml_candidate is False
    assert report.flags.supports_local_llm is True


def test_profile_id_is_deterministic_for_same_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        profiler_module,
        "detect_os_info",
        lambda: {"os_name": "windows", "os_version": "11", "device_class": "desktop"},
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_cpu_info",
        lambda: {
            "cpu_name": "Test CPU",
            "cpu_physical_cores": 8,
            "cpu_logical_cores": 16,
            "cpu_max_freq_mhz": 4200.0,
            "arch": "amd64",
        },
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_memory_info",
        lambda: {"memory_total_gb": 32.0, "memory_available_gb": 24.0},
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_gpu_info",
        lambda: {
            "gpu_available": True,
            "gpu_name": "NVIDIA RTX",
            "gpu_vendor": "nvidia",
            "gpu_vram_gb": 8.0,
            "gpu_vram_source": "nvidia-smi",
        },
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_cuda_info",
        lambda: {"cuda_available": True, "cuda_version": "550.54"},
    )
    monkeypatch.setattr(
        profiler_module,
        "detect_npu_info",
        lambda: {"npu_available": False, "npu_vendor": None, "npu_tops": None},
    )

    first = profiler_module.run_profiler()
    second = profiler_module.run_profiler()

    assert first.profile.profile_id == second.profile.profile_id
    assert first.profile.profile_id.startswith("profile-")
