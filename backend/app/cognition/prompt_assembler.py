from __future__ import annotations

from backend.app.personality.schema import PersonalityProfile


def assemble_prompt(
    transcript: str,
    personality: PersonalityProfile,
    working_memory: list[str] | None = None,
) -> str:
    parts: list[str] = [
        f"Assistant: {personality.display_name}",
        f"Tone: {personality.tone}",
        f"Brevity: {personality.brevity}",
    ]
    if personality.system_prompt_addendum.strip():
        parts.append(personality.system_prompt_addendum.strip())
    if working_memory:
        parts.append("Working memory:")
        parts.extend(f"- {line}" for line in working_memory)
    parts.append(f"User: {transcript}")
    return "\n".join(parts)