from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.personality import schema as schema_module
from backend.app.personality.schema import PersonalityProfile

_FORBIDDEN_OVERRIDE_CATEGORIES = tuple(sorted(schema_module._PROHIBITED_FIELDS))

_TRAIT_INSTRUCTIONS: dict[str, dict[str, str]] = {
    "warmth": {
        "none": "Use direct helpfulness with no extra warmth.",
        "low": "Keep warmth minimal and practical.",
        "medium": "Use a calm, friendly tone without extra reassurance.",
        "high": "Use clearly warm and supportive phrasing without overstating certainty.",
        "strong": "Use strongly warm and encouraging phrasing while staying truthful.",
    },
    "assertiveness": {
        "none": "Avoid recommendations unless the user asks for one.",
        "low": "Offer suggestions gently and avoid sounding commanding.",
        "medium": "Give clear recommendations while allowing uncertainty.",
        "high": "State the recommended path plainly when evidence supports it.",
        "strong": "Be decisive and action-oriented when the answer is clear.",
    },
    "detail": {
        "none": "Keep detail to the minimum needed for the answer.",
        "low": "Keep details sparse and action-focused.",
        "medium": "Include enough detail to explain the answer.",
        "high": "Add useful context and tradeoffs when they help.",
        "strong": "Provide fuller context, tradeoffs, and reasoning when useful.",
    },
    "humor": {
        "none": "Use no humor.",
        "light": "Use light humor rarely and only when natural.",
        "medium": "Use occasional light humor for low-risk, everyday topics; omit when the user needs serious guidance.",
        "high": "Use humor more readily in low-risk, everyday contexts; skip it when the user needs analysis, troubleshooting, or reliability details.",
        "dry": "Use at most one dry aside or slightly snarky observation when it sharpens or softens the answer; never force jokes or theatrics.",
    },
}


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
            *_trait_instruction_lines(profile),
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


def _trait_instruction_lines(profile: PersonalityProfile) -> tuple[str, ...]:
    return (
        "Behavior traits:",
        f"- Warmth guidance: {_TRAIT_INSTRUCTIONS['warmth'][profile.traits.warmth]}",
        f"- Assertiveness guidance: {_TRAIT_INSTRUCTIONS['assertiveness'][profile.traits.assertiveness]}",
        f"- Detail guidance: {_TRAIT_INSTRUCTIONS['detail'][profile.traits.detail]}",
        f"- Humor guidance: {_TRAIT_INSTRUCTIONS['humor'][profile.traits.humor]}",
    )
