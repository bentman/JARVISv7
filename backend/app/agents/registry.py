from __future__ import annotations

from pathlib import Path

from backend.app.agents.loader import load_agent_profiles
from backend.app.agents.schema import AgentProfile

_APPROVAL_EFFECT = {
    "none": "local_read",
    "standard": "local_write",
    "strict": "privileged_execution",
}

_APPROVAL_AUTH = {
    "none": "allow",
    "standard": "requires_approval",
    "strict": "requires_approval",
}


class AgentRegistry:
    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir = config_dir
        self._profiles: list[AgentProfile] | None = None

    def profiles(self) -> list[AgentProfile]:
        if self._profiles is None:
            if self._config_dir is None:
                self._profiles = []
            else:
                self._profiles = load_agent_profiles(self._config_dir)
        return list(self._profiles)

    def get(self, profile_id: str) -> AgentProfile | None:
        for profile in self.profiles():
            if profile.profile_id == profile_id:
                return profile
        return None

    def refresh(self) -> None:
        self._profiles = None

    def to_extension_records(self) -> list[tuple[str, str, str, str]]:
        return [
            (
                p.profile_id,
                p.display_name,
                p.purpose,
                f"config/agents/{p.profile_id}.yaml",
            )
            for p in self.profiles()
        ]

    def to_capability_records(self) -> list[tuple[str, str, str, str, str, int, bool]]:
        return [
            (
                f"agent-invoke-{p.profile_id}",
                p.profile_id,
                p.display_name,
                _APPROVAL_EFFECT[p.approval_class],
                _APPROVAL_AUTH[p.approval_class],
                p.timeout_ms,
                p.cancellable,
            )
            for p in self.profiles()
        ]
