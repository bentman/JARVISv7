from __future__ import annotations

from pathlib import Path
from typing import Any
from dataclasses import dataclass

import yaml

from backend.app.core.paths import CONFIG_DIR
from backend.app.personality.schema import PersonalityExample, PersonalityProfile, PersonalityStyle, PersonalityTraits


DEFAULT_PERSONALITY = PersonalityProfile(
    profile_id="default",
    display_name="Morgan",
    description="Balanced general assistant.",
    locale="en",
    system=(
        "You are Morgan, a balanced general assistant. Answer directly, include brief context when it helps, "
        "and stop before overexplaining."
    ),
    style=PersonalityStyle(
        max_words_default=120,
        structure="Answer first, then add brief context or a next step when useful.",
        do=("Start with the practical answer.", "State uncertainty plainly.", "Keep the tone calm and useful."),
        avoid=("Long digressions.", "Performative banter.", "Overexplaining simple requests."),
    ),
    traits=PersonalityTraits(warmth="medium", assertiveness="medium", detail="medium", humor="light"),
    examples=(
        PersonalityExample(
            user="I have 20 minutes before guests arrive and the kitchen is messy. What should I do first?",
            assistant=(
                "Start with what people will see first: clear counters, put dishes out of sight, wipe the main "
                "surfaces, and take out obvious trash. Leave hidden or low-impact cleaning for later."
            ),
        ),
    ),
    generation={
        "temperature": 0.6,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.08,
        "max_tokens": 180,
        "stop": ["\nUser:", "\nAssistant:"],
    },
    enabled=True,
)


@dataclass(frozen=True, slots=True)
class PersonalityProfileError:
    profile_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class PersonalityProfileList:
    profiles: list[PersonalityProfile]
    profile_errors: list[PersonalityProfileError]


def load_personality(path: Path) -> PersonalityProfile:
    with path.open("r", encoding="utf-8") as stream:
        data: Any = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise ValueError(f"personality profile must be a mapping: {path}")
    return PersonalityProfile.from_dict(data)


def _profile_path(profile_id: str) -> Path:
    normalized = profile_id.strip()
    if not normalized or normalized != profile_id or any(part in normalized for part in ("/", "\\", "..")):
        raise ValueError("invalid personality profile_id")
    return CONFIG_DIR / "personality" / f"{normalized}.yaml"


def load_personality_profile(profile_id: str) -> PersonalityProfile:
    path = _profile_path(profile_id)
    if not path.exists():
        raise FileNotFoundError(f"personality profile not found: {profile_id}")
    profile = load_personality(path)
    if profile.profile_id != profile_id:
        raise ValueError(f"personality profile id mismatch: {path}")
    return profile


def list_personality_profiles() -> list[PersonalityProfile]:
    return list_personality_profiles_with_errors().profiles


def list_personality_profiles_with_errors() -> PersonalityProfileList:
    directory = CONFIG_DIR / "personality"
    if not directory.exists():
        return PersonalityProfileList(profiles=[DEFAULT_PERSONALITY], profile_errors=[])
    profiles: list[PersonalityProfile] = []
    errors: list[PersonalityProfileError] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            profiles.append(load_personality(path))
        except Exception as exc:
            errors.append(PersonalityProfileError(profile_path=path.name, reason=str(exc)))
    return PersonalityProfileList(
        profiles=sorted(profiles, key=lambda profile: profile.profile_id),
        profile_errors=errors,
    )


def load_default_personality() -> PersonalityProfile:
    path = CONFIG_DIR / "personality" / "default.yaml"
    if not path.exists():
        return DEFAULT_PERSONALITY
    return load_personality(path)
