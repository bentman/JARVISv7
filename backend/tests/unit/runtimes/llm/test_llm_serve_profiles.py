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
                "windows_amd64_cpu": {
                    "os": "windows",
                    "arch": "amd64",
                    "accelerator": "cpu",
                    "binary_path": str(tmp_path / "bin" / "amd64-cpu" / "llama-server.exe"),
                    "base_url": "http://127.0.0.1:8080",
                    "launch": {
                        "ctx_size": 4096,
                        "gpu_layers": 0,
                    },
                },
                "windows_arm64_cpu": {
                    "os": "windows",
                    "arch": "arm64",
                    "accelerator": "cpu",
                    "binary_path": str(tmp_path / "bin" / "arm64-cpu" / "llama-server.exe"),
                    "base_url": "http://127.0.0.1:8080",
                    "launch": {
                        "ctx_size": 4096,
                        "gpu_layers": 0,
                    },
                },
                "windows_amd64_cuda": {
                    "os": "windows",
                    "arch": "amd64",
                    "accelerator": "gpu.cuda",
                    "binary_path": str(tmp_path / "bin" / "amd64-cuda" / "llama-server.exe"),
                    "close_if_unavailable": "Degraded-accelerator-unavailable",
                    "launch": {
                        "ctx_size": 4096,
                        "gpu_layers": "auto",
                    },
                },
                "windows_arm64_qnn": {
                    "os": "windows",
                    "arch": "arm64",
                    "accelerator": "npu.qnn",
                    "binary_path": str(tmp_path / "bin" / "arm64-qnn" / "llama-server.exe"),
                    "close_if_unavailable": "SKIP-no-viable-binary",
                    "launch": {
                        "ctx_size": 4096,
                        "device": "qnn",
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
        ("windows_amd64_cuda", "Degraded-accelerator-unavailable")
    ]


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
        ("windows_arm64_qnn", "Degraded-no-sidecar-binary")
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
