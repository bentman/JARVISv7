from __future__ import annotations

from pathlib import Path
from typing import Any
from dataclasses import dataclass

import yaml

from backend.app.core.paths import CONFIG_DIR
from backend.app.personality.schema import PersonalityProfile


DEFAULT_PERSONALITY = PersonalityProfile(
    profile_id="default",
    display_name="JARVIS",
    tone="professional",
    brevity="concise",
    formality="semi-formal",
    system_prompt_addendum="",
    response_language="",
    identity_summary="A local-first personal assistant with a professional JARVIS identity.",
    warmth="moderate",
    assertiveness="moderate",
    humor_policy="none",
    response_style="direct_answer",
    acknowledgment_style="minimal",
    confirmation_style="explicit_when_needed",
    interruption_style="stop_cleanly",
    voice_pacing="normal",
    voice_energy="neutral",
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
