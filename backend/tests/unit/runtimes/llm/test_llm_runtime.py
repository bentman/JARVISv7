from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.cognition.prompt_envelope import PromptEnvelope, PromptSegment
from backend.app.models.catalog import get_model_entry
from backend.app.runtimes.llm.claude_runtime import ClaudeLLM
from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.routing.runtime_selector import NullLLMRuntime


def test_local_runtime_is_available_returns_false():
    runtime = LlamaCppLLM(managed=False)

    assert runtime.is_available() is False
    assert "disabled" in runtime.reason


def test_local_runtime_is_available_true_when_models_endpoint_reachable(monkeypatch):
    monkeypatch.setattr(
        "backend.app.runtimes.llm.local_runtime.httpx.get",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"data": [{"id": "assistant-small-q4"}]},
        ),
    )
    runtime = LlamaCppLLM(base_url="http://test", model="assistant-small-q4")

    assert runtime.is_available() is True
    assert runtime.reason == "llama.cpp /v1/models reachable"


def test_local_runtime_is_available_falls_back_to_health_endpoint(monkeypatch):
    calls = []

    def fake_get(url, *, timeout):
        calls.append((url, timeout))
        if url.endswith("/v1/models"):
            raise RuntimeError("models route missing")
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr("backend.app.runtimes.llm.local_runtime.httpx.get", fake_get)
    runtime = LlamaCppLLM(base_url="http://test", model="assistant-small-q4")

    assert runtime.is_available() is True
    assert runtime.reason == "llama.cpp health endpoint reachable"
    assert calls[0] == ("http://test/v1/models", 10.0)
    assert calls[1] == ("http://test/health", 10.0)


def test_local_runtime_is_available_false_when_sidecar_status_not_running():
    runtime = LlamaCppLLM(
        sidecar_status=lambda: SimpleNamespace(
            running=False,
            base_url="http://test",
            degraded_reason="sidecar stopped",
            last_error=None,
        )
    )

    assert runtime.is_available() is False
    assert runtime.reason == "sidecar stopped"


def test_local_runtime_is_available_false_when_probe_unavailable(monkeypatch):
    monkeypatch.setattr(
        "backend.app.runtimes.llm.local_runtime.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    runtime = LlamaCppLLM(base_url="http://test", model="assistant-small-q4")

    assert runtime.is_available() is False
    assert "offline" in runtime.reason


def test_local_runtime_is_available_false_on_invalid_models_payload(monkeypatch):
    calls = []

    def fake_get(url, *, timeout):
        calls.append(url)
        if url.endswith("/v1/models"):
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"bad": []})
        raise RuntimeError("no health")

    monkeypatch.setattr("backend.app.runtimes.llm.local_runtime.httpx.get", fake_get)
    runtime = LlamaCppLLM(base_url="http://test", model="assistant-small-q4")

    assert runtime.is_available() is False
    assert "invalid payload" in runtime.reason


def test_local_runtime_generate_posts_openai_chat_completion(monkeypatch):
    calls = []

    def fake_post(url, *, json, timeout):
        calls.append((url, json, timeout))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": "ready"}}]},
        )

    monkeypatch.setattr("backend.app.runtimes.llm.local_runtime.httpx.post", fake_post)
    runtime = LlamaCppLLM(
        base_url="http://test",
        model="assistant-small-q4",
        timeout=7.0,
        generation_defaults={
            "temperature": 0.4,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.08,
            "max_tokens": 256,
            "stop": ["\nUser:"],
            "chat_template_kwargs": {"enable_thinking": False},
        },
    )

    assert runtime.generate("Reply ready") == "ready"
    assert calls == [
        (
            "http://test/v1/chat/completions",
            {
                "model": "assistant-small-q4",
                "messages": [{"role": "user", "content": "Reply ready"}],
                "stream": False,
                "temperature": 0.4,
                "top_p": 0.9,
                "top_k": 40,
                "repeat_penalty": 1.08,
                "max_tokens": 256,
                "stop": ["\nUser:"],
                "chat_template_kwargs": {"enable_thinking": False},
            },
            7.0,
        )
    ]


def test_local_runtime_generate_recovers_managed_sidecar_before_post(monkeypatch):
    recoveries = []
    status_ref = {
        "status": SimpleNamespace(
            running=False,
            base_url="http://test",
            model_id="assistant-small-q4",
            route="voice_chat",
            serve_profile_id="windows_amd64_cpu",
            accelerator="gpu.cuda",
            degraded_reason="sidecar stopped",
            last_error=None,
        )
    }

    def recover():
        recoveries.append("restart")
        status_ref["status"] = SimpleNamespace(
            running=True,
            base_url="http://test",
            model_id="assistant-small-q4",
            route="voice_chat",
            serve_profile_id="windows_amd64_cpu",
            accelerator="gpu.cuda",
            degraded_reason=None,
            last_error=None,
        )
        return status_ref["status"]

    monkeypatch.setattr(
        "backend.app.runtimes.llm.local_runtime.httpx.get",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"data": [{"id": "assistant-small-q4"}]},
        ),
    )
    monkeypatch.setattr(
        "backend.app.runtimes.llm.local_runtime.httpx.post",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": "ready"}}]},
        ),
    )

    runtime = LlamaCppLLM(
        sidecar_status=lambda: status_ref["status"],
        sidecar_recover=recover,
        managed=True,
    )

    assert runtime.generate("hello") == "ready"
    assert recoveries == ["restart"]
    assert runtime.accelerator == "gpu.cuda"


def test_local_runtime_generate_retries_after_connection_failure_with_managed_recovery(monkeypatch):
    recoveries = []
    posts = []
    running_status = SimpleNamespace(
        running=True,
        base_url="http://test",
        model_id="assistant-small-q4",
        route="voice_chat",
        serve_profile_id="windows_amd64_cpu",
        accelerator="gpu.cuda",
        degraded_reason=None,
        last_error=None,
    )

    monkeypatch.setattr(
        "backend.app.runtimes.llm.local_runtime.httpx.get",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"data": [{"id": "assistant-small-q4"}]},
        ),
    )

    def fake_post(*args, **kwargs):
        posts.append(args[0])
        if len(posts) == 1:
            raise RuntimeError("connection refused")
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": "ready after restart"}}]},
        )

    monkeypatch.setattr("backend.app.runtimes.llm.local_runtime.httpx.post", fake_post)

    runtime = LlamaCppLLM(
        sidecar_status=lambda: running_status,
        sidecar_recover=lambda: recoveries.append("restart") or running_status,
        managed=True,
    )

    assert runtime.generate("hello") == "ready after restart"
    assert recoveries == ["restart"]
    assert posts == ["http://test/v1/chat/completions", "http://test/v1/chat/completions"]


def test_local_runtime_generate_envelope_sends_flat_prompt_over_chat_with_template_kwargs(monkeypatch):
    calls = []

    def fake_post(url, *, json, timeout):
        calls.append((url, json, timeout))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": "ready"}}]},
        )

    monkeypatch.setattr("backend.app.runtimes.llm.local_runtime.httpx.post", fake_post)
    runtime = LlamaCppLLM(
        base_url="http://test",
        model="assistant-qwen3-4b-q4-portable",
        timeout=7.0,
        generation_defaults={
            "max_tokens": 16,
            "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False},
        },
    )
    envelope = PromptEnvelope(
        segments=(
            PromptSegment(
                authority="application",
                content_type="instruction",
                trusted=True,
                text="Answer the latest request.",
            ),
            PromptSegment(
                authority="user",
                content_type="user_input",
                trusted=False,
                text="User: Reply ready",
            ),
        )
    )

    assert runtime.generate_envelope(envelope) == "ready"
    payload = calls[0][1]
    assert calls[0][0] == "http://test/v1/chat/completions"
    assert payload["messages"] == [
        {
            "role": "user",
            "content": (
                "[APPLICATION RULES - trusted]\n"
                "Answer the latest request.\n\n"
                "[USER REQUEST - user instruction]\n"
                "User: Reply ready\n\n"
                "Assistant:"
            ),
        }
    ]
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}


def test_local_runtime_generate_fails_on_empty_response(monkeypatch):
    monkeypatch.setattr(
        "backend.app.runtimes.llm.local_runtime.httpx.post",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": ""}}]},
        ),
    )

    with pytest.raises(RuntimeError, match="empty response"):
        LlamaCppLLM(base_url="http://test").generate("hello")


def test_local_runtime_generate_fails_on_timeout_or_connection_failure(monkeypatch):
    monkeypatch.setattr(
        "backend.app.runtimes.llm.local_runtime.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("timeout")),
    )

    with pytest.raises(RuntimeError, match="llama.cpp chat completion failed"):
        LlamaCppLLM(base_url="http://test").generate("hello")


def test_local_runtime_generate_fails_on_invalid_json_payload(monkeypatch):
    monkeypatch.setattr(
        "backend.app.runtimes.llm.local_runtime.httpx.post",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [],
        ),
    )

    with pytest.raises(RuntimeError, match="invalid JSON payload"):
        LlamaCppLLM(base_url="http://test").generate("hello")


def test_local_runtime_generate_fails_on_unsupported_endpoint_response(monkeypatch):
    def raise_unsupported():
        raise RuntimeError("HTTP 404")

    monkeypatch.setattr(
        "backend.app.runtimes.llm.local_runtime.httpx.post",
        lambda *args, **kwargs: SimpleNamespace(raise_for_status=raise_unsupported),
    )

    with pytest.raises(RuntimeError, match="HTTP 404"):
        LlamaCppLLM(base_url="http://test").generate("hello")


def test_llm_catalog_declares_lower_quant_default_and_cpu_profiles():
    entry = get_model_entry("llm")

    assert entry.name == "assistant-small-q4"
    assert entry.local_path.as_posix().endswith(
        "models/llm/assistant-small-q4/qwen2.5-0.5b-instruct-q4_k_m.gguf"
    )
    assert entry.config["quantization"] == "q4_k_m"
    assert entry.config["source"]["type"] == "huggingface"
    assert entry.config["source"]["repo_id"] == "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
    assert entry.config["source"]["file"] == "qwen2.5-0.5b-instruct-q4_k_m.gguf"
    assert "voice_chat" in entry.config["routes"]

    profiles = entry.config["serve_profiles"]["hardware_profiles"]
    assert "windows_amd64_cpu" in profiles
    assert "windows_arm64_cpu" in profiles
    assert profiles["windows_amd64_cpu"]["binary_path"].endswith(
        "runtimes/llama.cpp/windows-amd64/llama-server.exe"
    )


def test_openai_compatible_providers_use_bound_generate_envelope(monkeypatch):
    captured = {}

    class DummyOpenAI:
        def __init__(self, api_key=None):
            captured["api_key"] = api_key

        def responses_create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text="Claude style answer")

    monkeypatch.setattr("backend.app.runtimes.llm.claude_runtime.Anthropic", lambda api_key=None: DummyOpenAI(api_key))
    llm = ClaudeLLM(api_key="test-key")
    envelope = PromptEnvelope(
        segments=(
            PromptSegment(
                authority="application",
                content_type="instruction",
                trusted=True,
                text="Obey concise style.",
            ),
            PromptSegment(
                authority="user",
                content_type="user_input",
                trusted=False,
                text="Summarize the log.",
            ),
        )
    )

    assert llm.generate_envelope(envelope) == "Claude style answer"
    assert captured["api_key"] == "test-key"
    assert captured["messages"] == [
        {"role": "system", "content": "Obey concise style."},
        {"role": "user", "content": "Summarize the log."},
    ]


def test_ollama_generate_envelope_delegates_to_rendered_prompt(monkeypatch):
    seen = {}

    def fake_generate(self, prompt, **kwargs):
        seen["prompt"] = prompt
        seen["kwargs"] = kwargs
        return "ollama answer"

    monkeypatch.setattr(OllamaLLM, "generate", fake_generate)
    envelope = PromptEnvelope(
        segments=(
            PromptSegment("application", "instruction", True, "Use short answers."),
            PromptSegment("user", "user_input", False, "What is uptime?"),
        )
    )

    assert OllamaLLM().generate_envelope(envelope, temperature=0) == "ollama answer"
    assert "Use short answers." in seen["prompt"]
    assert "What is uptime?" in seen["prompt"]
    assert seen["kwargs"] == {"temperature": 0}


def test_null_runtime_generate_envelope_raises_runtime_reason():
    runtime = NullLLMRuntime("no runtime")
    with pytest.raises(RuntimeError, match="no runtime"):
        runtime.generate_envelope(PromptEnvelope((PromptSegment("user", "user_input", False, "hello"),)))
