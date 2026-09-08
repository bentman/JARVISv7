from __future__ import annotations

import json
from typing import Any

import httpx
from backend.app.cognition.prompt_chat_renderer import render_chat_prompt
from backend.app.cognition.prompt_envelope import PromptEnvelope
from backend.app.runtimes.llm.base import (
    LLMBase,
    ToolCall,
    ToolCallResult,
    ToolDefinition,
)


class ProviderRequestError(RuntimeError):
    def __init__(self, message: str, *, escalation_eligible: bool) -> None:
        super().__init__(message)
        self.escalation_eligible = escalation_eligible


def _tool_arguments(raw: Any) -> dict[str, Any]:
    """Providers send arguments either as an object or as a JSON string."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ProviderRequestError(
                "provider returned an unparsable tool call", escalation_eligible=True
            ) from exc
        if isinstance(parsed, dict):
            return parsed
    raise ProviderRequestError(
        "provider returned an unparsable tool call", escalation_eligible=True
    )


def _openai_tool_payload(tools: tuple[ToolDefinition, ...]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in tools
    ]


class HTTPProviderLLM(LLMBase):
    def __init__(
        self,
        *,
        profile_id: str,
        profile_name: str,
        provider_kind: str,
        endpoint: str,
        model: str,
        context_size: int,
        timeout: float,
        api_key: str | None,
        client: httpx.Client | None = None,
    ) -> None:
        self.profile_id = profile_id
        self.profile_name = profile_name
        self.provider_kind = provider_kind
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.context_size = context_size
        self.timeout = timeout
        self.api_key = api_key
        self.client = client or httpx.Client()
        self.reason = "not probed"
        self.last_usage: dict[str, int] = {}

    def runtime_name(self) -> str:
        return self.provider_kind

    def context_window(self) -> int:
        return self.context_size

    def generate(self, prompt: str, **kwargs: object) -> str:
        from backend.app.cognition.prompt_envelope import PromptSegment

        return self.generate_envelope(
            PromptEnvelope((PromptSegment("user", "user_input", False, prompt),)),
            **kwargs,
        )

    def discover_models(self) -> list[dict[str, object]]:
        response = self._request("GET", self._models_url(), headers=self._headers())
        payload = self._json(response, "models")
        values = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(values, list):
            raise ProviderRequestError("provider models response is invalid", escalation_eligible=True)
        models: list[dict[str, object]] = []
        for item in values:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            model: dict[str, object] = {"id": item["id"]}
            if isinstance(item.get("display_name"), str):
                model["display_name"] = item["display_name"]
            if isinstance(item.get("max_input_tokens"), int):
                model["context_window"] = item["max_input_tokens"]
            meta = item.get("meta")
            if isinstance(meta, dict) and isinstance(meta.get("n_ctx_train"), int):
                model["context_window"] = meta["n_ctx_train"]
            models.append(model)
        return models

    def is_available(self) -> bool:
        try:
            self.discover_models()
        except Exception as exc:
            self.reason = self._safe_error("provider unavailable", exc)
            return False
        self.reason = "provider models endpoint reachable"
        return True

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self.client.request(method, url, timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            eligible = status == 429 or status >= 500
            label = "rate limited" if status == 429 else "authentication failed" if status in {401, 403} else f"HTTP {status}"
            raise ProviderRequestError(f"provider request failed: {label}", escalation_eligible=eligible) from exc
        except httpx.TimeoutException as exc:
            raise ProviderRequestError("provider request failed: timeout", escalation_eligible=True) from exc
        except httpx.TransportError as exc:
            raise ProviderRequestError("provider request failed: transport unavailable", escalation_eligible=True) from exc

    @staticmethod
    def _json(response: httpx.Response, label: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception as exc:
            raise ProviderRequestError(f"provider {label} response is invalid JSON", escalation_eligible=True) from exc
        if not isinstance(payload, dict):
            raise ProviderRequestError(f"provider {label} response is invalid", escalation_eligible=True)
        return payload

    @staticmethod
    def _safe_error(prefix: str, exc: Exception) -> str:
        if isinstance(exc, ProviderRequestError):
            return str(exc)
        return prefix

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _models_url(self) -> str:
        return f"{self.endpoint}/models"


class OpenAICompatibleLLM(HTTPProviderLLM):
    def generate_envelope(self, envelope: PromptEnvelope, **kwargs: object) -> str:
        prompt = render_chat_prompt(envelope)
        payload: dict[str, object] = {
            "model": self.model,
            "messages": prompt.messages,
            "stream": False,
        }
        payload.update(prompt.generation)
        payload.update(kwargs)
        response = self._request(
            "POST",
            f"{self.endpoint}/chat/completions",
            headers=self._headers(),
            json=payload,
        )
        data = self._json(response, "chat completion")
        self._capture_openai_usage(data)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderRequestError("provider returned no completion choices", escalation_eligible=True)
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else choices[0].get("text")
        if not isinstance(content, str) or not content.strip():
            refusal = message.get("refusal") if isinstance(message, dict) else None
            if refusal or choices[0].get("finish_reason") == "content_filter":
                raise ProviderRequestError("provider returned a safety refusal", escalation_eligible=False)
            raise ProviderRequestError("provider returned an empty response", escalation_eligible=True)
        return content

    def generate_structured(self, envelope: PromptEnvelope, schema: dict[str, object]) -> str:
        return self.generate_envelope(
            envelope,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "jarvis_response",
                    "strict": True,
                    "schema": schema,
                },
            },
        )

    def generate_with_tools(
        self, envelope: PromptEnvelope, tools: tuple[ToolDefinition, ...], **kwargs: object
    ) -> ToolCallResult:
        prompt = render_chat_prompt(envelope)
        payload: dict[str, object] = {
            "model": self.model,
            "messages": prompt.messages,
            "stream": False,
            "tools": _openai_tool_payload(tools),
            "tool_choice": "auto",
        }
        payload.update(prompt.generation)
        payload.update(kwargs)
        response = self._request(
            "POST", f"{self.endpoint}/chat/completions", headers=self._headers(), json=payload
        )
        data = self._json(response, "chat completion")
        self._capture_openai_usage(data)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderRequestError(
                "provider returned no completion choices", escalation_eligible=True
            )
        message = choices[0].get("message")
        message = message if isinstance(message, dict) else {}
        calls = message.get("tool_calls")
        # A tool call legitimately carries empty content, so it is read before the
        # empty-response ladder that plain generation uses.
        if isinstance(calls, list) and calls:
            function = calls[0].get("function") if isinstance(calls[0], dict) else None
            if isinstance(function, dict) and isinstance(function.get("name"), str):
                return ToolCallResult(
                    call=ToolCall(function["name"], _tool_arguments(function.get("arguments")))
                )
            raise ProviderRequestError(
                "provider returned an unparsable tool call", escalation_eligible=True
            )
        content = message.get("content") if message else choices[0].get("text")
        if not isinstance(content, str) or not content.strip():
            refusal = message.get("refusal")
            if refusal or choices[0].get("finish_reason") == "content_filter":
                raise ProviderRequestError(
                    "provider returned a safety refusal", escalation_eligible=False
                )
            raise ProviderRequestError(
                "provider returned an empty response", escalation_eligible=True
            )
        return ToolCallResult(text=content)

    def _capture_openai_usage(self, data: dict[str, Any]) -> None:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            self.last_usage = {}
            return
        self.last_usage = {
            key: int(value)
            for key, value in usage.items()
            if key in {"prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"}
            and isinstance(value, int)
        }


class OpenAIResponsesLLM(HTTPProviderLLM):
    def generate_envelope(self, envelope: PromptEnvelope, **kwargs: object) -> str:
        return self._generate(envelope, None, kwargs)

    def generate_structured(self, envelope: PromptEnvelope, schema: dict[str, object]) -> str:
        return self._generate(envelope, schema, {})

    def generate_with_tools(
        self, envelope: PromptEnvelope, tools: tuple[ToolDefinition, ...], **kwargs: object
    ) -> ToolCallResult:
        overrides: dict[str, object] = {
            "tools": [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                }
                for tool in tools
            ],
            "tool_choice": "auto",
            **kwargs,
        }
        data = self._post_response(envelope, None, overrides)
        output = data.get("output")
        if isinstance(output, list):
            for item in output:
                if isinstance(item, dict) and item.get("type") == "function_call":
                    name = item.get("name")
                    if isinstance(name, str):
                        return ToolCallResult(
                            call=ToolCall(name, _tool_arguments(item.get("arguments")))
                        )
                    raise ProviderRequestError(
                        "provider returned an unparsable tool call", escalation_eligible=True
                    )
        return ToolCallResult(text=self._response_text(data))

    def _generate(
        self,
        envelope: PromptEnvelope,
        schema: dict[str, object] | None,
        overrides: dict[str, object],
    ) -> str:
        return self._response_text(self._post_response(envelope, schema, overrides))

    def _post_response(
        self,
        envelope: PromptEnvelope,
        schema: dict[str, object] | None,
        overrides: dict[str, object],
    ) -> dict[str, Any]:
        prompt = render_chat_prompt(envelope)
        payload: dict[str, object] = {
            "model": self.model,
            "instructions": prompt.system_text,
            "input": [message for message in prompt.messages if message.get("role") != "system"],
        }
        generation = dict(prompt.generation)
        if "max_tokens" in generation:
            payload["max_output_tokens"] = generation["max_tokens"]
        for key in ("temperature", "top_p"):
            if key in generation:
                payload[key] = generation[key]
        if schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "jarvis_response",
                    "strict": True,
                    "schema": schema,
                }
            }
        payload.update(overrides)
        response = self._request(
            "POST",
            f"{self.endpoint}/responses",
            headers=self._headers(),
            json=payload,
        )
        data = self._json(response, "response")
        usage = data.get("usage")
        self.last_usage = {
            key: int(value)
            for key, value in usage.items()
            if key in {"input_tokens", "output_tokens", "total_tokens"} and isinstance(value, int)
        } if isinstance(usage, dict) else {}
        return data

    def _response_text(self, data: dict[str, Any]) -> str:
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        output = data.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict) or not isinstance(item.get("content"), list):
                    continue
                for block in item["content"]:
                    if isinstance(block, dict) and (
                        block.get("type") == "refusal" or isinstance(block.get("refusal"), str)
                    ):
                        raise ProviderRequestError("OpenAI returned a safety refusal", escalation_eligible=False)
                    if isinstance(block, dict) and isinstance(block.get("text"), str) and block["text"].strip():
                        return block["text"]
        incomplete = data.get("incomplete_details")
        if isinstance(incomplete, dict) and incomplete.get("reason") in {
            "max_output_tokens",
            "content_filter",
        }:
            raise ProviderRequestError("OpenAI response was incomplete", escalation_eligible=False)
        raise ProviderRequestError("OpenAI returned an empty response", escalation_eligible=True)


class AnthropicMessagesLLM(HTTPProviderLLM):
    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def generate_envelope(self, envelope: PromptEnvelope, **kwargs: object) -> str:
        return self._generate(envelope, None, kwargs)

    def generate_structured(self, envelope: PromptEnvelope, schema: dict[str, object]) -> str:
        return self._generate(envelope, schema, {})

    def generate_with_tools(
        self, envelope: PromptEnvelope, tools: tuple[ToolDefinition, ...], **kwargs: object
    ) -> ToolCallResult:
        overrides: dict[str, object] = {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
                for tool in tools
            ],
            "tool_choice": {"type": "auto"},
            **kwargs,
        }
        data = self._post_message(envelope, None, overrides)
        content = data.get("content")
        if isinstance(content, list):
            # A tool-only reply carries no text block, so tool_use is read before the
            # empty-response ladder below would reject it.
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name")
                    if isinstance(name, str):
                        return ToolCallResult(
                            call=ToolCall(name, _tool_arguments(block.get("input", {})))
                        )
                    raise ProviderRequestError(
                        "provider returned an unparsable tool call", escalation_eligible=True
                    )
        return ToolCallResult(text=self._message_text(data))

    def _generate(
        self,
        envelope: PromptEnvelope,
        schema: dict[str, object] | None,
        overrides: dict[str, object],
    ) -> str:
        return self._message_text(self._post_message(envelope, schema, overrides))

    def _post_message(
        self,
        envelope: PromptEnvelope,
        schema: dict[str, object] | None,
        overrides: dict[str, object],
    ) -> dict[str, Any]:
        prompt = render_chat_prompt(envelope)
        configured_max_tokens = prompt.generation.get("max_tokens", 512)
        max_tokens = configured_max_tokens if isinstance(configured_max_tokens, int) else 512
        payload: dict[str, object] = {
            "model": self.model,
            "system": prompt.system_text,
            "messages": [message for message in prompt.messages if message.get("role") != "system"],
            "max_tokens": max_tokens,
        }
        if schema is not None:
            payload["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        payload.update(overrides)
        response = self._request(
            "POST",
            f"{self.endpoint}/messages",
            headers=self._headers(),
            json=payload,
        )
        data = self._json(response, "message")
        usage = data.get("usage")
        self.last_usage = {
            key: int(value)
            for key, value in usage.items()
            if key in {"input_tokens", "output_tokens"} and isinstance(value, int)
        } if isinstance(usage, dict) else {}
        return data

    def _message_text(self, data: dict[str, Any]) -> str:
        content = data.get("content")
        if isinstance(content, list):
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "text"
                    and isinstance(block.get("text"), str)
                    and block["text"].strip()
                ):
                    return block["text"]
        stop_reason = data.get("stop_reason")
        eligible = stop_reason not in {"refusal", "max_tokens"}
        raise ProviderRequestError("Anthropic returned an empty response", escalation_eligible=eligible)
