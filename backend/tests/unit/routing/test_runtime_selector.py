from __future__ import annotations

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.routing.runtime_selector import NullLLMRuntime, select_llm
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM


class _AvailableOllama(OllamaLLM):
    def __init__(self) -> None:
        super().__init__(base_url="http://test", model="phi4-mini", enabled=True)
        self.reason = "test ollama available"

    def is_available(self) -> bool:
        self.reason = "test ollama available"
        return True


class _UnavailableOllama(OllamaLLM):
    def __init__(self) -> None:
        super().__init__(base_url="http://test", model="phi4-mini", enabled=True)
        self.reason = "test ollama unavailable"

    def is_available(self) -> bool:
        self.reason = "test ollama unavailable"
        return False


class _AvailableLocal:
    model = "assistant-small-q4"
    route = "voice_chat"
    serve_profile_id = "windows_amd64_cpu"
    accelerator = "cpu"
    base_url = "http://127.0.0.1:8080"
    selected_reason = "selected current-host CPU serve profile windows_amd64_cpu"
    reason = "llama.cpp /v1/models reachable"

    def runtime_name(self) -> str:
        return "llama.cpp"

    def is_available(self) -> bool:
        self.reason = "llama.cpp /v1/models reachable"
        return True

    def generate(self, prompt: str, **kwargs: object) -> str:
        return "local response"


class _UnavailableLocal(_AvailableLocal):
    reason = "Degraded-no-local-model-artifact"

    def is_available(self) -> bool:
        self.reason = "Degraded-no-local-model-artifact"
        return False


def _preflight() -> PreflightResult:
    return PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={})


def test_selector_prefers_viable_local_before_ollama():
    runtime, trace = select_llm(
        {"llm": {"cloud_enabled": True}, "cloud_providers": {}},
        _preflight(),
        HardwareProfile(),
        local=_AvailableLocal(),  # type: ignore[arg-type]
        ollama=_AvailableOllama(),
    )

    assert runtime.runtime_name() == "llama.cpp"
    assert trace.runtime_name == "llama.cpp"
    assert trace.model_id == "assistant-small-q4"
    assert trace.route == "voice_chat"
    assert trace.serve_profile_id == "windows_amd64_cpu"
    assert trace.accelerator == "cpu"
    assert trace.base_url == "http://127.0.0.1:8080"
    assert trace.selected_reason == "selected current-host CPU serve profile windows_amd64_cpu"


def test_selector_prefers_ollama_over_cloud_when_ollama_reachable():
    runtime, trace = select_llm(
        {"llm": {"cloud_enabled": True}, "cloud_providers": {}},
        _preflight(),
        HardwareProfile(),
        local=_UnavailableLocal(),  # type: ignore[arg-type]
        ollama=_AvailableOllama(),
    )

    assert runtime.runtime_name() == "ollama"
    assert trace.runtime_name == "ollama"
    assert "available" in trace.reason
    assert trace.degraded_reason == "Degraded-no-local-model-artifact"


def test_selector_returns_null_when_nothing_available():
    runtime, trace = select_llm(
        {"llm": {"cloud_enabled": False}, "cloud_providers": {}},
        _preflight(),
        HardwareProfile(),
        local=_UnavailableLocal(),  # type: ignore[arg-type]
        ollama=_UnavailableOllama(),
    )

    assert isinstance(runtime, NullLLMRuntime)
    assert trace.runtime_name == "null"
    assert "Degraded-no-local-model-artifact" in trace.reason
    assert "test ollama unavailable" in trace.reason


def test_selector_emits_selection_trace_with_runtime_name_and_reason():
    runtime, trace = select_llm(
        {},
        _preflight(),
        HardwareProfile(),
        local=_UnavailableLocal(),  # type: ignore[arg-type]
        ollama=_AvailableOllama(),
    )

    assert runtime.runtime_name() == trace.runtime_name
    assert trace.reason


def test_selector_skips_local_when_not_available():
    runtime, trace = select_llm(
        {},
        _preflight(),
        HardwareProfile(),
        local=_UnavailableLocal(),  # type: ignore[arg-type]
        ollama=_AvailableOllama(),
    )

    assert runtime.runtime_name() == "ollama"
    assert trace.runtime_name != "llama.cpp"
