from __future__ import annotations

from typing import Any

from backend.app.runtimes.llm.base import CloudLLMRuntime

DEFAULT_CLAUDE_BASE_URL = "https://api.anthropic.com/v1"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-5"
DEFAULT_CLAUDE_MAX_TOKENS = 1024
_ANTHROPIC_VERSION = "2023-06-01"


class ClaudeLLM(CloudLLMRuntime):
    def __init__(
        self,
        cloud_enabled: bool = False,
        api_key_env: str = "ANTHROPIC_API_KEY",
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(
            "claude",
            cloud_enabled=cloud_enabled,
            api_key_env=api_key_env,
            base_url=base_url or DEFAULT_CLAUDE_BASE_URL,
            model=model or DEFAULT_CLAUDE_MODEL,
            timeout=timeout,
        )

    def _generate_messages(self, messages: list[dict[str, str]], generation: dict[str, object]) -> str:
        system_parts = [message["content"] for message in messages if message.get("role") == "system"]
        chat_messages = [message for message in messages if message.get("role") != "system"]
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": generation.get("max_tokens") or DEFAULT_CLAUDE_MAX_TOKENS,
            "messages": chat_messages,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        for key in ("temperature", "top_p"):
            value = generation.get(key)
            if value is not None:
                payload[key] = value
        stop = generation.get("stop")
        if stop is not None:
            payload["stop_sequences"] = list(stop) if isinstance(stop, (list, tuple)) else [stop]
        data = self._post_json(
            f"{self.base_url}/messages",
            payload,
            {"x-api-key": self._api_key(), "anthropic-version": _ANTHROPIC_VERSION},
        )
        return self._messages_text(data)

    def _messages_text(self, data: Any) -> str:
        if not isinstance(data, dict):
            raise RuntimeError(f"{self.name} chat completion returned invalid JSON payload")
        content = data.get("content")
        if not isinstance(content, list) or not content or not isinstance(content[0], dict):
            raise RuntimeError(f"{self.name} chat completion returned no content")
        text = content[0].get("text")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(f"{self.name} chat completion returned an empty response")
        return text
