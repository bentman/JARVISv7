from __future__ import annotations

from backend.app.personality.schema import PersonalityProfile


def apply_personality(prompt: str, profile: PersonalityProfile) -> str:
    guidance = [
        "Personality guidance:",
        f"- Maintain a {profile.tone} tone.",
        f"- Keep responses {profile.brevity}.",
        f"- Use {profile.formality} formality.",
    ]
    addendum = profile.system_prompt_addendum.strip()
    if addendum and addendum not in prompt:
        guidance.append(f"- {addendum}")
    return "\n".join([prompt, *guidance])