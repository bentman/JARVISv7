from __future__ import annotations

import pytest
from backend.app.core.paths import REPO_ROOT
from backend.app.models.llm_profiles import resolve_llm_serve_profile


@pytest.mark.llm
def test_current_host_llm_serve_profile_resolution_uses_real_evidence(
    profiler_fixture,
    preflight_fixture,
) -> None:
    resolution = resolve_llm_serve_profile(
        "voice_chat",
        profiler_fixture.profile,
        preflight_fixture,
        flags=profiler_fixture.flags,
    )

    assert resolution.serve_profile_id.startswith(
        f"{profiler_fixture.profile.os_name}_{profiler_fixture.profile.arch}_"
    )
    assert resolution.binary_path.name == "llama-server.exe"
    assert resolution.local_model_path.name.endswith(".gguf")

    if profiler_fixture.profile.arch == "amd64" and profiler_fixture.profile.gpu_vendor == "nvidia":
        cuda_candidate = next(
            (
                candidate
                for candidate in resolution.degraded_candidates
                if candidate.profile_id == "windows_amd64_gpu_nvidia_cuda"
            ),
            None,
        )
        cuda_ready = (
            profiler_fixture.profile.cuda_available
            and profiler_fixture.flags.supports_cuda_llm
            and "ep:CUDAExecutionProvider" in preflight_fixture.tokens
        )
        cuda_binary = (
            REPO_ROOT / "runtimes" / "llama.cpp" / "windows-amd64-cuda" / "llama-server.exe"
        )

        if cuda_ready and cuda_binary.is_file() and resolution.local_model_path.is_file():
            assert resolution.serve_profile_id == "windows_amd64_gpu_nvidia_cuda"
            assert resolution.accelerator == "gpu.cuda"
        else:
            assert resolution.serve_profile_id == "windows_amd64_cpu"
            assert resolution.accelerator == "cpu"
            assert cuda_candidate is not None
            assert cuda_candidate.reason in {
                "Degraded-no-sidecar-binary",
                "Degraded-no-local-model-artifact",
                "Degraded-accelerator-unavailable",
            }

    if profiler_fixture.profile.arch == "arm64" and profiler_fixture.profile.npu_vendor == "qualcomm":
        qnn_candidate = next(
            (
                candidate
                for candidate in resolution.degraded_candidates
                if candidate.profile_id == "windows_arm64_npu_qualcomm_qnn"
            ),
            None,
        )
        qnn_ready = (
            profiler_fixture.flags.qnn_available
            and "ep:QNNExecutionProvider" in preflight_fixture.tokens
            and "dll:QnnHtp" in preflight_fixture.tokens
        )
        qnn_binary = REPO_ROOT / "runtimes" / "llama.cpp" / "windows-arm64-qnn" / "llama-server.exe"
        adreno_ready = (
            profiler_fixture.profile.gpu_available
            and profiler_fixture.profile.gpu_vendor == "qualcomm"
            and "opencl:adreno" in preflight_fixture.tokens
        )
        adreno_binary = (
            REPO_ROOT
            / "runtimes"
            / "llama.cpp"
            / "windows-arm64-adreno-opencl"
            / "llama-server.exe"
        )

        if adreno_ready and adreno_binary.is_file() and resolution.local_model_path.is_file():
            assert resolution.serve_profile_id == "windows_arm64_gpu_qualcomm_adreno_opencl"
            assert resolution.accelerator == "gpu.opencl.adreno"
        elif qnn_ready and qnn_binary.is_file() and resolution.local_model_path.is_file():
            assert resolution.serve_profile_id == "windows_arm64_npu_qualcomm_qnn"
            assert resolution.accelerator == "npu.qnn"
        else:
            assert resolution.serve_profile_id == "windows_arm64_cpu"
            assert resolution.accelerator == "cpu"
            assert qnn_candidate is not None
            assert qnn_candidate.reason in {
                "Degraded-no-sidecar-binary",
                "Degraded-no-local-model-artifact",
                "Degraded-accelerator-unavailable",
            }
