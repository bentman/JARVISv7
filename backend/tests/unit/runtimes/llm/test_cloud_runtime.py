from __future__ import annotations

from types import SimpleNamespace

import pytest
from backend.app.cognition.prompt_envelope import PromptEnvelope, PromptSegment
from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.routing.runtime_selector import select_llm
from backend.app.runtimes.llm.claude_runtime import ClaudeLLM
from backend.app.runtimes.llm.gemini_runtime import GeminiLLM
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.runtimes.llm.openai_runtime import OpenAILLM
from backend.app.runtimes.llm.xai_runtime import XaiLLM
from backend.app.runtimes.llm.zai_runtime import ZaiLLM

_OPENAI_COMPAT_CASES = [
    (OpenAILLM, "OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-4o-mini"),
    (GeminiLLM, "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash"),
    (XaiLLM, "XAI_API_KEY", "https://api.x.ai/v1", "grok-3-mini"),
    (ZaiLLM, "ZAI_API_KEY", "https://api.z.ai/api/paas/v4", "glm-4.7"),
]


def _chat_completion_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"choices": [{"message": {"content": content}}]},
    )


def _claude_messages_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"content": [{"type": "text", "text": text}]},
    )


def _envelope() -> PromptEnvelope:
    return PromptEnvelope(
        segments=(
            PromptSegment("application", "instruction", True, "Use short answers."),
            PromptSegment("user", "user_input", False, "What is uptime?"),
        ),
        generation={"temperature": 0.1, "top_p": 0.9, "max_tokens": 80, "stop": ["\nUser:"]},
    )


def test_cloud_runtime_is_available_false_when_policy_gated(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    runtime = ClaudeLLM(cloud_enabled=False)

    assert runtime.is_available() is False
    assert runtime.reason == "claude cloud LLM policy-gated"


def test_cloud_runtime_is_available_false_when_key_env_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runtime = ClaudeLLM(cloud_enabled=True)

    assert runtime.is_available() is False
    assert runtime.reason == "claude API key env var missing: ANTHROPIC_API_KEY"


def test_cloud_runtime_is_available_true_when_enabled_and_key_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    runtime = ClaudeLLM(cloud_enabled=True)

    assert runtime.is_available() is True
    assert runtime.reason == "claude cloud runtime available (policy-enabled, key present)"


@pytest.mark.parametrize(("runtime_cls", "key_env", "base_url", "model"), _OPENAI_COMPAT_CASES)
def test_openai_compat_generate_posts_chat_completion(monkeypatch, runtime_cls, key_env, base_url, model):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json, headers, timeout))
        return _chat_completion_response("cloud answer")

    monkeypatch.setattr("backend.app.runtimes.llm.base.httpx.post", fake_post)
    monkeypatch.setenv(key_env, "secret-token")
    runtime = runtime_cls(cloud_enabled=True)

    assert runtime.generate("hello") == "cloud answer"
    assert calls == [
        (
            f"{base_url}/chat/completions",
            {"model": model, "messages": [{"role": "user", "content": "hello"}]},
            {"Authorization": "Bearer secret-token"},
            60.0,
        )
    ]


def test_openai_compat_generate_envelope_maps_generation_params(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json, headers, timeout))
        return _chat_completion_response("cloud answer")

    monkeypatch.setattr("backend.app.runtimes.llm.base.httpx.post", fake_post)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-token")
    runtime = OpenAILLM(cloud_enabled=True, timeout=7.0)

    assert runtime.generate_envelope(_envelope()) == "cloud answer"
    assert calls == [
        (
            "https://api.openai.com/v1/chat/completions",
            {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "[APPLICATION RULES - trusted]\nUse short answers."},
                    {"role": "user", "content": "[USER REQUEST - user instruction]\nWhat is uptime?"},
                ],
                "temperature": 0.1,
                "top_p": 0.9,
                "max_tokens": 80,
                "stop": ["\nUser:"],
            },
            {"Authorization": "Bearer secret-token"},
            7.0,
        )
    ]


def test_openai_compat_constructor_overrides_model_and_base_url(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json))
        return _chat_completion_response("cloud answer")

    monkeypatch.setattr("backend.app.runtimes.llm.base.httpx.post", fake_post)
    monkeypatch.setenv("XAI_API_KEY", "secret-token")
    runtime = XaiLLM(cloud_enabled=True, model="grok-override", base_url="http://proxy/v1")

    assert runtime.generate("hello") == "cloud answer"
    assert calls[0][0] == "http://proxy/v1/chat/completions"
    assert calls[0][1]["model"] == "grok-override"


def test_openai_compat_generate_fails_on_empty_response(monkeypatch):
    monkeypatch.setattr(
        "backend.app.runtimes.llm.base.httpx.post",
        lambda *args, **kwargs: _chat_completion_response(""),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "secret-token")

    with pytest.raises(RuntimeError, match="openai chat completion returned an empty response"):
        OpenAILLM(cloud_enabled=True).generate("hello")


def test_openai_compat_generate_fails_on_missing_choices(monkeypatch):
    monkeypatch.setattr(
        "backend.app.runtimes.llm.base.httpx.post",
        lambda *args, **kwargs: SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"choices": []}),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "secret-token")

    with pytest.raises(RuntimeError, match="openai chat completion returned no choices"):
        OpenAILLM(cloud_enabled=True).generate("hello")


def test_openai_compat_generate_fails_on_http_error(monkeypatch):
    def raise_status():
        raise RuntimeError("HTTP 401")

    monkeypatch.setattr(
        "backend.app.runtimes.llm.base.httpx.post",
        lambda *args, **kwargs: SimpleNamespace(raise_for_status=raise_status),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "secret-token")

    with pytest.raises(RuntimeError, match="openai chat completion failed: HTTP 401"):
        OpenAILLM(cloud_enabled=True).generate("hello")


def test_openai_compat_generate_fails_when_key_env_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="openai API key env var missing: OPENAI_API_KEY"):
        OpenAILLM(cloud_enabled=True).generate("hello")


def test_claude_generate_posts_anthropic_messages_payload(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json, headers, timeout))
        return _claude_messages_response("claude answer")

    monkeypatch.setattr("backend.app.runtimes.llm.base.httpx.post", fake_post)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-token")
    runtime = ClaudeLLM(cloud_enabled=True)

    assert runtime.generate("hello") == "claude answer"
    assert calls == [
        (
            "https://api.anthropic.com/v1/messages",
            {
                "model": "claude-sonnet-4-5",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "hello"}],
            },
            {"x-api-key": "secret-token", "anthropic-version": "2023-06-01"},
            60.0,
        )
    ]


def test_claude_generate_envelope_splits_system_messages(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json, headers, timeout))
        return _claude_messages_response("claude answer")

    monkeypatch.setattr("backend.app.runtimes.llm.base.httpx.post", fake_post)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-token")
    runtime = ClaudeLLM(cloud_enabled=True)

    assert runtime.generate_envelope(_envelope()) == "claude answer"
    payload = calls[0][1]
    assert calls[0][0] == "https://api.anthropic.com/v1/messages"
    assert payload["system"] == "[APPLICATION RULES - trusted]\nUse short answers."
    assert payload["messages"] == [
        {"role": "user", "content": "[USER REQUEST - user instruction]\nWhat is uptime?"}
    ]
    assert all(message["role"] != "system" for message in payload["messages"])
    assert payload["max_tokens"] == 80
    assert payload["temperature"] == 0.1
    assert payload["top_p"] == 0.9
    assert payload["stop_sequences"] == ["\nUser:"]


def test_claude_generate_fails_on_empty_response(monkeypatch):
    monkeypatch.setattr(
        "backend.app.runtimes.llm.base.httpx.post",
        lambda *args, **kwargs: _claude_messages_response(""),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-token")

    with pytest.raises(RuntimeError, match="claude chat completion returned an empty response"):
        ClaudeLLM(cloud_enabled=True).generate("hello")


def test_claude_generate_fails_on_missing_content(monkeypatch):
    monkeypatch.setattr(
        "backend.app.runtimes.llm.base.httpx.post",
        lambda *args, **kwargs: SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"content": []}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-token")

    with pytest.raises(RuntimeError, match="claude chat completion returned no content"):
        ClaudeLLM(cloud_enabled=True).generate("hello")


def test_claude_generate_fails_on_http_error(monkeypatch):
    def raise_status():
        raise RuntimeError("HTTP 529")

    monkeypatch.setattr(
        "backend.app.runtimes.llm.base.httpx.post",
        lambda *args, **kwargs: SimpleNamespace(raise_for_status=raise_status),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-token")

    with pytest.raises(RuntimeError, match="claude chat completion failed: HTTP 529"):
        ClaudeLLM(cloud_enabled=True).generate("hello")


def test_cloud_runtime_uses_owned_client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-token")
    runtime = OpenAILLM(cloud_enabled=True)
    called = []

    def fake_post(url, *, json, headers, timeout):
        called.append(url)
        return _chat_completion_response("cloud answer")

    monkeypatch.setattr(runtime.client, "post", fake_post)

    assert runtime.generate("hello") == "cloud answer"
    assert called == ["https://api.openai.com/v1/chat/completions"]


class _UnavailableLocal:
    reason = "Degraded-no-local-model-artifact"

    def runtime_name(self) -> str:
        return "llama.cpp"

    def is_available(self) -> bool:
        return False

    def generate(self, prompt: str, **kwargs: object) -> str:
        raise RuntimeError("local unavailable")


class _UnavailableOllama(OllamaLLM):
    def __init__(self) -> None:
        super().__init__(base_url="http://test", model="phi4-mini", enabled=True)
        self.reason = "test ollama unavailable"

    def is_available(self) -> bool:
        self.reason = "test ollama unavailable"
        return False


def test_selector_cloud_fallback_returns_runtime_that_generates(monkeypatch):
    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "ZAI_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv("TEST_CLAUDE_KEY", "secret-token")
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json, headers))
        return _claude_messages_response("cloud fallback answer")

    monkeypatch.setattr("backend.app.runtimes.llm.base.httpx.post", fake_post)
    policy = {
        "llm": {"cloud_enabled": True},
        "cloud_providers": {
            "claude": {
                "api_key_env": "TEST_CLAUDE_KEY",
                "model": "claude-test-model",
                "base_url": "http://cloud-test/v1",
            }
        },
    }

    runtime, trace = select_llm(
        policy,
        PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={}),
        HardwareProfile(),
        local=_UnavailableLocal(),  # type: ignore[arg-type]
        ollama=_UnavailableOllama(),
    )

    assert runtime.runtime_name() == "claude"
    assert trace.runtime_name == "claude"
    assert trace.reason == "claude cloud runtime available (policy-enabled, key present)"
    assert trace.degraded_reason == "Degraded-no-local-model-artifact"
    assert runtime.generate("hello") == "cloud fallback answer"
    assert calls[0][0] == "http://cloud-test/v1/messages"
    assert calls[0][1]["model"] == "claude-test-model"
    assert calls[0][2] == {"x-api-key": "secret-token", "anthropic-version": "2023-06-01"}


def test_selector_cloud_fallback_uses_default_model_when_policy_entry_bare(monkeypatch):
    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "ZAI_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-token")
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json))
        return _chat_completion_response("cloud answer")

    monkeypatch.setattr("backend.app.runtimes.llm.base.httpx.post", fake_post)
    policy = {"llm": {"cloud_enabled": True}, "cloud_providers": {"openai": None}}

    runtime, trace = select_llm(
        policy,
        PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={}),
        HardwareProfile(),
        local=_UnavailableLocal(),  # type: ignore[arg-type]
        ollama=_UnavailableOllama(),
    )

    assert runtime.runtime_name() == "openai"
    assert trace.runtime_name == "openai"
    assert runtime.generate("hello") == "cloud answer"
    assert calls[0][0] == "https://api.openai.com/v1/chat/completions"
    assert calls[0][1]["model"] == "gpt-4o-mini"
