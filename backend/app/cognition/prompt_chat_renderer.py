from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.cognition.prompt_envelope import PromptEnvelope, PromptSegment
from backend.app.cognition.prompt_renderer import _header_for


@dataclass(frozen=True, slots=True)
class ChatPromptPayload:
    system_text: str
    user_text: str
    messages: list[dict[str, str]]
    generation: dict[str, object] = field(default_factory=dict)


_SYSTEM_AUTHORITIES = {"application", "persona", "output"}


def render_chat_prompt(envelope: PromptEnvelope) -> ChatPromptPayload:
    system_parts: list[str] = []
    user_parts: list[str] = []
    for segment in envelope.segments:
        rendered = _render_segment(segment)
        if segment.trusted and segment.authority in _SYSTEM_AUTHORITIES:
            system_parts.append(rendered)
        else:
            user_parts.append(rendered)

    system_text = "\n\n".join(system_parts).strip()
    user_text = "\n\n".join(user_parts).strip()
    messages: list[dict[str, str]] = []
    if system_text:
        messages.append({"role": "system", "content": system_text})
    messages.extend(dict(message) for message in envelope.example_messages)
    if user_text:
        messages.append({"role": "user", "content": user_text})
    return ChatPromptPayload(
        system_text=system_text,
        user_text=user_text,
        messages=messages,
        generation=dict(envelope.generation),
    )


def _render_segment(segment: PromptSegment) -> str:
    return f"{_header_for(segment)}\n{segment.text.strip()}"
