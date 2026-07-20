from __future__ import annotations

import argparse
import hashlib
import io
import os
import tarfile
import zipfile
from pathlib import Path

import pytest

from backend.app.core.capabilities import HardwareProfile
from backend.app.core.settings import Settings
from scripts import ensure_models


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _tar_gz_bytes(entries: dict[str, tuple[bytes, int]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, (payload, mode) in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            member.mode = mode
            archive.addfile(member, io.BytesIO(payload))
    return buffer.getvalue()


class _FakeResponse:
    def __init__(self, payload: bytes):
        self.content = payload

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str) -> _FakeResponse:
        return _FakeResponse(self._payload)


def _entry(tmp_path: Path, *, source_type: str = "pending-pinned-release") -> ensure_models.ModelEntry:
    model_file = tmp_path / "models" / "llm" / "assistant-small-q4" / "model.gguf"
    runtime_file = tmp_path / "runtimes" / "llama.cpp" / "windows-amd64-cpu" / "llama-server.exe"
    source: dict[str, object] = {"type": source_type, "reason": "test-pending"}
    if source_type == "url_zip":
        source = {"type": "url_zip", "url": "https://example.invalid/llama.zip"}
    if source_type == "url_zip_set":
        source = {
            "type": "url_zip_set",
            "archives": [
                {"asset": "llama.zip", "url": "https://example.invalid/llama.zip"},
                {"asset": "cudart.zip", "url": "https://example.invalid/cudart.zip"},
            ],
        }
    return ensure_models.ModelEntry(
        family="llm",
        name="assistant-small-q4",
        config={
            "local_path": str(model_file),
            "source": {
                "type": "huggingface",
                "repo_id": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
                "file": "model.gguf",
            },
            "serve_profiles": {
                "hardware_profiles": {
                    "windows_amd64_cpu": {
                        "profile_id": "windows_amd64_cpu",
                        "os": "windows",
                        "arch": "amd64",
                        "accelerator": "cpu",
                        "runtime_artifact": {
                            "source": source,
                            "binary_path": str(runtime_file),
                            "required_files": ["llama-server.exe"],
                            "required_adjacent": {"dll_extensions": [".dll"]},
                        },
                        "binary_path": str(runtime_file),
                    },
                    "windows_amd64_gpu_nvidia_cuda": {
                        "profile_id": "windows_amd64_gpu_nvidia_cuda",
                        "os": "windows",
                        "arch": "amd64",
                        "accelerator": "gpu.cuda",
                        "runtime_artifact": {
                            "source": {"type": "pending-pinned-release", "reason": "test-pending"},
                            "binary_path": str(
                                tmp_path / "runtimes" / "llama.cpp" / "windows-amd64-cuda" / "llama-server.exe"
                            ),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(
                            tmp_path / "runtimes" / "llama.cpp" / "windows-amd64-cuda" / "llama-server.exe"
                        ),
                        "close_if_unavailable": "Degraded-accelerator-unavailable",
                    },
                    "windows_amd64_gpu_amd": {
                        "profile_id": "windows_amd64_gpu_amd",
                        "os": "windows",
                        "arch": "amd64",
                        "accelerator": "gpu.vulkan",
                        "runtime_artifact": {
                            "source": {
                                "type": "pending-pinned-release",
                                "reason": "test-pending",
                                "candidate_artifact_families": ["vulkan", "hip"],
                            },
                            "binary_path": str(
                                tmp_path
                                / "runtimes"
                                / "llama.cpp"
                                / "windows-amd64-gpu-amd"
                                / "llama-server.exe"
                            ),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(
                            tmp_path / "runtimes" / "llama.cpp" / "windows-amd64-gpu-amd" / "llama-server.exe"
                        ),
                        "close_if_unavailable": "Degraded-accelerator-unavailable",
                    },
                    "windows_amd64_gpu_intel": {
                        "profile_id": "windows_amd64_gpu_intel",
                        "os": "windows",
                        "arch": "amd64",
                        "accelerator": "gpu.vulkan",
                        "runtime_artifact": {
                            "source": {
                                "type": "pending-pinned-release",
                                "reason": "test-pending",
                                "candidate_artifact_families": ["vulkan", "openvino", "sycl"],
                            },
                            "binary_path": str(
                                tmp_path
                                / "runtimes"
                                / "llama.cpp"
                                / "windows-amd64-gpu-intel"
                                / "llama-server.exe"
                            ),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(
                            tmp_path / "runtimes" / "llama.cpp" / "windows-amd64-gpu-intel" / "llama-server.exe"
                        ),
                        "close_if_unavailable": "Degraded-accelerator-unavailable",
                    },
                    "windows_arm64_npu_qualcomm_base": {
                        "profile_id": "windows_arm64_npu_qualcomm_base",
                        "os": "windows",
                        "arch": "arm64",
                        "accelerator": "npu.hexagon_candidate",
                        "runtime_artifact": {
                            "source": {
                                "type": "pending-viability",
                                "reason": "test-pending",
                                "candidate_runtime_findings": {
                                    "windows_on_snapdragon": "build-package-flow",
                                    "device_examples": ["cpu", "adreno-opencl", "hexagon-htp"],
                                    "release_asset": "none-confirmed",
                                },
                            },
                            "binary_path": str(
                                tmp_path
                                / "runtimes"
                                / "llama.cpp"
                                / "windows-arm64-npu-qualcomm"
                                / "llama-server.exe"
                            ),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(
                            tmp_path
                            / "runtimes"
                            / "llama.cpp"
                            / "windows-arm64-npu-qualcomm"
                            / "llama-server.exe"
                        ),
                        "close_if_unavailable": "Degraded-accelerator-unavailable",
                    },
                    "windows_arm64_gpu_qualcomm_adreno_opencl": {
                        "profile_id": "windows_arm64_gpu_qualcomm_adreno_opencl",
                        "os": "windows",
                        "arch": "arm64",
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
                            "binary_path": str(
                                tmp_path
                                / "runtimes"
                                / "llama.cpp"
                                / "windows-arm64-adreno-opencl"
                                / "llama-server.exe"
                            ),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(
                            tmp_path
                            / "runtimes"
                            / "llama.cpp"
                            / "windows-arm64-adreno-opencl"
                            / "llama-server.exe"
                        ),
                        "close_if_unavailable": "Degraded-opencl-build-required",
                    },
                    "windows_arm64_npu_qualcomm_qnn": {
                        "profile_id": "windows_arm64_npu_qualcomm_qnn",
                        "os": "windows",
                        "arch": "arm64",
                        "accelerator": "npu.qnn",
                        "runtime_artifact": {
                            "source": {
                                "type": "pending-viability",
                                "reason": "test-pending",
                                "project_label": "npu.qnn",
                                "runtime_mapping": "pending-hexagon-qnn-viability",
                            },
                            "binary_path": str(
                                tmp_path / "runtimes" / "llama.cpp" / "windows-arm64-qnn" / "llama-server.exe"
                            ),
                            "required_files": ["llama-server.exe"],
                        },
                        "binary_path": str(
                            tmp_path / "runtimes" / "llama.cpp" / "windows-arm64-qnn" / "llama-server.exe"
                        ),
                        "close_if_unavailable": "Degraded-no-sidecar-binary",
                    },
                }
            },
        },
    )


def test_verify_runtime_artifacts_reports_separate_profile_states(tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    cpu_binary = tmp_path / "runtimes" / "llama.cpp" / "windows-amd64-cpu" / "llama-server.exe"
    cpu_binary.parent.mkdir(parents=True)
    cpu_binary.write_bytes(b"exe")
    (cpu_binary.parent / "ggml.dll").write_bytes(b"dll")

    result = ensure_models._verify_runtime_artifacts(entry)

    profiles = {profile["profile_id"]: profile for profile in result["profiles"]}
    assert profiles["windows_amd64_cpu"]["ready"] is True
    assert profiles["windows_amd64_cpu"]["state"] == "ready"
    assert profiles["windows_amd64_gpu_nvidia_cuda"]["ready"] is False
    assert profiles["windows_amd64_gpu_nvidia_cuda"]["state"] == "skipped"
    assert profiles["windows_amd64_gpu_nvidia_cuda"]["degraded_reason"] == "SKIP-source-pending"
    assert profiles["windows_amd64_gpu_amd"]["state"] == "skipped"
    assert profiles["windows_amd64_gpu_amd"]["degraded_reason"] == "SKIP-source-pending"
    assert profiles["windows_amd64_gpu_intel"]["state"] == "skipped"
    assert profiles["windows_amd64_gpu_intel"]["degraded_reason"] == "SKIP-source-pending"
    assert profiles["windows_arm64_npu_qualcomm_base"]["ready"] is False
    assert profiles["windows_arm64_npu_qualcomm_base"]["degraded_reason"] == "SKIP-no-viable-binary"
    assert profiles["windows_arm64_gpu_qualcomm_adreno_opencl"]["ready"] is False
    assert profiles["windows_arm64_gpu_qualcomm_adreno_opencl"]["degraded_reason"] == "SKIP-build-required"
    assert profiles["windows_arm64_npu_qualcomm_qnn"]["ready"] is False
    assert profiles["windows_arm64_npu_qualcomm_qnn"]["degraded_reason"] == "SKIP-no-viable-binary"


def test_verify_runtime_artifacts_reports_current_host_summary(tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    cpu_binary = tmp_path / "runtimes" / "llama.cpp" / "windows-amd64-cpu" / "llama-server.exe"
    cpu_binary.parent.mkdir(parents=True)
    cpu_binary.write_bytes(b"exe")
    (cpu_binary.parent / "ggml.dll").write_bytes(b"dll")

    result = ensure_models._verify_runtime_artifacts(
        entry,
        hardware_profile=HardwareProfile(os_name="windows", arch="amd64"),
        extras=["hw-cpu-base", "hw-x64-base", "hw-x64-ort-cpu"],
    )

    assert result["current_host"] == {
        "os": "windows",
        "arch": "amd64",
        "applicable_profiles": ["windows_amd64_cpu"],
        "selected_profile_id": "windows_amd64_cpu",
        "selected_state": "ready",
        "selected_ready": True,
        "selected_degraded_reason": None,
    }


def test_ensure_llm_family_keeps_model_ready_separate_from_runtime_state(tmp_path: Path, monkeypatch) -> None:
    entry = _entry(tmp_path)
    entry.local_path.parent.mkdir(parents=True)
    entry.local_path.write_bytes(b"gguf")
    monkeypatch.setattr(ensure_models, "get_model_entry", lambda family, model_name=None: entry)
    monkeypatch.setattr(ensure_models, "_download_huggingface", lambda entry, dry_run: ["model.gguf"])

    code, result = ensure_models._ensure_family("llm", "assistant-small-q4", dry_run=False)

    assert code == 0
    assert result["ready"] is True
    assert result["models"][0]["ready"] is True
    assert result["runtime_artifacts"][0]["ready"] is False


def test_runtime_url_zip_acquisition_extracts_and_verifies_required_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    payload = _zip_bytes({"bin/llama-server.exe": b"exe", "bin/ggml.dll": b"dll"})
    monkeypatch.setattr(ensure_models.httpx, "Client", lambda **kwargs: _FakeClient(payload))
    entry = _entry(tmp_path, source_type="url_zip")
    profile = ensure_models._hardware_profiles(entry)["windows_amd64_cpu"]

    result = ensure_models._ensure_runtime_profile("windows_amd64_cpu", profile, dry_run=False)

    assert result["ready"] is True
    assert result["state"] == "ready"
    assert "llama-server.exe" in result["acquired"]
    assert "ggml.dll" in result["acquired"]
    assert (tmp_path / "runtimes" / "llama.cpp" / "windows-amd64-cpu" / "llama-server.exe").is_file()
    assert (tmp_path / "runtimes" / "llama.cpp" / "windows-amd64-cpu" / "ggml.dll").is_file()


def test_runtime_url_zip_acquisition_requires_configured_binary_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    payload = _zip_bytes({"llama-b9704/bin/llama-server.exe": b"exe", "llama-b9704/bin/ggml.dll": b"dll"})
    monkeypatch.setattr(ensure_models.httpx, "Client", lambda **kwargs: _FakeClient(payload))
    entry = _entry(tmp_path, source_type="url_zip")
    profile = ensure_models._hardware_profiles(entry)["windows_amd64_cpu"]

    result = ensure_models._ensure_runtime_profile("windows_amd64_cpu", profile, dry_run=False)

    assert result["ready"] is False
    assert result["state"] == "degraded"
    assert result["missing"] == ["llama-server.exe"]
    assert "bin/llama-server.exe" in result["acquired"]
    assert "bin/ggml.dll" in result["acquired"]
    assert (tmp_path / "runtimes" / "llama.cpp" / "windows-amd64-cpu" / "bin" / "llama-server.exe").is_file()


def test_runtime_url_zip_acquisition_skips_ready_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_client(**kwargs):
        raise AssertionError("ready runtime should not be downloaded")

    monkeypatch.setattr(ensure_models.httpx, "Client", fail_client)
    entry = _entry(tmp_path, source_type="url_zip")
    profile = ensure_models._hardware_profiles(entry)["windows_amd64_cpu"]
    runtime_file = tmp_path / "runtimes" / "llama.cpp" / "windows-amd64-cpu" / "llama-server.exe"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_bytes(b"exe")
    (runtime_file.parent / "ggml.dll").write_bytes(b"dll")

    result = ensure_models._ensure_runtime_profile("windows_amd64_cpu", profile, dry_run=False)

    assert result["ready"] is True
    assert result["state"] == "ready"
    assert result["acquired"] == []


def test_runtime_url_zip_set_acquisition_extracts_split_archives(
    tmp_path: Path,
    monkeypatch,
) -> None:
    payloads = [
        _zip_bytes({"llama-server.exe": b"exe", "ggml-cuda.dll": b"dll"}),
        _zip_bytes({"cudart64_13.dll": b"dll", "cublas64_13.dll": b"dll", "cublasLt64_13.dll": b"dll"}),
    ]

    class SplitClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str) -> _FakeResponse:
            assert payloads
            return _FakeResponse(payloads.pop(0))

    monkeypatch.setattr(ensure_models.httpx, "Client", lambda **kwargs: SplitClient())
    entry = _entry(tmp_path, source_type="url_zip_set")
    profile = ensure_models._hardware_profiles(entry)["windows_amd64_cpu"]
    profile["runtime_artifact"]["required_files"] = [
        "llama-server.exe",
        "ggml-cuda.dll",
        "cudart64_13.dll",
        "cublas64_13.dll",
        "cublasLt64_13.dll",
    ]

    result = ensure_models._ensure_runtime_profile("windows_amd64_cpu", profile, dry_run=False)

    assert result["ready"] is True
    assert result["state"] == "ready"
    assert result["missing"] == []
    assert result["acquired"] == [
        "llama-server.exe",
        "ggml-cuda.dll",
        "cudart64_13.dll",
        "cublas64_13.dll",
        "cublasLt64_13.dll",
    ]


@pytest.mark.skipif(os.name == "nt", reason="validates Linux/POSIX executable-mode filesystem semantics")
def test_runtime_url_tar_gz_acquisition_preserves_llama_server_executable_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    payload = _tar_gz_bytes(
        {
            "llama-b9704/llama-server": (b"server", 0o755),
            "llama-b9704/libggml.so": (b"library", 0o644),
        }
    )
    monkeypatch.setattr(ensure_models.httpx, "Client", lambda **kwargs: _FakeClient(payload))
    binary_path = tmp_path / "runtimes" / "llama.cpp" / "linux-amd64-cpu" / "llama-server"
    profile = {
        "runtime_artifact": {
            "source": {"type": "url_tar_gz", "url": "https://example.invalid/llama.tar.gz"},
            "binary_path": str(binary_path),
            "required_files": ["llama-server"],
        },
        "binary_path": str(binary_path),
    }

    result = ensure_models._ensure_runtime_profile("linux_amd64_cpu", profile, dry_run=False)

    assert result["ready"] is True
    assert result["state"] == "ready"
    assert result["acquired"] == ["llama-server", "libggml.so"]
    assert binary_path.is_file()
    assert binary_path.stat().st_mode & 0o111


def test_runtime_url_tar_gz_rejects_path_traversal(tmp_path: Path) -> None:
    payload = _tar_gz_bytes({"../llama-server": (b"server", 0o755)})

    with pytest.raises(RuntimeError, match="unsafe tar member path"):
        ensure_models._extract_runtime_tar_gz_payload(payload, tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="validates Linux/POSIX symbolic-link filesystem semantics")
def test_runtime_url_tar_gz_preserves_safe_relative_symbolic_links(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        server = tarfile.TarInfo("llama-b9704/llama-server")
        server.size = len(b"server")
        server.mode = 0o755
        archive.addfile(server, io.BytesIO(b"server"))
        library = tarfile.TarInfo("llama-b9704/libmtmd.so.0")
        library.size = len(b"library")
        library.mode = 0o644
        archive.addfile(library, io.BytesIO(b"library"))
        link = tarfile.TarInfo("llama-b9704/libmtmd.so")
        link.type = tarfile.SYMTYPE
        link.linkname = "libmtmd.so.0"
        archive.addfile(link)

    ensure_models._extract_runtime_tar_gz_payload(buffer.getvalue(), tmp_path)

    link_path = tmp_path / "libmtmd.so"
    assert link_path.is_symlink()
    assert link_path.readlink() == Path("libmtmd.so.0")


@pytest.mark.skipif(os.name == "nt", reason="validates Linux/POSIX source-build filesystem semantics")
def test_runtime_source_build_verifies_provenance_and_stages_shared_libraries(tmp_path: Path, monkeypatch) -> None:
    source_root_name = "llama.cpp-b9704"
    payload = _tar_gz_bytes({f"{source_root_name}/CMakeLists.txt": (b"cmake_minimum_required(VERSION 3.14)", 0o644)})
    sha256 = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(ensure_models.httpx, "Client", lambda **kwargs: _FakeClient(payload))

    binary_path = tmp_path / "runtimes" / "llama.cpp" / "linux-amd64-cuda" / "llama-server"
    profile = {
        "runtime_artifact": {
            "source": {
                "type": "source_tar_gz_build",
                "url": "https://example.invalid/llama.cpp-b9704.tar.gz",
                "asset": "llama.cpp-b9704.tar.gz",
                "sha256": sha256,
                "commit": "1" * 40,
                "cuda_compiler": str(tmp_path / "nvcc"),
                "cuda_toolkit_root": str(tmp_path / "cuda"),
            },
            "binary_path": str(binary_path),
            "required_files": [
                "llama-server",
                "libllama-server-impl.so",
                "libllama-common.so.0",
                "libggml.so",
                "libggml-cuda.so",
            ],
        },
        "binary_path": str(binary_path),
    }
    (tmp_path / "nvcc").write_bytes(b"compiler")
    (tmp_path / "cuda" / "include").mkdir(parents=True)

    def fake_run(command, check, **kwargs):
        assert check is True
        if command[0] == "ldd":
            return type("Result", (), {"returncode": 0, "stdout": ""})()
        assert kwargs["env"]["CUDA_HOME"] == str(tmp_path / "cuda")
        assert kwargs["env"]["CUDACXX"] == str(tmp_path / "nvcc")
        assert kwargs["env"]["PATH"].startswith(f"{tmp_path / 'cuda' / 'bin'}{os.pathsep}")
        assert kwargs["env"]["LD_LIBRARY_PATH"].startswith(f"{tmp_path / 'cuda' / 'lib64'}{os.pathsep}")
        if command[0] == "cmake" and "--build" not in command:
            assert "-DCMAKE_BUILD_RPATH=$ORIGIN" in command
            assert "-DCMAKE_INSTALL_RPATH=$ORIGIN" in command
        if "--build" in command:
            build_bin = Path(command[2]) / "bin"
            build_bin.mkdir(parents=True)
            for name in (
                "llama-server",
                "libllama-server-impl.so",
                "libllama-common.so.0",
                "libggml.so",
                "libggml-cuda.so",
            ):
                (build_bin / name).write_bytes(name.encode())
            (build_bin / "llama-server").chmod(0o755)
        return None

    monkeypatch.setattr(ensure_models.subprocess, "run", fake_run)
    monkeypatch.setattr(
        ensure_models,
        "REPO_ROOT",
        tmp_path,
    )

    result = ensure_models._ensure_runtime_profile("linux_amd64_gpu_nvidia_cuda", profile, dry_run=False)

    assert result["ready"] is True
    assert result["state"] == "ready"
    assert result["acquired"] == [
        "libggml-cuda.so",
        "libggml.so",
        "libllama-common.so.0",
        "libllama-server-impl.so",
        "llama-server",
    ]
    assert binary_path.stat().st_mode & 0o111
    assert (tmp_path / "cache" / "llama.cpp" / "linux_amd64_gpu_nvidia_cuda" / "source" / ".managed-source-commit").read_text().strip() == "1" * 40


def test_linux_cuda_runtime_verification_rejects_llama_libraries_outside_staging(tmp_path: Path, monkeypatch) -> None:
    binary_path = tmp_path / "runtimes" / "llama.cpp" / "linux-amd64-cuda" / "llama-server"
    binary_path.parent.mkdir(parents=True)
    binary_path.write_bytes(b"server")
    binary_path.chmod(0o755)
    profile = {
        "accelerator": "gpu.cuda",
        "runtime_artifact": {
            "source": {"type": "source_tar_gz_build"},
            "binary_path": str(binary_path),
            "required_files": ["llama-server"],
        },
    }
    monkeypatch.setattr(
        ensure_models.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {"returncode": 0, "stdout": "libllama.so.0 => /tmp/build/libllama.so.0 (0x0)\n"},
        )(),
    )

    result = ensure_models._verify_runtime_profile("linux_amd64_gpu_nvidia_cuda", profile)

    assert result["ready"] is False
    assert result["missing"] == ["llama.cpp library outside staged runtime: libllama.so.0"]


def test_runtime_verification_requires_libraries_adjacent_to_the_server(tmp_path: Path) -> None:
    binary_path = tmp_path / "runtimes" / "llama.cpp" / "linux-amd64-cuda" / "llama-server"
    binary_path.parent.mkdir(parents=True)
    binary_path.write_bytes(b"server")
    binary_path.chmod(0o755)
    nested_library = binary_path.parent / "cache" / "libllama-common.so.0"
    nested_library.parent.mkdir()
    nested_library.write_bytes(b"library")
    profile = {
        "accelerator": "cpu",
        "runtime_artifact": {
            "source": {"type": "url_tar_gz"},
            "binary_path": str(binary_path),
            "required_files": ["llama-server", "libllama-common.so.0"],
        },
    }

    result = ensure_models._verify_runtime_profile("linux_amd64_cpu", profile)

    assert result["ready"] is False
    assert result["missing"] == ["libllama-common.so.0"]


def test_runtime_source_build_rejects_checksum_mismatch(tmp_path: Path, monkeypatch) -> None:
    payload = _tar_gz_bytes({"llama.cpp-b9704/CMakeLists.txt": (b"project(llama)", 0o644)})
    monkeypatch.setattr(ensure_models.httpx, "Client", lambda **kwargs: _FakeClient(payload))
    monkeypatch.setattr(ensure_models, "REPO_ROOT", tmp_path)
    profile = {
        "runtime_artifact": {
            "source": {
                "type": "source_tar_gz_build",
                "url": "https://example.invalid/llama.cpp-b9704.tar.gz",
                "asset": "llama.cpp-b9704.tar.gz",
                "sha256": "0" * 64,
                "commit": "1" * 40,
                "cuda_compiler": str(tmp_path / "nvcc"),
                "cuda_toolkit_root": str(tmp_path / "cuda"),
            },
            "binary_path": str(tmp_path / "runtimes" / "llama-server"),
            "required_files": ["llama-server"],
        }
    }
    (tmp_path / "nvcc").write_bytes(b"compiler")
    (tmp_path / "cuda" / "include").mkdir(parents=True)

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        ensure_models._ensure_runtime_profile("linux_amd64_gpu_nvidia_cuda", profile, dry_run=False)


def test_runtime_dry_run_reports_planned_required_files_without_writing(tmp_path: Path) -> None:
    entry = _entry(tmp_path, source_type="url_zip")

    result = ensure_models._ensure_runtime_artifacts(entry, dry_run=True)

    profiles = {profile["profile_id"]: profile for profile in result["profiles"]}
    assert profiles["windows_amd64_cpu"]["state"] == "planned"
    assert profiles["windows_amd64_cpu"]["planned"] == ["llama-server.exe"]
    assert not (tmp_path / "runtimes").exists()


def test_runtime_dry_run_reports_pending_source_as_skipped(tmp_path: Path) -> None:
    entry = _entry(tmp_path)

    result = ensure_models._ensure_runtime_artifacts(entry, dry_run=True)

    profiles = {profile["profile_id"]: profile for profile in result["profiles"]}
    assert profiles["windows_amd64_cpu"]["state"] == "skipped"
    assert profiles["windows_amd64_cpu"]["planned"] == []
    assert profiles["windows_amd64_cpu"]["degraded_reason"] == "SKIP-source-pending"
    assert profiles["windows_arm64_gpu_qualcomm_adreno_opencl"]["state"] == "skipped"
    assert profiles["windows_arm64_gpu_qualcomm_adreno_opencl"]["planned"] == []
    assert profiles["windows_arm64_gpu_qualcomm_adreno_opencl"]["degraded_reason"] == "SKIP-build-required"


def test_runtime_source_metadata_rejects_missing_source_type(tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    profile = ensure_models._hardware_profiles(entry)["windows_amd64_cpu"]
    profile["runtime_artifact"]["source"] = {}

    with pytest.raises(ValueError, match="source.type"):
        ensure_models._ensure_runtime_profile("windows_amd64_cpu", profile, dry_run=True)


def test_runtime_source_metadata_rejects_invalid_url_zip_source(tmp_path: Path) -> None:
    entry = _entry(tmp_path, source_type="url_zip")
    profile = ensure_models._hardware_profiles(entry)["windows_amd64_cpu"]
    profile["runtime_artifact"]["source"]["url"] = "http://not-secure.invalid/archive.zip"

    with pytest.raises(ValueError, match="invalid runtime url_zip source"):
        ensure_models._ensure_runtime_profile("windows_amd64_cpu", profile, dry_run=False)


def test_catalog_cpu_runtime_profiles_use_pinned_url_sources() -> None:
    entry = ensure_models.get_model_entry("llm", "assistant-small-q4")
    profiles = ensure_models._hardware_profiles(entry)

    amd64_source = profiles["windows_amd64_cpu"]["runtime_artifact"]["source"]
    arm64_source = profiles["windows_arm64_cpu"]["runtime_artifact"]["source"]
    linux_amd64_source = profiles["linux_amd64_cpu"]["runtime_artifact"]["source"]
    linux_arm64_source = profiles["linux_arm64_cpu"]["runtime_artifact"]["source"]

    assert linux_amd64_source == {
        "type": "url_tar_gz",
        "release": "b9704",
        "asset": "llama-b9704-bin-ubuntu-x64.tar.gz",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b9704/llama-b9704-bin-ubuntu-x64.tar.gz",
    }
    assert linux_arm64_source == {
        "type": "url_tar_gz",
        "release": "b9704",
        "asset": "llama-b9704-bin-ubuntu-arm64.tar.gz",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b9704/llama-b9704-bin-ubuntu-arm64.tar.gz",
    }

    assert amd64_source == {
        "type": "url_zip",
        "release": "b9704",
        "asset": "llama-b9704-bin-win-cpu-x64.zip",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b9704/llama-b9704-bin-win-cpu-x64.zip",
    }
    assert arm64_source == {
        "type": "url_zip",
        "release": "b9704",
        "asset": "llama-b9704-bin-win-cpu-arm64.zip",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b9704/llama-b9704-bin-win-cpu-arm64.zip",
    }


def test_catalog_non_cuda_gpu_profiles_record_deferred_candidates() -> None:
    entry = ensure_models.get_model_entry("llm", "assistant-small-q4")
    profiles = ensure_models._hardware_profiles(entry)

    amd_source = profiles["windows_amd64_gpu_amd"]["runtime_artifact"]["source"]
    intel_source = profiles["windows_amd64_gpu_intel"]["runtime_artifact"]["source"]

    assert amd_source["type"] == "pending-pinned-release"
    assert amd_source["candidate_artifact_families"] == ["vulkan", "hip"]
    assert profiles["windows_amd64_gpu_amd"]["validation_status"] == "declared-degraded"
    assert intel_source["type"] == "pending-pinned-release"
    assert intel_source["candidate_artifact_families"] == ["vulkan", "openvino", "sycl"]
    assert profiles["windows_amd64_gpu_intel"]["validation_status"] == "declared-degraded"


def test_catalog_records_verified_cpu_and_cuda_serve_profiles() -> None:
    model_names = (
        "assistant-small-q4",
        "assistant-qwen3-0p6b-q8-diagnostic",
        "assistant-qwen3-4b-q4-portable",
        "assistant-qwen3-8b-q5-balanced",
        "assistant-qwen3-14b-q4-quality",
    )
    verified_profiles = (
        "linux_amd64_cpu",
        "linux_amd64_gpu_nvidia_cuda",
        "windows_amd64_cpu",
        "windows_arm64_cpu",
        "windows_amd64_gpu_nvidia_cuda",
    )

    for model_name in model_names:
        entry = ensure_models.get_model_entry("llm", model_name)
        profiles = ensure_models._hardware_profiles(entry)
        assert {profile: profiles[profile]["validation_status"] for profile in verified_profiles} == {
            profile: "validated" for profile in verified_profiles
        }

    small_profiles = ensure_models._hardware_profiles(ensure_models.get_model_entry("llm", "assistant-small-q4"))
    assert small_profiles["linux_arm64_cpu"]["validation_status"] == "declared-not-validated"


def test_catalog_cuda_runtime_profile_uses_pinned_split_archives() -> None:
    entry = ensure_models.get_model_entry("llm", "assistant-small-q4")
    profiles = ensure_models._hardware_profiles(entry)

    cuda_profile = profiles["windows_amd64_gpu_nvidia_cuda"]
    source = cuda_profile["runtime_artifact"]["source"]

    assert source["type"] == "url_zip_set"
    assert source["release"] == "b9704"
    assert source["cuda_version"] == "13.3"
    assert source["archives"] == [
        {
            "asset": "llama-b9704-bin-win-cuda-13.3-x64.zip",
            "url": "https://github.com/ggml-org/llama.cpp/releases/download/b9704/llama-b9704-bin-win-cuda-13.3-x64.zip",
        },
        {
            "asset": "cudart-llama-bin-win-cuda-13.3-x64.zip",
            "url": "https://github.com/ggml-org/llama.cpp/releases/download/b9704/cudart-llama-bin-win-cuda-13.3-x64.zip",
        },
    ]
    assert cuda_profile["runtime_artifact"]["required_files"] == [
        "llama-server.exe",
        "ggml-cuda.dll",
        "cudart64_13.dll",
        "cublas64_13.dll",
        "cublasLt64_13.dll",
    ]


def test_catalog_linux_cuda_runtime_profile_requires_server_implementation_and_common_library() -> None:
    profiles = ensure_models._hardware_profiles(ensure_models.get_model_entry("llm", "assistant-small-q4"))

    assert "libllama-server-impl.so" in profiles["linux_amd64_gpu_nvidia_cuda"]["runtime_artifact"]["required_files"]
    assert "libllama-common.so.0" in profiles["linux_amd64_gpu_nvidia_cuda"]["runtime_artifact"]["required_files"]


def test_catalog_qualcomm_npu_profiles_record_deferred_viability_findings() -> None:
    entry = ensure_models.get_model_entry("llm", "assistant-small-q4")
    profiles = ensure_models._hardware_profiles(entry)

    base_profile = profiles["windows_arm64_npu_qualcomm_base"]
    adreno_profile = profiles["windows_arm64_gpu_qualcomm_adreno_opencl"]
    qnn_profile = profiles["windows_arm64_npu_qualcomm_qnn"]
    base_source = base_profile["runtime_artifact"]["source"]
    adreno_source = adreno_profile["runtime_artifact"]["source"]
    qnn_source = qnn_profile["runtime_artifact"]["source"]

    assert base_profile["accelerator"] == "npu.hexagon_candidate"
    assert adreno_profile["accelerator"] == "gpu.opencl.adreno"
    assert qnn_profile["accelerator"] == "npu.qnn"
    assert base_source["candidate_runtime_findings"] == {
        "windows_on_snapdragon": "build-package-flow",
        "device_examples": ["cpu", "adreno-opencl", "hexagon-htp"],
        "release_asset": "none-confirmed",
    }
    assert adreno_source["type"] == "build-required"
    assert adreno_source["upstream"]["build_flag"] == "GGML_OPENCL=ON"
    assert adreno_source["candidate_runtime_findings"] == {
        "windows_on_snapdragon": "build-flow",
        "gpu_backend": "adreno-opencl",
        "release_asset": "none-confirmed",
        "optimized_quantization": "Q4_0",
        "current_model_quantization": "Q4_K_M",
    }
    assert qnn_source["project_label"] == "npu.qnn"
    assert qnn_source["runtime_mapping"] == "pending-hexagon-qnn-viability"
    assert qnn_source["candidate_runtime_findings"] == base_source["candidate_runtime_findings"]


def test_automatic_runtime_fetch_policy_derives_from_local_model_intent(monkeypatch) -> None:
    monkeypatch.setattr(
        ensure_models,
        "load_settings",
        lambda: Settings(use_local_model=True, local_model_fetch_explicit=False, local_model_fetch=False),
    )
    args = argparse.Namespace(family=None, model=None)

    allowed, reason = ensure_models._runtime_fetch_allowed(args)

    assert allowed is True
    assert reason == "automatic-local-fetch-enabled"


def test_automatic_runtime_fetch_policy_honors_explicit_local_fetch_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        ensure_models,
        "load_settings",
        lambda: Settings(use_local_model=True, local_model_fetch_explicit=True, local_model_fetch=False),
    )
    args = argparse.Namespace(family=None, model=None)

    allowed, reason = ensure_models._runtime_fetch_allowed(args)

    assert allowed is False
    assert reason == "LOCAL_MODEL_FETCH disabled"


def test_explicit_llm_cli_allows_runtime_fetch_even_when_automatic_fetch_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        ensure_models,
        "load_settings",
        lambda: Settings(use_local_model=True, local_model_fetch=False),
    )
    args = argparse.Namespace(family="llm", model=None)

    allowed, reason = ensure_models._runtime_fetch_allowed(args)

    assert allowed is True
    assert reason == "explicit-cli"


def test_verify_family_llm_defaults_to_selected_model(monkeypatch, tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    model_file = entry.local_path
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"gguf")
    selected: list[tuple[str, str | None]] = []

    monkeypatch.setattr(ensure_models, "get_model_entry", lambda family, model_name=None: entry)
    monkeypatch.setattr(
        ensure_models,
        "select_llm_model",
        lambda route, profile, policy=None: selected.append((route, policy)) or type(
            "Selection",
            (),
            {
                "model_id": "assistant-small-q4",
                "mode": "prod",
                "policy": policy or "auto",
                "role": "balanced",
                "hardware_selector": "windows_amd64_gpu_nvidia_cuda",
            },
        )(),
    )

    code, result = ensure_models._verify_family(
        "llm",
        None,
        hardware_profile=HardwareProfile(os_name="windows", arch="amd64"),
        extras=["dev"],
        llm_policy="balanced",
    )

    assert code == 0
    assert selected == [("voice_chat", "balanced")]
    assert result["selection"] == {
        "policy": "balanced",
        "model": "assistant-small-q4",
        "mode": "prod",
        "role": "balanced",
        "hardware_selector": "windows_amd64_gpu_nvidia_cuda",
    }
    assert [model["model"] for model in result["models"]] == ["assistant-small-q4"]


def test_verify_family_all_llm_keeps_full_catalog(monkeypatch, tmp_path: Path) -> None:
    entry = _entry(tmp_path)
    model_file = entry.local_path
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"gguf")
    monkeypatch.setattr(ensure_models, "list_models", lambda family: {entry.name: entry.config})

    code, result = ensure_models._verify_family(
        "llm",
        None,
        hardware_profile=HardwareProfile(os_name="windows", arch="amd64"),
        extras=["dev"],
        all_llm=True,
    )

    assert code == 0
    assert "selection" not in result
    assert [model["model"] for model in result["models"]] == ["assistant-small-q4"]
