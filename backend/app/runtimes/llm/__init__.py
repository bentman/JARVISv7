from __future__ import annotations

from backend.app.runtimes.llm.base import LLMBase
from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM

__all__ = [
    "LLMBase",
    "LlamaCppLLM",
    "OllamaLLM",
]
