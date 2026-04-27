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


def load_default_personality() -> PersonalityProfile:
    path = CONFIG_DIR / "personality" / "default.yaml"
    if not path.exists():
        return DEFAULT_PERSONALITY
    return load_personality(path)