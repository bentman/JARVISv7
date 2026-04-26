from __future__ import annotations

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.routing.runtime_selector import NullLLMRuntime, select_llm


class _AvailableOllama(OllamaLLM):
    def __init__(self) -> None:
        super().__init__(base_url="http://test", model="phi4-mini")
        self.reason = "test ollama available"

    def is_available(self) -> bool:
        self.reason = "test ollama available"
        return True


class _UnavailableOllama(OllamaLLM):
    def __init__(self) -> None:
        super().__init__(base_url="http://test", model="phi4-mini")
        self.reason = "test ollama unavailable"

    def is_available(self) -> bool:
        self.reason = "test ollama unavailable"
        return False


def _preflight() -> PreflightResult:
    return PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={})


def test_selector_prefers_ollama_over_cloud_when_ollama_reachable():
    runtime, trace = select_llm(
        {"llm": {"cloud_enabled": True}, "cloud_providers": {}},
        _preflight(),
        HardwareProfile(),
        ollama=_AvailableOllama(),
    )

    assert runtime.runtime_name() == "ollama"
    assert trace.runtime_name == "ollama"
    assert "available" in trace.reason


def test_selector_returns_null_when_nothing_available():
    runtime, trace = select_llm(
        {"llm": {"cloud_enabled": False}, "cloud_providers": {}},
        _preflight(),
        HardwareProfile(),
        ollama=_UnavailableOllama(),
    )

    assert isinstance(runtime, NullLLMRuntime)
    assert trace.runtime_name == "null"


def test_selector_emits_selection_trace_with_runtime_name_and_reason():
    runtime, trace = select_llm({}, _preflight(), HardwareProfile(), ollama=_AvailableOllama())

    assert runtime.runtime_name() == trace.runtime_name
    assert trace.reason


def test_selector_skips_local_when_not_available():
    runtime, trace = select_llm({}, _preflight(), HardwareProfile(), ollama=_AvailableOllama())

    assert runtime.runtime_name() == "ollama"
    assert trace.runtime_name != "llama.cpp"