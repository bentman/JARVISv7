from __future__ import annotations

from pathlib import Path
from typing import Any

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
)


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
    directory = CONFIG_DIR / "personality"
    if not directory.exists():
        return [DEFAULT_PERSONALITY]
    profiles = [load_personality(path) for path in sorted(directory.glob("*.yaml"))]
    return sorted(profiles, key=lambda profile: profile.profile_id)


def load_default_personality() -> PersonalityProfile:
    path = CONFIG_DIR / "personality" / "default.yaml"
    if not path.exists():
        return DEFAULT_PERSONALITY
    return load_personality(path)