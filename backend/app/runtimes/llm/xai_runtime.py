from __future__ import annotations

from backend.app.runtimes.llm.base import CloudLLMRuntime

DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_XAI_MODEL = "grok-3-mini"


class XaiLLM(CloudLLMRuntime):
    def __init__(
        self,
        cloud_enabled: bool = False,
        api_key_env: str = "XAI_API_KEY",
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(
            "xai",
            cloud_enabled=cloud_enabled,
            api_key_env=api_key_env,
            base_url=base_url or DEFAULT_XAI_BASE_URL,
            model=model or DEFAULT_XAI_MODEL,
            timeout=timeout,
        )
