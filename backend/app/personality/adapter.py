from __future__ import annotations

from backend.app.personality.schema import PersonalityProfile


def apply_personality(prompt: str, profile: PersonalityProfile) -> str:
    return prompt