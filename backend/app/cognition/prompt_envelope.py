from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Authority = Literal["application", "persona", "session", "memory", "retrieval", "tool", "user", "output"]
ContentType = Literal["instruction", "style", "context", "tool_result", "user_input", "contract"]


@dataclass(frozen=True, slots=True)
class PromptSegment:
    authority: Authority
    content_type: ContentType
    trusted: bool
    text: str


@dataclass(frozen=True, slots=True)
class PromptEnvelope:
    segments: tuple[PromptSegment, ...]
    example_messages: tuple[dict[str, str], ...] = field(default_factory=tuple)
    generation: dict[str, object] = field(default_factory=dict)

    def with_segment(self, segment: PromptSegment) -> "PromptEnvelope":
        return PromptEnvelope(
            segments=(*self.segments, segment),
            example_messages=self.example_messages,
            generation=dict(self.generation),
        )
