from __future__ import annotations

from backend.app.runtimes.llm.base import LLMBase


class LlamaCppLLM(LLMBase):
    def is_available(self) -> bool:
        return False

    def generate(self, prompt: str, **kwargs: object) -> str:
        raise NotImplementedError("llama.cpp activation deferred to H.1")

    def runtime_name(self) -> str:
        return "llama.cpp"