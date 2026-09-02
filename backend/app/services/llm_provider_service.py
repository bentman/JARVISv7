from __future__ import annotations

from dataclasses import dataclass, replace

from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.core.settings import Settings, load_settings
from backend.app.hardware.preflight import PreflightResult
from backend.app.routing.provider_router import RoutedLLM
from backend.app.routing.runtime_selector import SelectionTrace
from backend.app.runtimes.llm.base import LLMBase
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.runtimes.llm.provider_runtime import (
    AnthropicMessagesLLM,
    HTTPProviderLLM,
    OpenAICompatibleLLM,
    OpenAIResponsesLLM,
)
from backend.app.services.llm_provider_profiles import (
    LLMProviderProfileStore,
    ProviderProfile,
    ProviderSelection,
    SecretStoreLockedError,
)
from backend.app.services.local_llm_sidecar import LocalLLMSidecarService
from backend.app.services.local_llm_startup import prepare_managed_local_llm


class UnavailableProviderLLM(LLMBase):
    def __init__(self, kind: str, reason: str, context_size: int) -> None:
        self.kind = kind
        self.reason = reason
        self.context_size = context_size

    def generate(self, prompt: str, **kwargs: object) -> str:
        raise RuntimeError(self.reason)

    def is_available(self) -> bool:
        return False

    def runtime_name(self) -> str:
        return self.kind

    def context_window(self) -> int:
        return self.context_size


@dataclass(slots=True)
class LLMProviderStartup:
    runtime: RoutedLLM
    profiles: dict[str, ProviderProfile]
    selection: ProviderSelection
    trace: SelectionTrace
    sidecar: LocalLLMSidecarService | None = None


def prepare_llm_providers(
    hardware_profile: HardwareProfile,
    preflight: PreflightResult,
    *,
    flags: CapabilityFlags | None = None,
    settings: Settings | None = None,
    store: LLMProviderProfileStore | None = None,
) -> LLMProviderStartup:
    resolved_settings = settings or load_settings()
    profile_store = store or LLMProviderProfileStore()
    profiles = {profile.profile_id: profile for profile in profile_store.list_profiles(resolved_settings)}
    selection = profile_store.get_selection(resolved_settings)
    selected_ids = {
        profile_id
        for profile_id in (
            selection.primary_profile_id,
            selection.local_fallback_profile_id,
            selection.cloud_profile_id if selection.cloud_escalation_enabled else None,
        )
        if profile_id is not None
    }
    runtimes: dict[str, LLMBase] = {}
    sidecar: LocalLLMSidecarService | None = None
    managed_resolution = None

    for profile_id in selected_ids:
        profile = profiles[profile_id]
        if profile.kind == "managed_llama_cpp":
            managed_settings = resolved_settings
            if selection.persisted:
                managed_settings = replace(
                    resolved_settings,
                    use_local_model=True,
                    llama_cpp_managed=True,
                    llama_cpp_managed_explicit=True,
                    llama_cpp_base_url="",
                    llama_cpp_base_url_explicit=False,
                )
            startup = prepare_managed_local_llm(
                hardware_profile,
                preflight,
                flags=flags,
                settings=managed_settings,
            )
            sidecar = startup.sidecar
            managed_resolution = startup.resolution
            runtimes[profile_id] = startup.runtime or UnavailableProviderLLM(
                profile.kind,
                startup.degraded_reason or "managed llama.cpp is unavailable",
                profile.context_window,
            )
            continue
        runtimes[profile_id] = _profile_runtime(profile_store, profile)

    primary = profiles[selection.primary_profile_id]
    primary_runtime = runtimes[selection.primary_profile_id]
    trace = SelectionTrace(
        runtime_name=primary_runtime.runtime_name(),
        reason="operator provider profile selected",
        model_id=getattr(primary_runtime, "model", primary.model),
        route=getattr(managed_resolution, "route", None),
        serve_profile_id=getattr(managed_resolution, "serve_profile_id", primary.profile_id),
        accelerator=getattr(managed_resolution, "accelerator", "remote" if primary.cloud_eligible else "external"),
        base_url=primary.endpoint or getattr(managed_resolution, "base_url", None),
        selected_reason=f"selected provider profile {primary.name}",
        degraded_reason=getattr(primary_runtime, "reason", None),
        model_mode=getattr(managed_resolution, "model_mode", None),
        model_policy=getattr(managed_resolution, "model_policy", None),
        model_role=getattr(managed_resolution, "model_role", None),
        model_selection_reason=getattr(managed_resolution, "model_selection_reason", None),
    )
    return LLMProviderStartup(
        runtime=RoutedLLM(profiles=profiles, runtimes=runtimes, selection=selection),
        profiles=profiles,
        selection=selection,
        trace=trace,
        sidecar=sidecar,
    )


def _profile_runtime(store: LLMProviderProfileStore, profile: ProviderProfile) -> LLMBase:
    try:
        api_key = None if profile.builtin else store.read_secret(profile.profile_id, "api_key")
    except SecretStoreLockedError as exc:
        return UnavailableProviderLLM(profile.kind, str(exc), profile.context_window)
    if profile.kind in {"openai", "anthropic"} and not api_key:
        return UnavailableProviderLLM(profile.kind, "provider credential is not configured", profile.context_window)
    assert profile.endpoint is not None
    assert profile.model is not None
    if profile.kind == "ollama":
        return OllamaLLM(
            base_url=profile.endpoint,
            model=profile.model,
            num_ctx=profile.context_window,
            timeout=profile.timeout_seconds,
            enabled=True,
        )
    if profile.kind == "openai_compatible":
        return _http_provider_runtime(OpenAICompatibleLLM, profile, api_key)
    if profile.kind == "openai":
        return _http_provider_runtime(OpenAIResponsesLLM, profile, api_key)
    if profile.kind == "anthropic":
        return _http_provider_runtime(AnthropicMessagesLLM, profile, api_key)
    return UnavailableProviderLLM(profile.kind, "unsupported provider kind", profile.context_window)


def _http_provider_runtime(
    runtime_type: type[HTTPProviderLLM],
    profile: ProviderProfile,
    api_key: str | None,
) -> HTTPProviderLLM:
    assert profile.endpoint is not None
    assert profile.model is not None
    return runtime_type(
        profile_id=profile.profile_id,
        profile_name=profile.name,
        provider_kind=profile.kind,
        endpoint=profile.endpoint,
        model=profile.model,
        context_size=profile.context_window,
        timeout=profile.timeout_seconds,
        api_key=api_key,
    )


def provider_model_discovery(store: LLMProviderProfileStore, profile: ProviderProfile) -> list[dict[str, object]]:
    runtime = _profile_runtime(store, profile)
    if isinstance(runtime, UnavailableProviderLLM):
        raise RuntimeError(runtime.reason)
    if isinstance(runtime, OllamaLLM):
        response = runtime.client.get(f"{runtime.base_url}/api/tags", timeout=runtime.timeout)
        response.raise_for_status()
        payload = response.json()
        values = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(values, list):
            raise RuntimeError("Ollama model response is invalid")
        return [
            {"id": item["name"]}
            for item in values
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
    if isinstance(runtime, HTTPProviderLLM):
        return runtime.discover_models()
    raise RuntimeError("model discovery is unavailable")
