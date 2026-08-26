from __future__ import annotations

from abc import ABC, abstractmethod

from backend.app.cognition.prompt_envelope import PromptEnvelope
from backend.app.cognition.prompt_renderer import render_flat_prompt


class LLMBase(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs: object) -> str:
        raise NotImplementedError

    def generate_envelope(self, envelope: PromptEnvelope, **kwargs: object) -> str:
        return self.generate(render_flat_prompt(envelope), **kwargs)

    def generate_structured(self, envelope: PromptEnvelope, schema: dict[str, object]) -> str:
        raise RuntimeError("schema-constrained generation is unavailable")

    def context_window(self) -> int:
        return 2048

    def prompt_token_bound(self, envelope: PromptEnvelope) -> int:
        # Byte-fallback tokenizers need no more than one token per UTF-8 byte;
        # reserve additional space for each message's chat-template tokens.
        text = render_flat_prompt(envelope)
        text += "".join(message.get("content", "") for message in envelope.example_messages)
        return len(text.encode("utf-8")) + 64 * (len(envelope.example_messages) + 2)

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def runtime_name(self) -> str:
        raise NotImplementedError
