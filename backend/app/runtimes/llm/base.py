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

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def runtime_name(self) -> str:
        raise NotImplementedError
