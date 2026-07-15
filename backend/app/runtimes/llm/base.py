from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import httpx
from backend.app.cognition.prompt_chat_renderer import render_chat_prompt
from backend.app.cognition.prompt_envelope import PromptEnvelope
from backend.app.cognition.prompt_renderer import render_flat_prompt

_ORIGINAL_POST = httpx.post


class LLMBase(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs: object) -> str:
        raise NotImplementedError

    def generate_envelope(self, envelope: PromptEnvelope, **kwargs: object) -> str:
        return self.generate(render_flat_prompt(envelope), **kwargs)

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def runtime_name(self) -> str:
        raise NotImplementedError


_CHAT_COMPLETION_GENERATION_KEYS = ("temperature", "top_p", "max_tokens", "stop")


class CloudLLMRuntime(LLMBase):
    def __init__(
        self,
        name: str,
        cloud_enabled: bool = False,
        api_key_env: str = "",
        base_url: str = "",
        model: str = "",
        timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.cloud_enabled = cloud_enabled
        self.api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.reason = "not probed"
        self.client = httpx.Client()

    def runtime_name(self) -> str:
        return self.name

    def is_available(self) -> bool:
        if not self.cloud_enabled:
            self.reason = f"{self.name} cloud LLM policy-gated"
            return False
        if not self.api_key_env or not os.getenv(self.api_key_env):
            self.reason = f"{self.name} API key env var missing: {self.api_key_env}"
            return False
        self.reason = f"{self.name} cloud runtime available (policy-enabled, key present)"
        return True

    def generate(self, prompt: str, **kwargs: object) -> str:
        return self._generate_messages([{"role": "user", "content": prompt}], dict(kwargs))

    def generate_envelope(self, envelope: PromptEnvelope, **kwargs: object) -> str:
        chat_prompt = render_chat_prompt(envelope)
        generation = dict(chat_prompt.generation)
        generation.update(kwargs)
        return self._generate_messages(chat_prompt.messages, generation)

    def _generate_messages(self, messages: list[dict[str, str]], generation: dict[str, object]) -> str:
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        for key in _CHAT_COMPLETION_GENERATION_KEYS:
            value = generation.get(key)
            if value is not None:
                payload[key] = value
        data = self._post_json(
            f"{self.base_url}/chat/completions",
            payload,
            {"Authorization": f"Bearer {self._api_key()}"},
        )
        return self._chat_completion_text(data)

    def _api_key(self) -> str:
        key = os.getenv(self.api_key_env) if self.api_key_env else None
        if not key:
            raise RuntimeError(f"{self.name} API key env var missing: {self.api_key_env}")
        return key

    def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> Any:
        try:
            post_func = httpx.post if httpx.post is not _ORIGINAL_POST else self.client.post
            response = post_func(url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise RuntimeError(f"{self.name} chat completion failed: {exc}") from exc

    def _chat_completion_text(self, data: Any) -> str:
        if not isinstance(data, dict):
            raise RuntimeError(f"{self.name} chat completion returned invalid JSON payload")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise RuntimeError(f"{self.name} chat completion returned no choices")
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(f"{self.name} chat completion returned an empty response")
        return content
