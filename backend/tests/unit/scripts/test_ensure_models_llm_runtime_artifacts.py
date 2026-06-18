from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path

from backend.app.core.settings import Settings
from scripts import ensure_models


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
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
                    "windows_arm64_npu_qualcomm_qnn": {
                        "profile_id": "windows_arm64_npu_qualcomm_qnn",
                        "os": "windows",
                        "arch": "arm64",
                        "accelerator": "npu.qnn",
                        "runtime_artifact": {
                            "source": {"type": "pending-viability", "reason": "test-pending"},
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
    assert profiles["windows_amd64_gpu_nvidia_cuda"]["state"] == "degraded"
    assert profiles["windows_amd64_gpu_nvidia_cuda"]["degraded_reason"] == "Degraded-accelerator-unavailable"
    assert profiles["windows_arm64_npu_qualcomm_qnn"]["ready"] is False
    assert profiles["windows_arm64_npu_qualcomm_qnn"]["degraded_reason"] == "Degraded-no-sidecar-binary"


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
    assert "bin/llama-server.exe" in result["acquired"]
    assert "bin/ggml.dll" in result["acquired"]


def test_runtime_dry_run_reports_planned_required_files_without_writing(tmp_path: Path) -> None:
    entry = _entry(tmp_path)

    result = ensure_models._ensure_runtime_artifacts(entry, dry_run=True)

    profiles = {profile["profile_id"]: profile for profile in result["profiles"]}
    assert profiles["windows_amd64_cpu"]["state"] == "planned"
    assert profiles["windows_amd64_cpu"]["planned"] == ["llama-server.exe"]
    assert not (tmp_path / "runtimes").exists()


def test_automatic_runtime_fetch_policy_honors_local_fetch_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        ensure_models,
        "load_settings",
        lambda: Settings(use_local_model=True, local_model_fetch=False),
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
