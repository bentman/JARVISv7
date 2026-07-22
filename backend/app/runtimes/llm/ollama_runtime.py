from __future__ import annotations

from typing import Any

import httpx

from backend.app.cognition.prompt_chat_renderer import render_chat_prompt
from backend.app.cognition.prompt_envelope import PromptEnvelope
from backend.app.core.settings import load_settings
from backend.app.runtimes.llm.base import LLMBase

_ORIGINAL_GET = httpx.get
_ORIGINAL_POST = httpx.post


DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
# Bounded compatibility fallback for callers without prompt-level generation policy.
DEFAULT_OLLAMA_NUM_PREDICT = 220


class OllamaLLM(LLMBase):
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        num_ctx: int | None = None,
        timeout: float = 60.0,
        enabled: bool | None = None,
    ) -> None:
        settings = load_settings()
        self.enabled = settings.use_ollama if enabled is None else enabled
        self.base_url = (base_url or settings.ollama_base_url or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.ollama_model or "phi4-mini"
        self.num_ctx = num_ctx if num_ctx is not None else settings.ollama_num_ctx
        self.timeout = timeout
        self.reason = "not probed"
        self.client = httpx.Client()

    def runtime_name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        if not self.enabled:
            self.reason = "ollama disabled by USE_OLLAMA"
            return False
        try:
            get_func = httpx.get if httpx.get is not _ORIGINAL_GET else self.client.get
            response = get_func(f"{self.base_url}/api/tags", timeout=10.0)
            response.raise_for_status()
        except Exception as exc:
            self.reason = f"ollama unavailable: {exc}"
            return False
        self.reason = "ollama /api/tags reachable"
        return True

    def _payload(self, prompt: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": _apply_no_think_compatibility(prompt, self.model),
            "stream": False,
            "think": False,
            "options": {
                "stop": ["\nUser:", "\nAssistant:", "User:", "Assistant:"],
                "num_predict": DEFAULT_OLLAMA_NUM_PREDICT,
            },
        }
        if self.num_ctx is not None:
            payload["options"]["num_ctx"] = self.num_ctx
        return payload

    def generate(self, prompt: str, **kwargs: object) -> str:
        payload = self._payload(prompt)
        max_tokens = kwargs.pop("max_tokens", None)
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens
        payload.update(kwargs)
        payload["think"] = False
        return self._post_generate(payload)

    def generate_envelope(self, envelope: PromptEnvelope, **kwargs: object) -> str:
        chat_prompt = render_chat_prompt(envelope)
        payload = self._chat_payload(chat_prompt.messages, chat_prompt.generation)
        payload.update(kwargs)
        payload["think"] = False
        return self._post_chat(payload)

    def _post_generate(self, payload: dict[str, Any]) -> str:
        try:
            post_func = httpx.post if httpx.post is not _ORIGINAL_POST else self.client.post
            response = post_func(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise RuntimeError(f"ollama generate failed: {exc}") from exc
        generated = data.get("response")
        if not isinstance(generated, str) or not generated.strip():
            raise RuntimeError("ollama generate returned an empty response")
        return generated

    def _chat_payload(self, messages: list[dict[str, str]], generation: dict[str, object]) -> dict[str, Any]:
        options: dict[str, Any] = {
            "stop": ["\nUser:", "\nAssistant:", "User:", "Assistant:"],
            "num_predict": DEFAULT_OLLAMA_NUM_PREDICT,
        }
        if self.num_ctx is not None:
            options["num_ctx"] = self.num_ctx
        _copy_option(generation, options, "temperature")
        _copy_option(generation, options, "top_p")
        _copy_option(generation, options, "top_k")
        _copy_option(generation, options, "repeat_penalty")
        _copy_option(generation, options, "stop")
        if "max_tokens" in generation:
            options["num_predict"] = generation["max_tokens"]
        return {
            "model": self.model,
            "messages": _apply_chat_no_think_compatibility(messages, self.model),
            "stream": False,
            "think": False,
            "options": options,
        }

    def _post_chat(self, payload: dict[str, Any]) -> str:
        try:
            post_func = httpx.post if httpx.post is not _ORIGINAL_POST else self.client.post
            response = post_func(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise RuntimeError(f"ollama chat failed: {exc}") from exc
        message = data.get("message")
        generated = message.get("content") if isinstance(message, dict) else None
        if not isinstance(generated, str) or not generated.strip():
            raise RuntimeError("ollama chat returned an empty response")
        return generated


def _copy_option(source: dict[str, object], target: dict[str, Any], key: str) -> None:
    value = source.get(key)
    if value is not None:
        target[key] = value


def _apply_no_think_compatibility(prompt: str, model: str) -> str:
    if "qwen3" not in model.casefold() or prompt.rstrip().endswith("/no_think"):
        return prompt
    return f"{prompt}\n/no_think"


def _apply_chat_no_think_compatibility(
    messages: list[dict[str, str]], model: str
) -> list[dict[str, str]]:
    if "qwen3" not in model.casefold():
        return messages
    compatible_messages = [message.copy() for message in messages]
    for message in reversed(compatible_messages):
        if message.get("role") == "user":
            message["content"] = _apply_no_think_compatibility(message["content"], model)
            break
    return compatible_messages
