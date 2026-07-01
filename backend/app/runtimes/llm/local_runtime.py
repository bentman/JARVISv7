from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from backend.app.core.settings import load_settings
from backend.app.runtimes.llm.base import LLMBase
from backend.app.services.local_llm_sidecar import LocalLLMSidecarStatus


DEFAULT_LLAMA_CPP_BASE_URL = "http://127.0.0.1:8080"
_OPENAI_MODELS_PATH = "/v1/models"
_OPENAI_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
_HEALTH_PATHS = ("/health", "/healthz")


class LlamaCppLLM(LLMBase):
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        generation_defaults: dict[str, Any] | None = None,
        timeout: float | None = None,
        sidecar_status: Callable[[], LocalLLMSidecarStatus] | None = None,
        managed: bool | None = None,
        route: str | None = None,
        serve_profile_id: str | None = None,
        accelerator: str | None = None,
        selected_reason: str | None = None,
        model_mode: str | None = None,
        model_policy: str | None = None,
        model_role: str | None = None,
        model_selection_reason: str | None = None,
    ) -> None:
        settings = load_settings()
        self._explicit_base_url = base_url is not None
        self.base_url = (base_url or settings.llama_cpp_base_url or DEFAULT_LLAMA_CPP_BASE_URL).rstrip("/")
        self.model = model or settings.llama_cpp_model_name or "local-llama-cpp"
        self.generation_defaults = generation_defaults or {}
        self.timeout = timeout if timeout is not None else settings.llama_cpp_timeout_seconds
        self.sidecar_status = sidecar_status
        self.managed = settings.llama_cpp_managed if managed is None else managed
        self.route = route
        self.serve_profile_id = serve_profile_id
        self.accelerator = accelerator
        self.selected_reason = selected_reason
        self.model_mode = model_mode
        self.model_policy = model_policy
        self.model_role = model_role
        self.model_selection_reason = model_selection_reason
        self.reason = "not probed"

    def is_available(self) -> bool:
        if not self._sidecar_ready():
            return False

        models_reason = self._probe_models_endpoint()
        if models_reason is None:
            self.reason = "llama.cpp /v1/models reachable"
            return True

        health_reason = self._probe_health_endpoint()
        if health_reason is None:
            self.reason = "llama.cpp health endpoint reachable"
            return True

        self.reason = f"llama.cpp unavailable: {models_reason}; {health_reason}"
        return False

    def generate(self, prompt: str, **kwargs: object) -> str:
        payload = self._chat_payload(prompt)
        payload.update(kwargs)
        try:
            response = httpx.post(
                f"{self.base_url}{_OPENAI_CHAT_COMPLETIONS_PATH}",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise RuntimeError(f"llama.cpp chat completion failed: {exc}") from exc

        generated = _chat_completion_text(data)
        if not generated.strip():
            raise RuntimeError("llama.cpp chat completion returned an empty response")
        return generated

    def runtime_name(self) -> str:
        return "llama.cpp"

    def _sidecar_ready(self) -> bool:
        if self.sidecar_status is not None:
            status = self.sidecar_status()
            if not status.running:
                self.reason = status.degraded_reason or status.last_error or "managed llama.cpp sidecar is not running"
                return False
            if status.base_url:
                self.base_url = status.base_url.rstrip("/")
            if status.model_id:
                self.model = status.model_id
            if status.route:
                self.route = status.route
            if status.serve_profile_id:
                self.serve_profile_id = status.serve_profile_id
            if status.accelerator:
                self.accelerator = status.accelerator
            return True

        if self._explicit_base_url or self.managed:
            return True
        self.reason = "managed llama.cpp sidecar is disabled"
        return False

    def _probe_models_endpoint(self) -> str | None:
        try:
            response = httpx.get(f"{self.base_url}{_OPENAI_MODELS_PATH}", timeout=10.0)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            return f"/v1/models unavailable: {exc}"
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            return "/v1/models returned invalid payload"
        return None

    def _probe_health_endpoint(self) -> str | None:
        last_reason = "health endpoint unavailable"
        for path in _HEALTH_PATHS:
            try:
                response = httpx.get(f"{self.base_url}{path}", timeout=10.0)
                response.raise_for_status()
            except Exception as exc:
                last_reason = f"{path} unavailable: {exc}"
                continue
            return None
        return last_reason

    def _chat_payload(self, prompt: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        defaults = dict(self.generation_defaults)
        _copy_default(defaults, payload, "temperature")
        _copy_default(defaults, payload, "top_p")
        _copy_default(defaults, payload, "top_k")
        _copy_default(defaults, payload, "repeat_penalty")
        _copy_default(defaults, payload, "max_tokens")
        _copy_default(defaults, payload, "stop")
        return payload


def _copy_default(source: dict[str, Any], target: dict[str, Any], key: str) -> None:
    value = source.get(key)
    if value is not None:
        target[key] = value


def _chat_completion_text(data: Any) -> str:
    if not isinstance(data, dict):
        raise RuntimeError("llama.cpp chat completion returned invalid JSON payload")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("llama.cpp chat completion returned no choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise RuntimeError("llama.cpp chat completion returned invalid choice")
    message = first_choice.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    text = first_choice.get("text")
    if isinstance(text, str):
        return text
    raise RuntimeError("llama.cpp chat completion returned no text")
