from __future__ import annotations

import httpx
import pytest
from backend.app.cognition.prompt_envelope import PromptEnvelope, PromptSegment
from backend.app.runtimes.llm.provider_runtime import (
    AnthropicMessagesLLM,
    OpenAICompatibleLLM,
    OpenAIResponsesLLM,
    ProviderRequestError,
)


def _envelope() -> PromptEnvelope:
    return PromptEnvelope(
        (
            PromptSegment("application", "instruction", True, "Be concise."),
            PromptSegment("user", "user_input", False, "Hello"),
        ),
        generation={"max_tokens": 42, "temperature": 0.2},
    )


def _runtime(runtime_type, handler, *, api_key="token"):
    return runtime_type(
        profile_id="profile-1",
        profile_name="Provider",
        provider_kind="provider",
        endpoint="https://provider.test/v1",
        model="model-1",
        context_size=8192,
        timeout=12,
        api_key=api_key,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_openai_compatible_contract_and_structured_output():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "model-1", "meta": {"n_ctx_train": 32768}}]})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ready":true}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            },
        )

    runtime = _runtime(OpenAICompatibleLLM, handler)
    assert runtime.discover_models() == [{"id": "model-1", "context_window": 32768}]
    assert runtime.generate_structured(_envelope(), {"type": "object"}) == '{"ready":true}'
    payload = __import__("json").loads(requests[-1].content)
    assert requests[-1].url.path == "/v1/chat/completions"
    assert requests[-1].headers["authorization"] == "Bearer token"
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "jarvis_response", "strict": True, "schema": {"type": "object"}},
    }
    assert runtime.last_usage["total_tokens"] == 13


def test_openai_responses_contract():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"output_text": "ready", "usage": {"input_tokens": 12, "output_tokens": 2, "total_tokens": 14}},
        )

    runtime = _runtime(OpenAIResponsesLLM, handler)
    assert runtime.generate_structured(_envelope(), {"type": "object"}) == "ready"
    payload = __import__("json").loads(captured[0].content)
    assert captured[0].url.path == "/v1/responses"
    assert "Be concise." in payload["instructions"]
    assert payload["max_output_tokens"] == 42
    assert payload["text"]["format"]["strict"] is True


def test_anthropic_messages_contract():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ready"}], "usage": {"input_tokens": 8}})

    runtime = _runtime(AnthropicMessagesLLM, handler)
    assert runtime.generate_structured(_envelope(), {"type": "object"}) == "ready"
    payload = __import__("json").loads(captured[0].content)
    assert captured[0].url.path == "/v1/messages"
    assert captured[0].headers["x-api-key"] == "token"
    assert captured[0].headers["anthropic-version"] == "2023-06-01"
    assert "Be concise." in payload["system"]
    assert payload["output_config"]["format"]["schema"] == {"type": "object"}


@pytest.mark.parametrize(
    ("status", "eligible", "message"),
    [(401, False, "authentication"), (400, False, "HTTP 400"), (429, True, "rate limited"), (503, True, "HTTP 503")],
)
def test_provider_status_failure_classification(status, eligible, message):
    runtime = _runtime(OpenAIResponsesLLM, lambda request: httpx.Response(status, json={"error": "failure"}))

    with pytest.raises(ProviderRequestError, match=message) as raised:
        runtime.generate_envelope(_envelope())
    assert raised.value.escalation_eligible is eligible


def test_provider_invalid_and_empty_responses_are_eligible_failures():
    runtime = _runtime(OpenAICompatibleLLM, lambda request: httpx.Response(200, content=b"not-json"))
    with pytest.raises(ProviderRequestError, match="invalid JSON") as raised:
        runtime.generate_envelope(_envelope())
    assert raised.value.escalation_eligible is True


def test_provider_timeout_is_eligible_but_safety_refusal_is_not():
    timeout_runtime = _runtime(
        OpenAIResponsesLLM,
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=request)),
    )
    with pytest.raises(ProviderRequestError, match="timeout") as timeout:
        timeout_runtime.generate_envelope(_envelope())
    assert timeout.value.escalation_eligible is True

    refusal_runtime = _runtime(
        OpenAIResponsesLLM,
        lambda request: httpx.Response(
            200,
            json={"output": [{"content": [{"type": "refusal", "refusal": "cannot comply"}]}]},
        ),
    )
    with pytest.raises(ProviderRequestError, match="safety refusal") as refusal:
        refusal_runtime.generate_envelope(_envelope())
    assert refusal.value.escalation_eligible is False
