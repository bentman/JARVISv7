from __future__ import annotations

import pytest
from backend.app.cognition.prompt_envelope import PromptEnvelope, PromptSegment
from backend.app.routing.provider_router import RoutedLLM
from backend.app.runtimes.llm.base import (
    LLMBase,
    ToolCall,
    ToolCallResult,
    ToolDefinition,
)
from backend.app.runtimes.llm.provider_runtime import ProviderRequestError
from backend.app.services.llm_provider_profiles import ProviderProfile, ProviderSelection


class _Runtime(LLMBase):
    def __init__(self, name: str, outcomes: list[str | Exception]) -> None:
        self.name = name
        self.outcomes = outcomes
        self.calls = 0
        self.last_usage = {"total_tokens": 7}

    def generate(self, prompt: str, **kwargs: object) -> str:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def is_available(self) -> bool:
        return True

    def runtime_name(self) -> str:
        return self.name


def _profile(profile_id: str, name: str, kind: str, endpoint: str) -> ProviderProfile:
    return ProviderProfile(profile_id, name, kind, endpoint, "model", 8192, 30)


def _envelope(text: str) -> PromptEnvelope:
    return PromptEnvelope((PromptSegment("user", "user_input", False, text),))


def _router(primary, fallback, cloud, *, enabled=True):
    profiles = {
        "primary": _profile("primary", "Local", "openai_compatible", "http://127.0.0.1:8080/v1"),
        "fallback": _profile("fallback", "Ollama", "ollama", "http://127.0.0.1:11434"),
        "cloud": _profile("cloud", "Claude Pro", "anthropic", "https://api.anthropic.com/v1"),
    }
    runtimes = {"primary": primary, "fallback": fallback, "cloud": cloud}
    selection = ProviderSelection("primary", "fallback", enabled, "cloud")
    return RoutedLLM(profiles=profiles, runtimes=runtimes, selection=selection)


def test_router_uses_primary_then_local_fallback_then_cloud_once():
    primary = _Runtime("local", [ProviderRequestError("offline", escalation_eligible=True)])
    fallback = _Runtime("ollama", [ProviderRequestError("timeout", escalation_eligible=True)])
    cloud = _Runtime("anthropic", ["cloud answer"])
    router = _router(primary, fallback, cloud)

    assert router.generate_envelope(_envelope("answer this")) == "cloud answer"
    assert (primary.calls, fallback.calls, cloud.calls) == (1, 1, 1)
    assert [attempt.trigger for attempt in router.last_attempts] == ["primary", "local_fallback", "failure_escalation"]
    assert router.last_attempts[-1].usage == {"total_tokens": 7}


def test_router_does_not_escalate_authentication_or_context_failures():
    primary = _Runtime("local", [ProviderRequestError("authentication failed", escalation_eligible=False)])
    fallback = _Runtime("ollama", ["unused"])
    cloud = _Runtime("anthropic", ["unused"])
    router = _router(primary, fallback, cloud)

    with pytest.raises(ProviderRequestError, match="authentication"):
        router.generate_envelope(_envelope("answer this"))
    assert (primary.calls, fallback.calls, cloud.calls) == (1, 0, 0)


def test_explicit_cloud_request_routes_directly_and_negation_stays_local():
    primary = _Runtime("local", ["local answer", "local answer"])
    fallback = _Runtime("ollama", ["unused"])
    cloud = _Runtime("anthropic", ["cloud answer"])
    router = _router(primary, fallback, cloud)

    assert router.generate_envelope(_envelope("Please ask Claude about this")) == "cloud answer"
    assert router.last_attempts[0].trigger == "explicit_request"
    assert router.generate_envelope(_envelope("Do not ask Claude; answer locally")) == "local answer"
    assert (primary.calls, cloud.calls) == (1, 1)


def test_explicit_cloud_request_requires_authorization():
    router = _router(_Runtime("local", ["unused"]), _Runtime("ollama", ["unused"]), _Runtime("cloud", ["unused"]), enabled=False)

    with pytest.raises(RuntimeError, match="disabled"):
        router.generate_envelope(_envelope("Use cloud for this"))
    assert all(runtime.calls == 0 for runtime in router.runtimes.values())


def test_explicit_cloud_request_does_not_substitute_another_provider():
    primary = _Runtime("local", ["unused"])
    fallback = _Runtime("ollama", ["unused"])
    cloud = _Runtime("anthropic", ["unused"])
    router = _router(primary, fallback, cloud)

    with pytest.raises(RuntimeError, match="not configured"):
        router.generate_envelope(_envelope("Ask OpenAI about this"))
    assert all(runtime.calls == 0 for runtime in router.runtimes.values())


def test_configured_cloud_profile_name_routes_directly():
    primary = _Runtime("local", ["unused"])
    fallback = _Runtime("ollama", ["unused"])
    cloud = _Runtime("anthropic", ["named cloud answer"])
    router = _router(primary, fallback, cloud)

    assert router.generate_envelope(_envelope("Use Claude Pro for this")) == "named cloud answer"
    assert (primary.calls, fallback.calls, cloud.calls) == (0, 0, 1)


def test_cloud_primary_is_persistent_authorization_for_normal_and_explicit_turns():
    profile = _profile("cloud", "Claude Pro", "anthropic", "https://api.anthropic.com/v1")
    runtime = _Runtime("anthropic", ["normal", "explicit"])
    router = RoutedLLM(
        profiles={"cloud": profile},
        runtimes={"cloud": runtime},
        selection=ProviderSelection("cloud"),
    )

    assert router.generate_envelope(_envelope("answer normally")) == "normal"
    assert router.generate_envelope(_envelope("ask Claude about this")) == "explicit"


class _ToolRuntime(_Runtime):
    """A runtime that implements the tool protocol, so supports_tool_calling() is True."""

    def __init__(self, name: str, outcomes: list[ToolCallResult | Exception]) -> None:
        super().__init__(name, [])
        self.tool_outcomes = outcomes

    def generate_with_tools(self, envelope, tools, **kwargs) -> ToolCallResult:
        self.calls += 1
        outcome = self.tool_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


_TOOLS = (ToolDefinition("search-public-web", "Search", {"type": "object"}),)


def test_a_runtime_without_tool_support_is_skipped_and_the_chain_continues():
    primary = _Runtime("local", [])  # inherits the raising LLMBase implementation
    fallback = _Runtime("ollama", [])
    cloud = _ToolRuntime("anthropic", [ToolCallResult(call=ToolCall("search-public-web", {}))])
    router = _router(primary, fallback, cloud)

    result = router.generate_with_tools(_envelope("look this up"), _TOOLS)

    assert result.call == ToolCall("search-public-web", {})
    assert [attempt.trigger for attempt in router.last_attempts] == [
        "primary", "local_fallback", "failure_escalation",
    ]
    # The skip is recorded as a failed attempt, so the choice of provider stays visible.
    assert [attempt.outcome for attempt in router.last_attempts] == ["failed", "failed", "succeeded"]


def test_the_router_reports_no_tool_support_when_no_candidate_has_it():
    router = _router(_Runtime("local", []), _Runtime("ollama", []), _Runtime("anthropic", []))
    assert router.supports_tool_calling() is False


def test_the_router_reports_tool_support_when_any_candidate_has_it():
    router = _router(_Runtime("local", []), _Runtime("ollama", []), _ToolRuntime("anthropic", []))
    assert router.supports_tool_calling() is True


def test_a_tool_capable_primary_is_not_escalated():
    primary = _ToolRuntime("local", [ToolCallResult(text="answered locally")])
    cloud = _ToolRuntime("anthropic", [])
    router = _router(primary, _Runtime("ollama", []), cloud)

    result = router.generate_with_tools(_envelope("hello"), _TOOLS)

    assert (result.text, result.call) == ("answered locally", None)
    assert cloud.calls == 0
