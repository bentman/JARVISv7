from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.core.settings import Settings
from backend.app.hardware.preflight import PreflightResult
from backend.app.models.catalog import ModelEntry
from backend.app.models.llm_profiles import LLMServeProfileResolution
from backend.app.services import local_llm_startup
from backend.app.services.local_llm_startup import prepare_managed_local_llm


class _Response:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def _settings(*, use_local_model: bool = True, managed: bool = True) -> Settings:
    return Settings(
        use_local_model=use_local_model,
        llama_cpp_managed=managed,
        llama_cpp_base_url="",
        llama_cpp_model_path=None,
        llama_cpp_binary_path=None,
    )


def _preflight() -> PreflightResult:
    return PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={})


def test_prepare_managed_local_llm_returns_no_candidate_when_local_model_disabled() -> None:
    result = prepare_managed_local_llm(
        HardwareProfile(os_name="windows", arch="amd64"),
        _preflight(),
        settings=_settings(use_local_model=False),
    )

    assert result.runtime is None
    assert result.sidecar is None
    assert result.degraded_reason == "local model disabled"


def test_prepare_managed_local_llm_reports_profile_degraded_reason(
    monkeypatch,
    tmp_path: Path,
) -> None:
    degraded_resolution = LLMServeProfileResolution(
        model_id="assistant-small-q4",
        route="voice_chat",
        serve_profile_id="windows_amd64_cpu",
        local_model_path=tmp_path / "missing.gguf",
        binary_path=tmp_path / "missing.exe",
        base_url="http://127.0.0.1:8080",
        accelerator="cpu",
        launch={},
        generation_defaults={},
        selected_reason="selected current-host CPU serve profile windows_amd64_cpu",
        degraded_reasons=["Degraded-no-local-model-artifact"],
    )
    monkeypatch.setattr(
        local_llm_startup,
        "resolve_llm_serve_profile",
        lambda *args, **kwargs: degraded_resolution,
    )
    monkeypatch.setattr(
        local_llm_startup,
        "select_llm_model",
        lambda *args, **kwargs: type(
            "Selection",
            (),
            {
                "model_id": "assistant-small-q4",
                "mode": "dev",
                "policy": "auto",
                "role": "portable",
                "reason": "policy auto selected assistant-small-q4",
            },
        )(),
    )

    result = prepare_managed_local_llm(
        HardwareProfile(os_name="windows", arch="amd64"),
        _preflight(),
        settings=_settings(),
        route="voice_chat",
        flags=CapabilityFlags(),
    )

    assert result.runtime is None
    assert result.sidecar is None
    assert result.degraded_reason == "Degraded-no-local-model-artifact"


def test_prepare_managed_local_llm_starts_managed_sidecar_and_returns_wired_runtime(
    monkeypatch,
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model.gguf"
    binary_path = tmp_path / "llama-server.exe"
    model_path.write_bytes(b"gguf")
    binary_path.write_bytes(b"exe")

    class FakeSidecar:
        def __init__(self) -> None:
            self.started = False

        def start(self, resolution):
            self.started = True
            return type(
                "Status",
                (),
                {"running": True, "degraded_reason": None, "last_error": None},
            )()

        def status(self):
            return type(
                "Status",
                (),
                {
                    "running": True,
                    "base_url": "http://127.0.0.1:8080",
                    "model_id": "assistant-small-q4",
                    "route": "voice_chat",
                    "serve_profile_id": "windows_amd64_cpu",
                    "accelerator": "cpu",
                },
            )()

    sidecars: list[FakeSidecar] = []

    def fake_sidecar_factory() -> FakeSidecar:
        sidecar = FakeSidecar()
        sidecars.append(sidecar)
        return sidecar

    monkeypatch.setattr(local_llm_startup, "LocalLLMSidecarService", fake_sidecar_factory)

    entry = ModelEntry(
        family="llm",
        name="assistant-small-q4",
        config={
            "local_path": str(model_path),
            "routes": ["voice_chat"],
            "generation_defaults": {"max_tokens": 16},
            "serve_profiles": {
                "windows_amd64_cpu": {
                    "os": "windows",
                    "arch": "amd64",
                    "accelerator": "cpu",
                    "binary_path": str(binary_path),
                    "base_url": "http://127.0.0.1:8080",
                },
            },
        },
    )
    monkeypatch.setattr(
        local_llm_startup,
        "resolve_llm_serve_profile",
        lambda *args, **kwargs: __import__("backend.app.models.llm_profiles", fromlist=["resolve_llm_serve_profile"]).resolve_llm_serve_profile(
            *args,
            **{**kwargs, "entry": entry},
        ),
    )
    monkeypatch.setattr(
        local_llm_startup,
        "select_llm_model",
        lambda *args, **kwargs: type(
            "Selection",
            (),
            {
                "model_id": "assistant-small-q4",
                "mode": "dev",
                "policy": "auto",
                "role": "portable",
                "reason": "policy auto selected assistant-small-q4",
            },
        )(),
    )

    result = prepare_managed_local_llm(
        HardwareProfile(os_name="windows", arch="amd64"),
        _preflight(),
        settings=_settings(managed=True),
        readiness_probe=lambda base_url, timeout: (True, "ready"),
    )

    assert result.runtime is not None
    assert result.sidecar is sidecars[0]
    assert sidecars[0].started is True
    assert result.runtime.model == "assistant-small-q4"
    assert result.runtime.serve_profile_id == "windows_amd64_cpu"
    assert result.runtime.model_mode == "dev"
    assert result.runtime.model_policy == "auto"
    assert result.runtime.model_role == "portable"


def test_wait_for_llama_cpp_ready_reports_health_and_models_phase_durations(monkeypatch) -> None:
    monotonic_values = iter((0.0, 0.0, 0.001, 0.004, 0.005, 0.011))
    monkeypatch.setattr(local_llm_startup.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(
        local_llm_startup.httpx,
        "get",
        lambda url, timeout: _Response({"data": []}) if url.endswith("/v1/models") else _Response(),
    )
    durations: dict[str, float] = {}

    ready, reason = local_llm_startup.wait_for_llama_cpp_ready(
        "http://127.0.0.1:8080",
        90.0,
        phase_durations_ms=durations,
    )

    assert ready is True
    assert reason == "health and /v1/models reachable"
    assert durations == {
        "health_readiness": pytest.approx(4.0),
        "models_readiness": pytest.approx(6.0),
    }
