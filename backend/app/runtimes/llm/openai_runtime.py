from __future__ import annotations

from backend.app.runtimes.llm.base import CloudLLMRuntime

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class OpenAILLM(CloudLLMRuntime):
    def __init__(
        self,
        cloud_enabled: bool = False,
        api_key_env: str = "OPENAI_API_KEY",
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(
            "openai",
            cloud_enabled=cloud_enabled,
            api_key_env=api_key_env,
            base_url=base_url or DEFAULT_OPENAI_BASE_URL,
            model=model or DEFAULT_OPENAI_MODEL,
            timeout=timeout,
        )
