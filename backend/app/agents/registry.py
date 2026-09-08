from __future__ import annotations

from pathlib import Path

from backend.app.agents.loader import load_agent_profile
from backend.app.agents.schema import AgentProfile

# The current runtime invokes an agent in-process through TurnEngine, so no approval class
# describes a privileged subprocess yet. ADR 0007 owns the process-isolated runtime adapter
# that would justify a privileged_execution effect class here.
_APPROVAL_EFFECT = {
    "none": "local_read",
    "standard": "local_write",
    "strict": "local_write",
}

_APPROVAL_AUTH = {
    "none": "allow",
    "standard": "requires_approval",
    "strict": "requires_approval",
}

INVOCATION_MODE = "direct"
UNSUPPORTED_MODE = (
    f"This agent profile does not declare the {INVOCATION_MODE!r} invocation mode, "
    "which is the only mode the current runtime executes."
)


class AgentRegistry:
    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir = config_dir
        self._profiles: list[AgentProfile] | None = None
        self._errors: tuple[tuple[str, str], ...] = ()
        self._signature: tuple[tuple[str, int], ...] = ()

    def _directory(self) -> Path | None:
        if self._config_dir is None:
            return None
        directory = self._config_dir / "agents"
        return directory if directory.is_dir() else None

    def _observe(self) -> tuple[tuple[str, int], ...]:
        directory = self._directory()
        if directory is None:
            return ()
        return tuple(
            sorted((path.name, path.stat().st_mtime_ns) for path in directory.glob("*.yaml"))
        )

    def profiles(self) -> list[AgentProfile]:
        # Profiles are files an operator edits, so the set is re-observed rather than cached
        # for the life of the process; a profile that fails to load is reported, not raised,
        # so one bad file cannot take the capability catalog offline.
        signature = self._observe()
        if self._profiles is not None and signature == self._signature:
            return list(self._profiles)
        directory = self._directory()
        profiles: list[AgentProfile] = []
        errors: list[tuple[str, str]] = []
        for path in sorted(directory.glob("*.yaml")) if directory else ():
            try:
                profiles.append(load_agent_profile(path))
            except Exception as exc:
                errors.append((f"agent-invoke-{path.stem}", str(exc)[:256]))
        self._profiles = sorted(profiles, key=lambda profile: profile.profile_id)
        self._errors = tuple(errors)
        self._signature = signature
        return list(self._profiles)

    def errors(self) -> tuple[tuple[str, str], ...]:
        self.profiles()
        return self._errors

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

    def to_capability_records(self) -> list[tuple[str, str, str, str, str, int, bool, str]]:
        return [
            (
                f"agent-invoke-{p.profile_id}",
                p.profile_id,
                p.display_name,
                _APPROVAL_EFFECT[p.approval_class],
                _APPROVAL_AUTH[p.approval_class],
                p.timeout_ms,
                p.cancellable,
                "" if INVOCATION_MODE in p.invocation_modes else UNSUPPORTED_MODE,
            )
            for p in self.profiles()
        ]
