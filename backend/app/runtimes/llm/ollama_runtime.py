from __future__ import annotations

import os
from typing import Any

import httpx

from backend.app.runtimes.llm.base import LLMBase


DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


def _env_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return int(value)


class OllamaLLM(LLMBase):
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        num_ctx: int | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL") or "phi4-mini"
        self.num_ctx = num_ctx if num_ctx is not None else _env_int("OLLAMA_NUM_CTX")
        self.timeout = timeout
        self.reason = "not probed"

    def runtime_name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=10.0)
            response.raise_for_status()
        except Exception as exc:
            self.reason = f"ollama unavailable: {exc}"
            return False
        self.reason = "ollama /api/tags reachable"
        return True

    def _payload(self, prompt: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.model, "prompt": prompt, "stream": False}
        if self.num_ctx is not None:
            payload["options"] = {"num_ctx": self.num_ctx}
        return payload

    def generate(self, prompt: str, **kwargs: object) -> str:
        payload = self._payload(prompt)
        payload.update(kwargs)
        try:
            response = httpx.post(
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