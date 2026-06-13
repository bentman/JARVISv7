from __future__ import annotations

from backend.app.runtimes.llm.base import LLMBase


class LlamaCppLLM(LLMBase):
    def is_available(self) -> bool:
        return False

    def generate(self, prompt: str, **kwargs: object) -> str:
        raise NotImplementedError(
            "llama.cpp is not wired as a verified runtime; local LLM runtime boundary owns wiring and validation"
        )

    def runtime_name(self) -> str:
        return "llama.cpp"
