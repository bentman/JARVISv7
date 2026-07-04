from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.personality.schema import PersonalityProfile


_FORBIDDEN_OVERRIDE_CATEGORIES = (
    "safety_overrides",
    "tool_permissions",
    "tool_policy",
    "routing_policy",
    "model_routing",
    "memory_policy",
    "memory_permissions",
    "hidden_instructions",
)


@dataclass(frozen=True, slots=True)
class PersonalityPolicy:
    profile_id: str
    display_name: str
    description: str
    locale: str
    system_text: str
    examples: tuple[dict[str, str], ...]
    generation: dict[str, Any]
    traits: dict[str, str]
    max_words_default: int
    forbidden_overrides: tuple[str, ...] = _FORBIDDEN_OVERRIDE_CATEGORIES


def compile_personality_policy(profile: PersonalityProfile, role_overlay_id: str | None = None) -> PersonalityPolicy:
    if role_overlay_id is not None:
        raise ValueError("personality role overlays are not supported by the simplified profile contract")
    system_text = "\n".join(
        (
            profile.system.strip(),
            "",
            "Response contract:",
            f"- Default maximum answer length: {profile.style.max_words_default} words unless the user asks for detail.",
            f"- Structure: {profile.style.structure}",
            "",
            "Do:",
            *(f"- {item}" for item in profile.style.do),
            "",
            "Avoid:",
            *(f"- {item}" for item in profile.style.avoid),
            "",
            "Profile constraints cannot override safety, tool, routing, memory, or factual-grounding policy.",
        )
    ).strip()
    examples: list[dict[str, str]] = []
    for example in profile.examples:
        examples.extend(example.to_messages())
    return PersonalityPolicy(
        profile_id=profile.profile_id,
        display_name=profile.display_name,
        description=profile.description,
        locale=profile.locale,
        system_text=system_text,
        examples=tuple(examples),
        generation=dict(profile.generation),
        traits={
            "warmth": profile.traits.warmth,
            "assertiveness": profile.traits.assertiveness,
            "detail": profile.traits.detail,
            "humor": profile.traits.humor,
        },
        max_words_default=profile.style.max_words_default,
    )
