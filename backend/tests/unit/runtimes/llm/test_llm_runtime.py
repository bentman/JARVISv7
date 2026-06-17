from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.models.catalog import get_model_entry
from backend.app.runtimes.llm.claude_runtime import ClaudeLLM
from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.routing.runtime_selector import NullLLMRuntime


def test_local_runtime_is_available_returns_false():
    runtime = LlamaCppLLM()

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
            },
            7.0,
        )
    ]


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

    profiles = entry.config["serve_profiles"]
    assert profiles["windows_amd64_cpu"]["accelerator"] == "cpu"
    assert profiles["windows_amd64_cpu"]["base_url"] == "http://127.0.0.1:8080"
    assert profiles["windows_amd64_cpu"]["launch"]["gpu_layers"] == 0
    assert profiles["windows_arm64_cpu"]["accelerator"] == "cpu"
    assert profiles["windows_arm64_cpu"]["launch"]["gpu_layers"] == 0


def test_llm_catalog_accelerator_profiles_are_declared_without_validation_claims():
    entry = get_model_entry("llm")
    profiles = entry.config["serve_profiles"]

    assert profiles["windows_amd64_cuda"]["accelerator"] == "gpu.cuda"
    assert profiles["windows_amd64_cuda"]["validation_status"] == "declared-not-validated"
    assert profiles["windows_arm64_qnn"]["accelerator"] == "npu.qnn"
    assert profiles["windows_arm64_qnn"]["validation_status"] == "declared-degraded"
    assert profiles["windows_arm64_qnn"]["close_if_unavailable"] == "SKIP-no-viable-binary"


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
                "options": {
                    "stop": ["\nUser:", "\nAssistant:", "User:", "Assistant:"],
                    "num_predict": 220,
                    "num_ctx": 4096,
                },
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
