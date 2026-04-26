from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.runtimes.llm.claude_runtime import ClaudeLLM
from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.routing.runtime_selector import NullLLMRuntime


def test_local_runtime_is_available_returns_false():
    assert LlamaCppLLM().is_available() is False


def test_local_runtime_generate_raises_not_implemented():
    with pytest.raises(NotImplementedError, match="H.1"):
        LlamaCppLLM().generate("hello")


def test_ollama_runtime_is_available_true_when_reachable(monkeypatch):
    monkeypatch.setattr(
        "backend.app.runtimes.llm.ollama_runtime.httpx.get",
        lambda *args, **kwargs: SimpleNamespace(raise_for_status=lambda: None),
    )
    runtime = OllamaLLM(base_url="http://test", model="phi4-mini")

    assert runtime.is_available() is True
    assert "reachable" in runtime.reason


def test_ollama_runtime_is_available_false_when_unreachable(monkeypatch):
    def fake_get(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr("backend.app.runtimes.llm.ollama_runtime.httpx.get", fake_get)
    runtime = OllamaLLM(base_url="http://test", model="phi4-mini")

    assert runtime.is_available() is False
    assert "offline" in runtime.reason


def test_ollama_runtime_generate_posts_stream_false_and_num_ctx(monkeypatch):
    calls = []

    def fake_post(url, *, json, timeout):
        calls.append((url, json, timeout))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"response": "ready"})

    monkeypatch.setattr("backend.app.runtimes.llm.ollama_runtime.httpx.post", fake_post)
    runtime = OllamaLLM(base_url="http://test", model="phi4-mini", num_ctx=4096, timeout=7.0)

    assert runtime.generate("Reply ready") == "ready"
    assert calls == [
        (
            "http://test/api/generate",
            {
                "model": "phi4-mini",
                "prompt": "Reply ready",
                "stream": False,
                "options": {"num_ctx": 4096},
            },
            7.0,
        )
    ]


def test_ollama_runtime_generate_fails_on_empty_response(monkeypatch):
    monkeypatch.setattr(
        "backend.app.runtimes.llm.ollama_runtime.httpx.post",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"response": ""},
        ),
    )

    with pytest.raises(RuntimeError, match="empty response"):
        OllamaLLM(base_url="http://test", model="phi4-mini").generate("hello")


def test_cloud_runtime_is_available_false_when_policy_gated():
    runtime = ClaudeLLM(cloud_enabled=False)

    assert runtime.is_available() is False
    assert "policy-gated" in runtime.reason
    with pytest.raises(RuntimeError, match="policy-gated"):
        runtime.generate("hello")


def test_cloud_runtime_is_available_false_when_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runtime = ClaudeLLM(cloud_enabled=True)

    assert runtime.is_available() is False
    assert "API key" in runtime.reason


def test_null_runtime_raises_with_reason():
    runtime = NullLLMRuntime("nothing available")

    assert runtime.is_available() is False
    with pytest.raises(RuntimeError, match="nothing available"):
        runtime.generate("hello")