from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Authority = Literal["application", "persona", "memory", "retrieval", "tool", "user", "output"]
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

    def with_segment(self, segment: PromptSegment) -> "PromptEnvelope":
        return PromptEnvelope(segments=(*self.segments, segment))
