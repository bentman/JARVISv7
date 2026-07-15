from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.core.capabilities import HardwareProfile
from backend.app.core.settings import Settings
from backend.app.hardware.preflight import PreflightResult
from backend.app.runtimes.internetsearch import (
    DDGSRuntime,
    NullSearchRuntime,
    SearchBase,
    SearXNGRuntime,
    TavilyRuntime,
)
from backend.app.runtimes.llm.base import LLMBase
from backend.app.runtimes.llm.claude_runtime import ClaudeLLM
from backend.app.runtimes.llm.gemini_runtime import GeminiLLM
from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.runtimes.llm.openai_runtime import OpenAILLM
from backend.app.runtimes.llm.xai_runtime import XaiLLM
from backend.app.runtimes.llm.zai_runtime import ZaiLLM


@dataclass(frozen=True, slots=True)
class SelectionTrace:
    runtime_name: str
    reason: str
    model_id: str | None = None
    route: str | None = None
    serve_profile_id: str | None = None
    accelerator: str | None = None
    base_url: str | None = None
    selected_reason: str | None = None
    degraded_reason: str | None = None
    model_mode: str | None = None
    model_policy: str | None = None
    model_role: str | None = None
    model_selection_reason: str | None = None


class NullLLMRuntime(LLMBase):
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def runtime_name(self) -> str:
        return "null"

    def is_available(self) -> bool:
        return False

    def generate(self, prompt: str, **kwargs: object) -> str:
        raise RuntimeError(self.reason)


def _provider_api_key_env(provider_policy: dict[str, Any], name: str, default: str) -> str:
    # A bare `name:` entry in policies.yaml parses to None; a non-dict entry
    # must not crash startup with AttributeError.
    entry = provider_policy.get(name)
    if not isinstance(entry, dict):
        return default
    value = entry.get("api_key_env", default)
    return value if isinstance(value, str) and value else default


def _cloud_runtimes(policy: dict[str, Any]) -> list[LLMBase]:
    llm_policy = policy.get("llm", {}) if isinstance(policy.get("llm", {}), dict) else {}
    provider_policy = (
        policy.get("cloud_providers", {}) if isinstance(policy.get("cloud_providers", {}), dict) else {}
    )
    cloud_enabled = bool(llm_policy.get("cloud_enabled", False))
    return [
        ClaudeLLM(cloud_enabled, _provider_api_key_env(provider_policy, "claude", "ANTHROPIC_API_KEY")),
        OpenAILLM(cloud_enabled, _provider_api_key_env(provider_policy, "openai", "OPENAI_API_KEY")),
        GeminiLLM(cloud_enabled, _provider_api_key_env(provider_policy, "gemini", "GEMINI_API_KEY")),
        XaiLLM(cloud_enabled, _provider_api_key_env(provider_policy, "xai", "XAI_API_KEY")),
        ZaiLLM(cloud_enabled, _provider_api_key_env(provider_policy, "zai", "ZAI_API_KEY")),
    ]


def select_llm(
    policy: dict[str, Any],
    preflight: PreflightResult,
    profile: HardwareProfile,
    local: LlamaCppLLM | None = None,
    ollama: OllamaLLM | None = None,
) -> tuple[LLMBase, SelectionTrace]:
    local_runtime = local or LlamaCppLLM()
    if local_runtime.is_available():
        return local_runtime, _local_trace(local_runtime, "local llama.cpp available")
    local_degraded_reason = getattr(local_runtime, "reason", "local llama.cpp unavailable")

    ollama_runtime = ollama or OllamaLLM()
    if ollama_runtime.is_available():
        return ollama_runtime, SelectionTrace(
            "ollama",
            ollama_runtime.reason,
            degraded_reason=local_degraded_reason,
        )

    for runtime in _cloud_runtimes(policy):
        if runtime.is_available():
            return runtime, SelectionTrace(
                runtime.runtime_name(),
                getattr(runtime, "reason", "available"),
                degraded_reason=local_degraded_reason,
            )

    reason = f"no LLM runtime available; local={local_degraded_reason}; ollama={ollama_runtime.reason}"
    return NullLLMRuntime(reason), SelectionTrace("null", reason)


def _local_trace(local: LlamaCppLLM, reason: str) -> SelectionTrace:
    return SelectionTrace(
        runtime_name=local.runtime_name(),
        reason=reason,
        model_id=getattr(local, "model", None),
        route=getattr(local, "route", None),
        serve_profile_id=getattr(local, "serve_profile_id", None),
        accelerator=getattr(local, "accelerator", None),
        base_url=getattr(local, "base_url", None),
        selected_reason=getattr(local, "selected_reason", None),
        degraded_reason=getattr(local, "reason", None),
        model_mode=getattr(local, "model_mode", None),
        model_policy=getattr(local, "model_policy", None),
        model_role=getattr(local, "model_role", None),
        model_selection_reason=getattr(local, "model_selection_reason", None),
    )


def select_search_runtime(settings: Settings) -> tuple[SearchBase, SelectionTrace]:
    providers: list[SearchBase] = [
        SearXNGRuntime(settings),
        DDGSRuntime(settings),
        TavilyRuntime(settings),
    ]
    for provider in providers:
        if provider.is_available():
            return provider, SelectionTrace(provider.runtime_name(), "available")
    reason = "no search runtime available"
    return NullSearchRuntime(reason), SelectionTrace("null", reason)
