from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend.app.agents.schema import AUTHORITY_FIELDS, AgentProfile


def load_agent_profile(path: Path) -> AgentProfile:
    with path.open("r", encoding="utf-8") as stream:
        data: Any = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise ValueError(f"agent profile must be a mapping: {path}")
    return AgentProfile.from_dict(data)


def load_agent_profiles(config_dir: Path) -> list[AgentProfile]:
    directory = config_dir / "agents"
    if not directory.exists():
        return []
    profiles: list[AgentProfile] = []
    for path in sorted(directory.glob("*.yaml")):
        profile = load_agent_profile(path)
        profiles.append(profile)
    return sorted(profiles, key=lambda p: p.profile_id)
