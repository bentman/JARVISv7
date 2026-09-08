from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from backend.app.cognition.prompt_envelope import PromptEnvelope
from backend.app.cognition.prompt_renderer import render_flat_prompt


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """One capability offered to the model for selection."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    """Either the model answered, or it selected one tool. Never both, never invented."""

    text: str = ""
    call: ToolCall | None = None


class ToolCallingUnavailableError(RuntimeError):
    """A runtime has no tool-calling protocol.

    This is a capability fact, not a provider failure, so it must not be recorded as
    provider failure pressure with an invented escalation eligibility.
    """

    def __init__(self, runtime_name: str) -> None:
        super().__init__(f"native tool calling is unavailable on {runtime_name}")


class LLMBase(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs: object) -> str:
        raise NotImplementedError

    def generate_envelope(self, envelope: PromptEnvelope, **kwargs: object) -> str:
        return self.generate(render_flat_prompt(envelope), **kwargs)

    def generate_structured(self, envelope: PromptEnvelope, schema: dict[str, object]) -> str:
        raise RuntimeError("schema-constrained generation is unavailable")

    def generate_with_tools(
        self, envelope: PromptEnvelope, tools: tuple[ToolDefinition, ...], **kwargs: object
    ) -> ToolCallResult:
        raise ToolCallingUnavailableError(self.runtime_name())

    def supports_tool_calling(self) -> bool:
        # Support is derived from the implementation rather than declared, so a runtime
        # cannot claim a protocol it does not implement.
        return type(self).generate_with_tools is not LLMBase.generate_with_tools

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
