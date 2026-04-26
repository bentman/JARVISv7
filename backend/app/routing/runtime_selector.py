from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
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


class NullLLMRuntime(LLMBase):
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def runtime_name(self) -> str:
        return "null"

    def is_available(self) -> bool:
        return False

    def generate(self, prompt: str, **kwargs: object) -> str:
        raise RuntimeError(self.reason)


def _cloud_runtimes(policy: dict[str, Any]) -> list[LLMBase]:
    llm_policy = policy.get("llm", {}) if isinstance(policy.get("llm", {}), dict) else {}
    provider_policy = (
        policy.get("cloud_providers", {}) if isinstance(policy.get("cloud_providers", {}), dict) else {}
    )
    cloud_enabled = bool(llm_policy.get("cloud_enabled", False))
    return [
        ClaudeLLM(cloud_enabled, provider_policy.get("claude", {}).get("api_key_env", "ANTHROPIC_API_KEY")),
        OpenAILLM(cloud_enabled, provider_policy.get("openai", {}).get("api_key_env", "OPENAI_API_KEY")),
        GeminiLLM(cloud_enabled, provider_policy.get("gemini", {}).get("api_key_env", "GEMINI_API_KEY")),
        XaiLLM(cloud_enabled, provider_policy.get("xai", {}).get("api_key_env", "XAI_API_KEY")),
        ZaiLLM(cloud_enabled, provider_policy.get("zai", {}).get("api_key_env", "ZAI_API_KEY")),
    ]


def select_llm(
    policy: dict[str, Any],
    preflight: PreflightResult,
    profile: HardwareProfile,
    ollama: OllamaLLM | None = None,
) -> tuple[LLMBase, SelectionTrace]:
    local = LlamaCppLLM()
    if local.is_available():
        return local, SelectionTrace(local.runtime_name(), "local llama.cpp available")

    ollama_runtime = ollama or OllamaLLM()
    if ollama_runtime.is_available():
        return ollama_runtime, SelectionTrace("ollama", ollama_runtime.reason)

    for runtime in _cloud_runtimes(policy):
        if runtime.is_available():
            return runtime, SelectionTrace(runtime.runtime_name(), getattr(runtime, "reason", "available"))

    reason = "no LLM runtime available"
    return NullLLMRuntime(reason), SelectionTrace("null", reason)