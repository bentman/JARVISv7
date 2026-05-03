from __future__ import annotations

from typing import TYPE_CHECKING

from backend.app.personality.schema import PersonalityProfile

if TYPE_CHECKING:
    from backend.app.memory.retrieval import RetrievedFact


def assemble_prompt(
    transcript: str,
    personality: PersonalityProfile,
    working_memory: list[str] | None = None,
    *,
    retrieved_context: list[RetrievedFact] | None = None,
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
    if retrieved_context:
        parts.append("Relevant prior context:")
        parts.extend(f"- [{fact.session_id[:8]}/{fact.turn_id[:8]}] {fact.content}" for fact in retrieved_context)
    parts.append(f"User: {transcript}")
    return "\n".join(parts)