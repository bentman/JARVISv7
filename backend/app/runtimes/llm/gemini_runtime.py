from __future__ import annotations

from backend.app.runtimes.llm.base import CloudLLMRuntime

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


class GeminiLLM(CloudLLMRuntime):
    def __init__(
        self,
        cloud_enabled: bool = False,
        api_key_env: str = "GEMINI_API_KEY",
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(
            "gemini",
            cloud_enabled=cloud_enabled,
            api_key_env=api_key_env,
            base_url=base_url or DEFAULT_GEMINI_BASE_URL,
            model=model or DEFAULT_GEMINI_MODEL,
            timeout=timeout,
        )
