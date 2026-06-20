from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.core.settings import Settings
from backend.app.hardware.preflight import PreflightResult
from backend.app.models.catalog import ModelCatalogError, ModelEntry
from backend.app.models.llm_profiles import resolve_llm_serve_profile


def _entry(tmp_path: Path) -> ModelEntry:
    model_file = tmp_path / "models" / "assistant-small-q4" / "model.gguf"
    return ModelEntry(
        family="llm",
        name="assistant-small-q4",
        config={
            "local_path": str(model_file),
            "routes": [
                "voice_chat",
                "text_chat",
                "research",
                "code_plan",
                "tool_plan",
                "agent_plan_disabled",
            ],
            "generation_defaults": {
                "temperature": 0.4,
                "max_tokens": 256,
            },
            "serve_profiles": {
                "hardware_profiles": {
                    "windows_amd64_cpu": {
                        "profile_id": "windows_amd64_cpu",
                        "os": "windows",
                        "arch": "amd64",
                        "provisioning_extras": ["hw-cpu-base", "hw-x64-base", "hw-x64-ort-cpu"],
                        "accelerator": "cpu",
                        "runtime_artifact": {
                            "source": {"type": "pending-pinned-release", "reason": "S-G1-pending"},
                            "binary_path": str(tmp_path / "bin" / "amd64-cpu" / "llama-server.exe"),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(tmp_path / "bin" / "amd64-cpu" / "llama-server.exe"),
                        "base_url": "http://127.0.0.1:8080",
                        "launch": {
                            "ctx_size": 4096,
                            "gpu_layers": 0,
                        },
                    },
                    "windows_arm64_cpu": {
                        "profile_id": "windows_arm64_cpu",
                        "os": "windows",
                        "arch": "arm64",
                        "provisioning_extras": ["hw-cpu-base", "hw-arm64-base", "hw-arm64-ort-cpu"],
                        "accelerator": "cpu",
                        "runtime_artifact": {
                            "source": {"type": "pending-pinned-release", "reason": "S-G1-pending"},
                            "binary_path": str(tmp_path / "bin" / "arm64-cpu" / "llama-server.exe"),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(tmp_path / "bin" / "arm64-cpu" / "llama-server.exe"),
                        "base_url": "http://127.0.0.1:8080",
                        "launch": {
                            "ctx_size": 4096,
                            "gpu_layers": 0,
                        },
                    },
                    "windows_amd64_gpu_nvidia_cuda": {
                        "profile_id": "windows_amd64_gpu_nvidia_cuda",
                        "os": "windows",
                        "arch": "amd64",
                        "provisioning_extras": ["hw-gpu-nvidia-cuda"],
                        "accelerator": "gpu.cuda",
                        "runtime_artifact": {
                            "source": {"type": "pending-pinned-release", "reason": "S-G1-pending"},
                            "binary_path": str(tmp_path / "bin" / "amd64-cuda" / "llama-server.exe"),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(tmp_path / "bin" / "amd64-cuda" / "llama-server.exe"),
                        "close_if_unavailable": "Degraded-accelerator-unavailable",
                        "launch": {
                            "ctx_size": 4096,
                            "gpu_layers": "auto",
                        },
                    },
                    "windows_amd64_gpu_amd": {
                        "profile_id": "windows_amd64_gpu_amd",
                        "os": "windows",
                        "arch": "amd64",
                        "provisioning_extras": ["hw-gpu-amd"],
                        "accelerator": "gpu.vulkan",
                        "runtime_artifact": {
                            "source": {
                                "type": "pending-pinned-release",
                                "reason": "S-G1-pending",
                                "candidate_artifact_families": ["vulkan", "hip"],
                            },
                            "binary_path": str(tmp_path / "bin" / "amd64-amd" / "llama-server.exe"),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(tmp_path / "bin" / "amd64-amd" / "llama-server.exe"),
                        "close_if_unavailable": "Degraded-accelerator-unavailable",
                    },
                    "windows_amd64_gpu_intel": {
                        "profile_id": "windows_amd64_gpu_intel",
                        "os": "windows",
                        "arch": "amd64",
                        "provisioning_extras": ["hw-gpu-intel"],
                        "accelerator": "gpu.vulkan",
                        "runtime_artifact": {
                            "source": {
                                "type": "pending-pinned-release",
                                "reason": "S-G1-pending",
                                "candidate_artifact_families": ["vulkan", "openvino", "sycl"],
                            },
                            "binary_path": str(tmp_path / "bin" / "amd64-intel" / "llama-server.exe"),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(tmp_path / "bin" / "amd64-intel" / "llama-server.exe"),
                        "close_if_unavailable": "Degraded-accelerator-unavailable",
                    },
                    "windows_arm64_npu_qualcomm_base": {
                        "profile_id": "windows_arm64_npu_qualcomm_base",
                        "os": "windows",
                        "arch": "arm64",
                        "provisioning_extras": ["hw-npu-qualcomm-qnn"],
                        "accelerator": "npu.hexagon_candidate",
                        "runtime_artifact": {
                            "source": {
                                "type": "pending-viability",
                                "reason": "S-G1-pending",
                                "candidate_runtime_findings": {
                                    "windows_on_snapdragon": "build-package-flow",
                                    "device_examples": ["cpu", "adreno-opencl", "hexagon-htp"],
                                    "release_asset": "none-confirmed",
                                },
                            },
                            "binary_path": str(tmp_path / "bin" / "arm64-hexagon" / "llama-server.exe"),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(tmp_path / "bin" / "arm64-hexagon" / "llama-server.exe"),
                        "close_if_unavailable": "Degraded-accelerator-unavailable",
                    },
                    "windows_arm64_gpu_qualcomm_adreno_opencl": {
                        "profile_id": "windows_arm64_gpu_qualcomm_adreno_opencl",
                        "os": "windows",
                        "arch": "arm64",
                        "provisioning_extras": ["hw-arm64-base"],
                        "accelerator": "gpu.opencl.adreno",
                        "runtime_artifact": {
                            "source": {
                                "type": "build-required",
                                "reason": "no-pinned-release-asset",
                                "upstream": {
                                    "backend": "llama.cpp Adreno OpenCL",
                                    "build_flag": "GGML_OPENCL=ON",
                                    "platform": "Windows on Snapdragon",
                                },
                                "candidate_runtime_findings": {
                                    "windows_on_snapdragon": "build-flow",
                                    "gpu_backend": "adreno-opencl",
                                    "release_asset": "none-confirmed",
                                    "optimized_quantization": "Q4_0",
                                    "current_model_quantization": "Q4_K_M",
                                },
                            },
                            "binary_path": str(tmp_path / "bin" / "arm64-adreno-opencl" / "llama-server.exe"),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(tmp_path / "bin" / "arm64-adreno-opencl" / "llama-server.exe"),
                        "close_if_unavailable": "Degraded-opencl-build-required",
                        "launch": {
                            "ctx_size": 4096,
                            "gpu_layers": "auto",
                        },
                    },
                    "windows_arm64_npu_qualcomm_qnn": {
                        "profile_id": "windows_arm64_npu_qualcomm_qnn",
                        "os": "windows",
                        "arch": "arm64",
                        "provisioning_extras": ["hw-npu-qualcomm-qnn"],
                        "accelerator": "npu.qnn",
                        "runtime_artifact": {
                            "source": {
                                "type": "pending-viability",
                                "reason": "S-G1-pending",
                                "project_label": "npu.qnn",
                                "runtime_mapping": "pending-hexagon-qnn-viability",
                                "candidate_runtime_findings": {
                                    "windows_on_snapdragon": "build-package-flow",
                                    "device_examples": ["cpu", "adreno-opencl", "hexagon-htp"],
                                    "release_asset": "none-confirmed",
                                },
                            },
                            "binary_path": str(tmp_path / "bin" / "arm64-qnn" / "llama-server.exe"),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(tmp_path / "bin" / "arm64-qnn" / "llama-server.exe"),
                        "close_if_unavailable": "Degraded-no-sidecar-binary",
                        "launch": {
                            "ctx_size": 4096,
                            "device": "qnn",
                        },
                    },
                },
            },
        },
    )


def _settings() -> Settings:
    return Settings(
        llama_cpp_base_url="",
        llama_cpp_model_path=None,
        llama_cpp_binary_path=None,
    )


def _preflight(tokens: list[str] | None = None) -> PreflightResult:
    return PreflightResult(tokens=tokens or [], dll_discovery_log=[], probe_errors={})


def test_resolve_windows_amd64_cpu_profile_with_existing_artifacts(tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    entry.local_path.parent.mkdir(parents=True)
    entry.local_path.write_bytes(b"gguf")
    binary_path = tmp_path / "bin" / "amd64-cpu" / "llama-server.exe"
    binary_path.parent.mkdir(parents=True)
    binary_path.write_bytes(b"exe")

    resolution = resolve_llm_serve_profile(
        "voice_chat",
        HardwareProfile(os_name="windows", arch="amd64"),
        _preflight(),
        settings=_settings(),
        entry=entry,
    )

    assert resolution.model_id == "assistant-small-q4"
    assert resolution.route == "voice_chat"
    assert resolution.serve_profile_id == "windows_amd64_cpu"
    assert resolution.local_model_path == entry.local_path
    assert resolution.binary_path == binary_path
    assert resolution.base_url == "http://127.0.0.1:8080"
    assert resolution.accelerator == "cpu"
    assert resolution.launch["gpu_layers"] == 0
    assert resolution.generation_defaults["temperature"] == 0.4
    assert resolution.degraded_reason is None


def test_resolve_windows_arm64_cpu_profile_first(tmp_path: Path) -> None:
    resolution = resolve_llm_serve_profile(
        "text_chat",
        HardwareProfile(os_name="windows", arch="arm64"),
        _preflight(),
        settings=_settings(),
        entry=_entry(tmp_path),
    )

    assert resolution.serve_profile_id == "windows_arm64_cpu"
    assert resolution.accelerator == "cpu"
    assert "selected current-host CPU serve profile windows_arm64_cpu" == resolution.selected_reason
    assert resolution.degraded_reasons == [
        "Degraded-no-local-model-artifact",
        "Degraded-no-sidecar-binary",
    ]


def test_resolve_reports_amd64_cuda_as_degraded_until_evidence_exists(tmp_path: Path) -> None:
    resolution = resolve_llm_serve_profile(
        "research",
        HardwareProfile(
            os_name="windows",
            arch="amd64",
            gpu_available=True,
            gpu_vendor="nvidia",
            cuda_available=True,
        ),
        _preflight(),
        settings=_settings(),
        flags=CapabilityFlags(supports_cuda_llm=True),
        entry=_entry(tmp_path),
    )

    assert [(candidate.profile_id, candidate.reason) for candidate in resolution.degraded_candidates] == [
        ("windows_amd64_gpu_nvidia_cuda", "Degraded-accelerator-unavailable"),
        ("windows_amd64_gpu_amd", "Degraded-accelerator-unavailable"),
        ("windows_amd64_gpu_intel", "Degraded-accelerator-unavailable"),
    ]


def test_non_cuda_gpu_profiles_do_not_block_cpu_fallback(tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    entry.local_path.parent.mkdir(parents=True)
    entry.local_path.write_bytes(b"gguf")
    cpu_binary = tmp_path / "bin" / "amd64-cpu" / "llama-server.exe"
    cpu_binary.parent.mkdir(parents=True)
    cpu_binary.write_bytes(b"exe")

    resolution = resolve_llm_serve_profile(
        "research",
        HardwareProfile(os_name="windows", arch="amd64", gpu_available=True, gpu_vendor="amd"),
        _preflight(),
        settings=_settings(),
        entry=entry,
    )

    assert resolution.serve_profile_id == "windows_amd64_cpu"
    assert resolution.accelerator == "cpu"
    assert resolution.binary_path == cpu_binary
    assert resolution.degraded_reason is None
    assert [(candidate.profile_id, candidate.reason) for candidate in resolution.degraded_candidates] == [
        ("windows_amd64_gpu_nvidia_cuda", "Degraded-accelerator-unavailable"),
        ("windows_amd64_gpu_amd", "Degraded-accelerator-unavailable"),
        ("windows_amd64_gpu_intel", "Degraded-accelerator-unavailable"),
    ]


def test_non_cuda_gpu_profiles_are_not_selected_for_unrelated_hardware(tmp_path: Path) -> None:
    resolution = resolve_llm_serve_profile(
        "research",
        HardwareProfile(os_name="windows", arch="arm64"),
        _preflight(),
        settings=_settings(),
        entry=_entry(tmp_path),
    )

    assert resolution.serve_profile_id == "windows_arm64_cpu"
    assert {candidate.profile_id for candidate in resolution.degraded_candidates} == {
        "windows_arm64_gpu_qualcomm_adreno_opencl",
        "windows_arm64_npu_qualcomm_base",
        "windows_arm64_npu_qualcomm_qnn",
    }


def test_resolve_selects_amd64_cuda_when_runtime_evidence_exists(tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    entry.local_path.parent.mkdir(parents=True)
    entry.local_path.write_bytes(b"gguf")
    cuda_binary = tmp_path / "bin" / "amd64-cuda" / "llama-server.exe"
    cuda_binary.parent.mkdir(parents=True)
    cuda_binary.write_bytes(b"exe")

    resolution = resolve_llm_serve_profile(
        "research",
        HardwareProfile(
            os_name="windows",
            arch="amd64",
            gpu_available=True,
            gpu_vendor="nvidia",
            cuda_available=True,
        ),
        _preflight(["ep:CUDAExecutionProvider"]),
        settings=_settings(),
        flags=CapabilityFlags(supports_cuda_llm=True),
        entry=entry,
    )

    assert resolution.serve_profile_id == "windows_amd64_gpu_nvidia_cuda"
    assert resolution.accelerator == "gpu.cuda"
    assert resolution.binary_path == cuda_binary
    assert resolution.degraded_reason is None
    assert "windows_amd64_gpu_nvidia_cuda" not in {
        candidate.profile_id for candidate in resolution.degraded_candidates
    }


def test_resolve_reports_arm64_qnn_as_skipped_until_viable_binary_exists(tmp_path: Path) -> None:
    resolution = resolve_llm_serve_profile(
        "tool_plan",
        HardwareProfile(
            os_name="windows",
            arch="arm64",
            npu_available=True,
            npu_vendor="qualcomm",
        ),
        _preflight(["ep:QNNExecutionProvider", "dll:QnnHtp"]),
        settings=_settings(),
        flags=CapabilityFlags(qnn_available=True),
        entry=_entry(tmp_path),
    )

    assert [(candidate.profile_id, candidate.reason) for candidate in resolution.degraded_candidates] == [
        ("windows_arm64_npu_qualcomm_base", "Degraded-accelerator-unavailable"),
        ("windows_arm64_gpu_qualcomm_adreno_opencl", "Degraded-opencl-build-required"),
        ("windows_arm64_npu_qualcomm_qnn", "Degraded-no-sidecar-binary"),
    ]
    assert resolution.serve_profile_id == "windows_arm64_cpu"
    assert resolution.accelerator == "cpu"


def test_qualcomm_npu_base_profile_is_separate_from_qnn_sidecar(tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    profiles = entry.config["serve_profiles"]["hardware_profiles"]
    base_profile = profiles["windows_arm64_npu_qualcomm_base"]
    qnn_profile = profiles["windows_arm64_npu_qualcomm_qnn"]
    adreno_profile = profiles["windows_arm64_gpu_qualcomm_adreno_opencl"]

    assert base_profile["accelerator"] == "npu.hexagon_candidate"
    assert qnn_profile["accelerator"] == "npu.qnn"
    assert adreno_profile["accelerator"] == "gpu.opencl.adreno"
    assert base_profile["runtime_artifact"]["source"]["candidate_runtime_findings"] == {
        "windows_on_snapdragon": "build-package-flow",
        "device_examples": ["cpu", "adreno-opencl", "hexagon-htp"],
        "release_asset": "none-confirmed",
    }
    assert qnn_profile["runtime_artifact"]["source"]["runtime_mapping"] == "pending-hexagon-qnn-viability"
    assert adreno_profile["runtime_artifact"]["source"]["candidate_runtime_findings"] == {
        "windows_on_snapdragon": "build-flow",
        "gpu_backend": "adreno-opencl",
        "release_asset": "none-confirmed",
        "optimized_quantization": "Q4_0",
        "current_model_quantization": "Q4_K_M",
    }


def test_resolve_selects_arm64_adreno_opencl_when_runtime_evidence_exists(tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    entry.local_path.parent.mkdir(parents=True)
    entry.local_path.write_bytes(b"gguf")
    adreno_binary = tmp_path / "bin" / "arm64-adreno-opencl" / "llama-server.exe"
    adreno_binary.parent.mkdir(parents=True)
    adreno_binary.write_bytes(b"exe")

    resolution = resolve_llm_serve_profile(
        "tool_plan",
        HardwareProfile(
            os_name="windows",
            arch="arm64",
            gpu_available=True,
            gpu_vendor="qualcomm",
            npu_available=True,
            npu_vendor="qualcomm",
        ),
        _preflight(["opencl:adreno"]),
        settings=_settings(),
        flags=CapabilityFlags(qnn_available=True),
        entry=entry,
    )

    assert resolution.serve_profile_id == "windows_arm64_gpu_qualcomm_adreno_opencl"
    assert resolution.accelerator == "gpu.opencl.adreno"
    assert resolution.binary_path == adreno_binary
    assert "device" not in resolution.launch
    assert resolution.degraded_reason is None
    assert "windows_arm64_gpu_qualcomm_adreno_opencl" not in {
        candidate.profile_id for candidate in resolution.degraded_candidates
    }


def test_resolve_selects_arm64_qnn_when_runtime_evidence_exists(tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    entry.local_path.parent.mkdir(parents=True)
    entry.local_path.write_bytes(b"gguf")
    qnn_binary = tmp_path / "bin" / "arm64-qnn" / "llama-server.exe"
    qnn_binary.parent.mkdir(parents=True)
    qnn_binary.write_bytes(b"exe")

    resolution = resolve_llm_serve_profile(
        "tool_plan",
        HardwareProfile(
            os_name="windows",
            arch="arm64",
            npu_available=True,
            npu_vendor="qualcomm",
        ),
        _preflight(["ep:QNNExecutionProvider", "dll:QnnHtp"]),
        settings=_settings(),
        flags=CapabilityFlags(qnn_available=True),
        entry=entry,
    )

    assert resolution.serve_profile_id == "windows_arm64_npu_qualcomm_qnn"
    assert resolution.accelerator == "npu.qnn"
    assert resolution.binary_path == qnn_binary
    assert resolution.launch["device"] == "qnn"
    assert (
        resolution.selected_reason
        == "selected current-host npu.qnn serve profile windows_arm64_npu_qualcomm_qnn"
    )
    assert resolution.degraded_reason is None
    assert "windows_arm64_npu_qualcomm_qnn" not in {
        candidate.profile_id for candidate in resolution.degraded_candidates
    }


def test_global_binary_override_does_not_make_arm64_qnn_candidate_viable(tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    entry.local_path.parent.mkdir(parents=True)
    entry.local_path.write_bytes(b"gguf")
    cpu_binary = tmp_path / "bin" / "arm64-cpu" / "llama-server.exe"
    cpu_binary.parent.mkdir(parents=True)
    cpu_binary.write_bytes(b"exe")

    resolution = resolve_llm_serve_profile(
        "tool_plan",
        HardwareProfile(
            os_name="windows",
            arch="arm64",
            npu_available=True,
            npu_vendor="qualcomm",
        ),
        _preflight(["ep:QNNExecutionProvider", "dll:QnnHtp"]),
        settings=Settings(
            llama_cpp_base_url="",
            llama_cpp_model_path=None,
            llama_cpp_binary_path=str(cpu_binary),
        ),
        flags=CapabilityFlags(qnn_available=True),
        entry=entry,
    )

    assert resolution.serve_profile_id == "windows_arm64_cpu"
    assert resolution.accelerator == "cpu"
    assert resolution.binary_path == cpu_binary
    assert [(candidate.profile_id, candidate.reason) for candidate in resolution.degraded_candidates] == [
        ("windows_arm64_npu_qualcomm_base", "Degraded-accelerator-unavailable"),
        ("windows_arm64_gpu_qualcomm_adreno_opencl", "Degraded-opencl-build-required"),
        ("windows_arm64_npu_qualcomm_qnn", "Degraded-no-sidecar-binary"),
    ]


def test_resolve_rejects_routes_not_declared_in_catalog(tmp_path: Path) -> None:
    with pytest.raises(ModelCatalogError, match="not declared"):
        resolve_llm_serve_profile(
            "unsupported",
            HardwareProfile(os_name="windows", arch="amd64"),
            _preflight(),
            settings=_settings(),
            entry=_entry(tmp_path),
        )
