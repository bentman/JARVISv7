from __future__ import annotations

from types import SimpleNamespace

from backend.app.core.capabilities import HardwareProfile
from backend.app.core.settings import Settings
from backend.app.hardware.preflight import PreflightResult
from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.runtimes.llm.provider_runtime import OpenAICompatibleLLM
from backend.app.services import llm_provider_service
from backend.app.services.llm_provider_profiles import (
    BUILTIN_MANAGED_PROFILE_ID,
    LEGACY_EXTERNAL_PROFILE_ID,
    LEGACY_OLLAMA_PROFILE_ID,
    LLMProviderProfileStore,
)
from backend.app.services.llm_provider_service import prepare_llm_providers


def _store(tmp_path, monkeypatch):
    monkeypatch.delenv("JARVIS_SECRET_STORE_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("KEEP=value\n", encoding="utf-8")
    return LLMProviderProfileStore(tmp_path / "operator.sqlite", env_path)


def test_prepare_provider_service_preserves_external_env_compatibility_without_sidecar(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    settings = Settings(
        use_local_model=True,
        use_ollama=False,
        llama_cpp_managed=False,
        llama_cpp_managed_explicit=True,
        llama_cpp_base_url="http://127.0.0.1:8888",
        llama_cpp_base_url_explicit=True,
        llama_cpp_model_name="unsloth-model",
        llama_cpp_context_size=65536,
        llama_cpp_timeout_seconds=50,
    )

    startup = prepare_llm_providers(
        HardwareProfile(os_name="windows", arch="amd64"),
        PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={}),
        settings=settings,
        store=store,
    )

    assert startup.selection.primary_profile_id == LEGACY_EXTERNAL_PROFILE_ID
    assert startup.sidecar is None
    runtime = startup.runtime.runtimes[LEGACY_EXTERNAL_PROFILE_ID]
    assert isinstance(runtime, OpenAICompatibleLLM)
    assert runtime.endpoint == "http://127.0.0.1:8888/v1"
    assert runtime.model == "unsloth-model"
    assert runtime.context_window() == 65536


def test_prepare_provider_service_preserves_managed_then_ollama_env_order(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    managed_runtime = LlamaCppLLM(managed=False)
    captured_settings = []

    def prepare(profile, preflight, *, flags, settings):
        captured_settings.append(settings)
        return SimpleNamespace(
            runtime=managed_runtime,
            sidecar=None,
            resolution=None,
            degraded_reason=None,
        )

    monkeypatch.setattr(llm_provider_service, "prepare_managed_local_llm", prepare)
    settings = Settings(use_local_model=True, use_ollama=True, ollama_model="ollama-model")
    startup = prepare_llm_providers(
        HardwareProfile(os_name="windows", arch="amd64"),
        PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={}),
        settings=settings,
        store=store,
    )

    assert startup.selection.primary_profile_id == BUILTIN_MANAGED_PROFILE_ID
    assert startup.selection.local_fallback_profile_id == LEGACY_OLLAMA_PROFILE_ID
    assert captured_settings[0] is settings
    assert startup.runtime.runtimes[BUILTIN_MANAGED_PROFILE_ID] is managed_runtime
    assert startup.runtime.runtimes[LEGACY_OLLAMA_PROFILE_ID].runtime_name() == "ollama"


def test_saved_managed_selection_overrides_disabled_env_bootstrap(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    store.set_selection(
        primary_profile_id=BUILTIN_MANAGED_PROFILE_ID,
        local_fallback_profile_id=None,
        cloud_escalation_enabled=False,
        cloud_profile_id=None,
    )
    captured_settings = []

    def prepare(profile, preflight, *, flags, settings):
        captured_settings.append(settings)
        return SimpleNamespace(
            runtime=LlamaCppLLM(managed=False),
            sidecar=None,
            resolution=None,
            degraded_reason=None,
        )

    monkeypatch.setattr(llm_provider_service, "prepare_managed_local_llm", prepare)
    prepare_llm_providers(
        HardwareProfile(os_name="windows", arch="amd64"),
        PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={}),
        settings=Settings(use_local_model=False, use_ollama=False),
        store=store,
    )

    assert captured_settings[0].use_local_model is True
    assert captured_settings[0].llama_cpp_managed is True
    assert captured_settings[0].llama_cpp_managed_explicit is True
