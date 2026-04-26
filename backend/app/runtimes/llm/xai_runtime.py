from __future__ import annotations

from backend.app.runtimes.llm.base import CloudLLMRuntime


class XaiLLM(CloudLLMRuntime):
    def __init__(self, cloud_enabled: bool = False, api_key_env: str = "XAI_API_KEY") -> None:
        super().__init__("xai", cloud_enabled=cloud_enabled, api_key_env=api_key_env)