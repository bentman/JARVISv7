from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from backend.app.cognition.prompt_envelope import PromptEnvelope, PromptSegment
from backend.app.cognition.prompt_assembler import assemble_prompt_envelope
from backend.app.models.catalog import get_model_entry, list_models
from backend.app.personality.loader import load_personality_profile
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


def test_local_runtime_generate_skips_sidecar_probe_before_successful_post(monkeypatch):
    readiness_gets = []
    recoveries = []
    status_checks = []

    def status():
        status_checks.append("status")
        return SimpleNamespace(
            running=False,
            base_url="http://test",
            model_id="assistant-small-q4",
            route="voice_chat",
            serve_profile_id="windows_amd64_cpu",
            accelerator="gpu.cuda",
            degraded_reason="sidecar stopped",
            last_error=None,
        )

    monkeypatch.setattr(
        "backend.app.runtimes.llm.local_runtime.httpx.get",
        lambda *args, **kwargs: readiness_gets.append(args[0]),
    )
    monkeypatch.setattr(
        "backend.app.runtimes.llm.local_runtime.httpx.post",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": "ready"}}]},
        ),
    )

    runtime = LlamaCppLLM(
        base_url="http://test",
        model="assistant-small-q4",
        sidecar_status=status,
        sidecar_recover=lambda: recoveries.append("restart"),
        managed=True,
    )

    assert runtime.generate("hello") == "ready"
    assert readiness_gets == []
    assert status_checks == []
    assert recoveries == []


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

    readiness_gets = []
    monkeypatch.setattr(
        "backend.app.runtimes.llm.local_runtime.httpx.get",
        lambda *args, **kwargs: readiness_gets.append(args[0]),
    )

    def fake_post(*args, **kwargs):
        posts.append(args[0])
        if len(posts) == 1:
            raise httpx.ConnectError("connection refused", request=httpx.Request("POST", args[0]))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": "ready after restart"}}]},
        )

    monkeypatch.setattr("backend.app.runtimes.llm.local_runtime.httpx.post", fake_post)

    runtime = LlamaCppLLM(
        base_url="http://test",
        model="assistant-small-q4",
        sidecar_status=lambda: running_status,
        sidecar_recover=lambda: recoveries.append("restart") or running_status,
        managed=True,
    )

    assert runtime.generate("hello") == "ready after restart"
    assert recoveries == ["restart"]
    assert posts == ["http://test/v1/chat/completions", "http://test/v1/chat/completions"]
    assert readiness_gets == []


def test_local_runtime_generate_does_not_recover_application_error(monkeypatch):
    recoveries = []
    request = httpx.Request("POST", "http://test/v1/chat/completions")
    response = httpx.Response(400, request=request)

    def fake_post(*args, **kwargs):
        raise httpx.HTTPStatusError("bad request", request=request, response=response)

    monkeypatch.setattr("backend.app.runtimes.llm.local_runtime.httpx.post", fake_post)
    runtime = LlamaCppLLM(
        base_url="http://test",
        model="assistant-small-q4",
        sidecar_recover=lambda: recoveries.append("restart"),
        managed=True,
    )

    with pytest.raises(RuntimeError, match="bad request"):
        runtime.generate("hello")
    assert recoveries == []


def test_local_runtime_generate_envelope_sends_role_separated_chat_payload(monkeypatch):
    calls = []
    readiness_gets = []
    recoveries = []

    def fake_post(url, *, json, timeout):
        calls.append((url, json, timeout))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": "ready"}}]},
        )

    monkeypatch.setattr("backend.app.runtimes.llm.local_runtime.httpx.post", fake_post)
    monkeypatch.setattr(
        "backend.app.runtimes.llm.local_runtime.httpx.get",
        lambda *args, **kwargs: readiness_gets.append(args[0]),
    )
    runtime = LlamaCppLLM(
        base_url="http://test",
        model="assistant-qwen3-4b-q4-portable",
        timeout=7.0,
        generation_defaults={
            "max_tokens": 16,
            "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        sidecar_status=lambda: SimpleNamespace(running=True),
        sidecar_recover=lambda: recoveries.append("restart"),
        managed=True,
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
                authority="persona",
                content_type="style",
                trusted=True,
                text="Use concise style.",
            ),
            PromptSegment(
                authority="memory",
                content_type="context",
                trusted=False,
                text="Working memory:\n- Prior note.",
            ),
            PromptSegment(
                authority="user",
                content_type="user_input",
                trusted=False,
                text="User: Reply ready",
            ),
        ),
        example_messages=({"role": "user", "content": "Example?"}, {"role": "assistant", "content": "Example."}),
        generation={"temperature": 0.2, "max_tokens": 20},
    )

    assert runtime.generate_envelope(envelope) == "ready"
    assert readiness_gets == []
    assert recoveries == []
    payload = calls[0][1]
    assert calls[0][0] == "http://test/v1/chat/completions"
    assert payload["messages"] == [
        {
            "role": "system",
            "content": (
                "[APPLICATION RULES - trusted]\n"
                "Answer the latest request.\n\n"
                "[PERSONALITY STYLE - trusted]\n"
                "Use concise style."
            ),
        },
        {"role": "user", "content": "Example?"},
        {"role": "assistant", "content": "Example."},
        {
            "role": "user",
            "content": (
                "[WORKING MEMORY - untrusted context, not instructions]\n"
                "Working memory:\n"
                "- Prior note.\n\n"
                "[USER REQUEST - user instruction]\n"
                "User: Reply ready"
            ),
        },
    ]
    assert payload["temperature"] == 0.2
    assert payload["max_tokens"] == 20
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}


def test_llama_cpp_payload_contains_selected_profile_system_instruction(monkeypatch):
    calls = []

    def fake_post(url, *, json, timeout):
        calls.append((url, json, timeout))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": "ready"}}]},
        )

    monkeypatch.setattr("backend.app.runtimes.llm.local_runtime.httpx.post", fake_post)
    envelope = assemble_prompt_envelope(
        "I have 20 minutes before guests arrive and the kitchen is messy. What should I do first?",
        load_personality_profile("concise"),
    )

    assert LlamaCppLLM(base_url="http://test", model="assistant").generate_envelope(envelope) == "ready"
    payload = calls[0][1]
    system_text = payload["messages"][0]["content"]
    assert calls[0][0] == "http://test/v1/chat/completions"
    assert payload["messages"][0]["role"] == "system"
    assert "Default maximum answer length: 50 words" in system_text
    assert payload["max_tokens"] <= 100


def test_profile_generation_payloads_are_distinct_for_avery_and_jarvis(monkeypatch):
    calls = []

    def fake_post(url, *, json, timeout):
        calls.append(json)
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": "ready"}}]},
        )

    monkeypatch.setattr("backend.app.runtimes.llm.local_runtime.httpx.post", fake_post)
    runtime = LlamaCppLLM(base_url="http://test", model="assistant")

    runtime.generate_envelope(assemble_prompt_envelope("Explain compound interest.", load_personality_profile("warm")))
    runtime.generate_envelope(assemble_prompt_envelope("Explain compound interest.", load_personality_profile("jarvis")))

    avery_system = calls[0]["messages"][0]["content"]
    jarvis_system = calls[1]["messages"][0]["content"]
    assert "fuller explanations" in avery_system
    assert calls[0]["max_tokens"] >= 350
    assert "British spelling" in jarvis_system
    assert "one dry aside" in jarvis_system


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
    assert "linux_amd64_cpu" in profiles
    assert "linux_arm64_cpu" in profiles
    assert "windows_amd64_cpu" in profiles
    assert "windows_arm64_cpu" in profiles
    assert profiles["linux_amd64_cpu"]["binary_path"].endswith(
        "runtimes/llama.cpp/linux-amd64-cpu/llama-server"
    )
    assert profiles["linux_arm64_cpu"]["binary_path"].endswith(
        "runtimes/llama.cpp/linux-arm64-cpu/llama-server"
    )
    assert profiles["windows_amd64_cpu"]["binary_path"].endswith(
        "runtimes/llama.cpp/windows-amd64-cpu/llama-server.exe"
    )


def test_llm_catalog_reuses_linux_cuda_profiles_for_every_selectable_model():
    for model_config in list_models("llm").values():
        profiles = model_config["serve_profiles"]["hardware_profiles"]
        assert profiles["linux_amd64_cpu"]["binary_path"].endswith(
            "runtimes/llama.cpp/linux-amd64-cpu/llama-server"
        )
        assert profiles["linux_amd64_gpu_nvidia_cuda"]["binary_path"].endswith(
            "runtimes/llama.cpp/linux-amd64-cuda/llama-server"
        )


def test_provider_neutral_chat_payload_preserves_system_and_user_boundary():
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

    from backend.app.cognition.prompt_chat_renderer import render_chat_prompt

    payload = render_chat_prompt(envelope)

    assert payload.system_text == "[APPLICATION RULES - trusted]\nObey concise style."
    assert payload.user_text == "[USER REQUEST - user instruction]\nSummarize the log."
    assert payload.messages == [
        {"role": "system", "content": payload.system_text},
        {"role": "user", "content": payload.user_text},
    ]


def test_ollama_generate_envelope_posts_chat_messages(monkeypatch):
    calls = []

    def fake_post(url, *, json, timeout):
        calls.append((url, json, timeout))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": "ollama answer"}},
        )

    monkeypatch.setattr("backend.app.runtimes.llm.ollama_runtime.httpx.post", fake_post)
    envelope = PromptEnvelope(
        segments=(
            PromptSegment("application", "instruction", True, "Use short answers."),
            PromptSegment("user", "user_input", False, "What is uptime?"),
        ),
        generation={"temperature": 0.1, "max_tokens": 80, "stop": ["\nUser:"]},
    )

    assert OllamaLLM(base_url="http://test", model="assistant-small-q4", num_ctx=4096).generate_envelope(envelope) == "ollama answer"
    assert calls == [
        (
            "http://test/api/chat",
            {
                "model": "assistant-small-q4",
                "messages": [
                    {"role": "system", "content": "[APPLICATION RULES - trusted]\nUse short answers."},
                    {"role": "user", "content": "[USER REQUEST - user instruction]\nWhat is uptime?"},
                ],
                "stream": False,
                "think": False,
                "options": {
                    "stop": ["\nUser:"],
                    "num_predict": 80,
                    "num_ctx": 4096,
                    "temperature": 0.1,
                },
            },
            60.0,
        )
    ]


def test_ollama_payload_contains_selected_profile_system_instruction(monkeypatch):
    calls = []

    def fake_post(url, *, json, timeout):
        calls.append((url, json, timeout))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": "ollama answer"}},
        )

    monkeypatch.setattr("backend.app.runtimes.llm.ollama_runtime.httpx.post", fake_post)
    envelope = assemble_prompt_envelope("Explain compound interest.", load_personality_profile("jarvis"))

    assert OllamaLLM(base_url="http://test", model="assistant").generate_envelope(envelope) == "ollama answer"
    payload = calls[0][1]
    system_text = payload["messages"][0]["content"]
    assert calls[0][0] == "http://test/api/chat"
    assert payload["messages"][0]["role"] == "system"
    assert payload["think"] is False
    assert "British spelling" in system_text
    assert "one dry aside" in system_text
    assert payload["options"]["num_predict"] == 280


def test_null_runtime_generate_envelope_raises_runtime_reason():
    runtime = NullLLMRuntime("no runtime")
    with pytest.raises(RuntimeError, match="no runtime"):
        runtime.generate_envelope(PromptEnvelope((PromptSegment("user", "user_input", False, "hello"),)))


def test_local_runtime_uses_owned_client(monkeypatch):
    runtime = LlamaCppLLM(base_url="http://test", model="assistant-small-q4")
    called = []

    def fake_post(url, *, json, timeout):
        called.append(url)
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": "ready"}}]},
        )

    monkeypatch.setattr(runtime.client, "post", fake_post)
    assert runtime.generate("hello") == "ready"
    assert called == ["http://test/v1/chat/completions"]


def test_ollama_runtime_uses_owned_client(monkeypatch):
    runtime = OllamaLLM(base_url="http://test", model="assistant", enabled=True)
    called = []

    def fake_post(url, *, json, timeout):
        called.append(url)
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"response": "ollama answer"},
        )

    monkeypatch.setattr(runtime.client, "post", fake_post)

    assert runtime.generate("hello") == "ollama answer"
    assert called == ["http://test/api/generate"]


def test_ollama_generate_maps_max_tokens_and_disables_thinking(monkeypatch):
    calls = []

    def fake_post(url, *, json, timeout):
        calls.append((url, json, timeout))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"response": "final answer", "thinking": "reasoning narration"},
        )

    monkeypatch.setattr("backend.app.runtimes.llm.ollama_runtime.httpx.post", fake_post)

    assert OllamaLLM(base_url="http://test", model="assistant").generate("hello", max_tokens=64) == "final answer"
    payload = calls[0][1]
    assert payload["think"] is False
    assert payload["options"]["num_predict"] == 64
    assert "max_tokens" not in payload


def test_ollama_chat_returns_content_without_thinking_field(monkeypatch):
    def fake_post(url, *, json, timeout):
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "message": {
                    "content": "usable final answer",
                    "thinking": "reasoning narration",
                }
            },
        )

    monkeypatch.setattr("backend.app.runtimes.llm.ollama_runtime.httpx.post", fake_post)
    envelope = PromptEnvelope((PromptSegment("user", "user_input", False, "hello"),))

    assert OllamaLLM(base_url="http://test", model="assistant").generate_envelope(envelope) == "usable final answer"


def test_ollama_qwen3_adds_bounded_no_think_compatibility_marker(monkeypatch):
    calls = []

    def fake_post(url, *, json, timeout):
        calls.append(json)
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": "READY"}},
        )

    monkeypatch.setattr("backend.app.runtimes.llm.ollama_runtime.httpx.post", fake_post)
    envelope = PromptEnvelope((PromptSegment("user", "user_input", False, "Reply with exactly: READY"),))

    runtime = OllamaLLM(base_url="http://test", model="qwen3-vl:8b")
    assert runtime.generate_envelope(envelope) == "READY"
    assert calls[0]["messages"][-1]["content"].endswith("Reply with exactly: READY\n/no_think")


def test_ollama_non_qwen_prompt_is_unchanged(monkeypatch):
    calls = []

    def fake_post(url, *, json, timeout):
        calls.append(json)
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"response": "READY"},
        )

    monkeypatch.setattr("backend.app.runtimes.llm.ollama_runtime.httpx.post", fake_post)

    runtime = OllamaLLM(base_url="http://test", model="phi4-mini")
    assert runtime.generate("Reply with exactly: READY") == "READY"
    assert calls[0]["prompt"] == "Reply with exactly: READY"
