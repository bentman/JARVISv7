from __future__ import annotations

from typing import Any

import httpx

from backend.app.core.settings import load_settings
from backend.app.runtimes.llm.base import LLMBase


DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


class OllamaLLM(LLMBase):
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        num_ctx: int | None = None,
        timeout: float = 60.0,
    ) -> None:
        settings = load_settings()
        self.base_url = (base_url or settings.ollama_base_url or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.ollama_model or "phi4-mini"
        self.num_ctx = num_ctx if num_ctx is not None else settings.ollama_num_ctx
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