from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

import yaml
from backend.app.agents.loader import load_agent_profile
from backend.app.agents.schema import AgentProfile
from backend.app.artifacts.storage import write_text_atomic

# An internal agent runs in-process through TurnEngine, so its approval class decides the
# effect. An ACP-runtime agent runs an external agent process, which is privileged execution
# whatever the profile's approval class says.
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

# An ACP-runtime agent runs through run_extension, which admits its own turn, so it cannot
# run inside a turn that already holds the turn lock.
EXECUTABLE_MODES = {
    "internal": ("direct", "as_tool", "router_selected", "handoff"),
    "acp": ("direct",),
}
UNSUPPORTED_MODE = (
    "This agent profile declares no invocation mode its runtime executes; "
    "an agent that runs in an external ACP agent must declare 'direct'."
)
DISABLED = "Agent is disabled."
_INACTIVE_STATES = {"disabled", "retired"}

_SOURCES = (("config", "application"), ("data", "operator"))


class AgentProfileError(ValueError):
    def __init__(self, status_code: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error


def profile_fingerprint(profile: AgentProfile) -> str:
    # Parsed content, not raw YAML, so reformatting alone never reads as a conflicting edit.
    encoded = json.dumps(profile.to_dict(), sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class AgentRegistry:
    def __init__(
        self,
        config_dir: Path | None = None,
        data_dir: Path | None = None,
        overlay: Any = None,
    ) -> None:
        self._config_dir = config_dir
        self._data_dir = data_dir
        self._overlay = overlay
        self._lock = threading.RLock()
        self._profiles: list[AgentProfile] | None = None
        self._sources: dict[str, tuple[str, str]] = {}
        self._errors: tuple[tuple[str, str], ...] = ()
        self._signature: tuple[tuple[str, str, int], ...] = ()

    def _roots(self) -> list[tuple[str, str, Path]]:
        roots = []
        for (prefix, trust), base in zip(_SOURCES, (self._config_dir, self._data_dir), strict=True):
            if base is not None:
                roots.append((prefix, trust, base / "agents"))
        return roots

    def _observe(self) -> tuple[tuple[str, str, int], ...]:
        return tuple(
            sorted(
                (prefix, path.name, path.stat().st_mtime_ns)
                for prefix, _trust, directory in self._roots()
                if directory.is_dir()
                for path in directory.glob("*.yaml")
            )
        )

    def profiles(self) -> list[AgentProfile]:
        # Profiles are files an operator edits, so the set is re-observed rather than cached
        # for the life of the process; a profile that fails to load is reported, not raised,
        # so one bad file cannot take the capability catalog offline.
        with self._lock:
            signature = self._observe()
            if self._profiles is not None and signature == self._signature:
                return list(self._profiles)
            profiles: dict[str, AgentProfile] = {}
            sources: dict[str, tuple[str, str]] = {}
            errors: list[tuple[str, str]] = []
            for prefix, trust, directory in self._roots():
                if not directory.is_dir():
                    continue
                for path in sorted(directory.glob("*.yaml")):
                    capability_id = f"agent-invoke-{path.stem}"
                    try:
                        profile = load_agent_profile(path)
                    except Exception as exc:
                        errors.append((capability_id, str(exc)[:256]))
                        continue
                    if profile.profile_id in profiles:
                        errors.append(
                            (capability_id, "an application agent profile owns this id")
                        )
                        continue
                    profiles[profile.profile_id] = profile
                    sources[profile.profile_id] = (trust, f"{prefix}/agents/{path.name}")
            self._profiles = sorted(profiles.values(), key=lambda profile: profile.profile_id)
            self._sources = sources
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

    def source(self, profile_id: str) -> tuple[str, str]:
        """Trust and repo-relative source of a loaded profile."""
        self.profiles()
        return self._sources.get(profile_id, ("application", f"config/agents/{profile_id}.yaml"))

    def enabled(self, profile_id: str) -> bool:
        overlay = self._overlay.read(f"agent:{profile_id}") if self._overlay else None
        return overlay is None or overlay.state not in _INACTIVE_STATES

    def refresh(self) -> None:
        with self._lock:
            self._profiles = None

    def unavailable_reason(self, profile: AgentProfile) -> str:
        if not self.enabled(profile.profile_id):
            return DISABLED
        if not any(
            mode in profile.invocation_modes for mode in EXECUTABLE_MODES[profile.runtime_kind]
        ):
            return UNSUPPORTED_MODE
        if profile.runtime_kind == "acp":
            return self._acp_adapter(profile.runtime["adapter_id"])[0]
        return ""

    def _acp_adapter(self, adapter_id: str) -> tuple[str, dict[str, Any]]:
        """Why the referenced ACP definition cannot run, and its declared process boundary."""
        from backend.app.extensions.discovery import discover_definition_manifests

        if self._config_dir is None:
            return f"ACP definition '{adapter_id}' is not available.", {}
        definitions = discover_definition_manifests(
            "acp", config_root=self._config_dir, data_root=self._data_dir or self._config_dir
        )
        manifest = next(
            (item for item in definitions.manifests if item.local_id == adapter_id), None
        )
        if manifest is None:
            return f"ACP definition '{adapter_id}' is not defined.", {}
        process = manifest.definition.get("process")
        process = process if isinstance(process, dict) else {}
        overlay = self._overlay.read(f"acp:{adapter_id}") if self._overlay else None
        if not manifest.declared_enabled or (overlay and overlay.state in _INACTIVE_STATES):
            return f"ACP definition '{adapter_id}' is disabled.", process
        return "", process

    def to_extension_records(self) -> list[tuple[str, str, str, str, str]]:
        return [
            (p.profile_id, p.display_name, p.purpose, *reversed(self.source(p.profile_id)))
            for p in self.profiles()
        ]

    def to_capability_records(
        self,
    ) -> list[tuple[str, str, str, str, str, int, bool, str, str, dict[str, Any]]]:
        records = []
        for p in self.profiles():
            reason = self.unavailable_reason(p)
            process = self._acp_adapter(p.runtime["adapter_id"])[1] if p.runtime_kind == "acp" else {}
            # Without a resolvable ACP definition there is no process boundary to declare, so
            # the agent is described by its approval class and served as misconfigured.
            privileged = bool(process)
            records.append(
                (
                    f"agent-invoke-{p.profile_id}",
                    p.profile_id,
                    p.display_name,
                    "privileged_execution" if privileged else _APPROVAL_EFFECT[p.approval_class],
                    "requires_approval" if privileged else _APPROVAL_AUTH[p.approval_class],
                    p.timeout_ms,
                    p.cancellable,
                    reason,
                    "disabled" if reason == DISABLED else "misconfigured" if reason else "available",
                    process,
                )
            )
        return records

    def _operator_path(self, profile_id: str) -> Path:
        if self._data_dir is None:
            raise AgentProfileError(503, "unavailable", "operator agent storage is unavailable")
        return self._data_dir / "agents" / f"{profile_id}.yaml"

    def _require_operator_owned(self, profile_id: str) -> None:
        if self._config_dir is not None and (
            self._config_dir / "agents" / f"{profile_id}.yaml"
        ).is_file():
            raise AgentProfileError(
                409, "conflict", "an application agent profile owns this id"
            )

    def _stored(self, path: Path) -> AgentProfile | None:
        return load_agent_profile(path) if path.is_file() else None

    def write_profile(
        self, data: dict[str, Any], *, expected_fingerprint: str | None = None
    ) -> dict[str, Any]:
        """Create or replace an operator-owned profile.

        Omitting `expected_fingerprint` is a create and is refused if the id already exists;
        supplying it is an edit and is refused if the stored profile no longer matches.
        """
        try:
            profile = AgentProfile.from_dict(data)
        except (TypeError, ValueError) as exc:
            raise AgentProfileError(422, "invalid", str(exc)) from exc
        self._require_operator_owned(profile.profile_id)
        path = self._operator_path(profile.profile_id)
        with self._lock:
            self._check_expected(path, expected_fingerprint, creating=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            document = json.loads(json.dumps(profile.to_dict()))
            write_text_atomic(path, yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
            self.refresh()
        return {
            "profile_id": profile.profile_id,
            "source": f"data/agents/{path.name}",
            "fingerprint": profile_fingerprint(profile),
        }

    def delete_profile(
        self, profile_id: str, *, expected_fingerprint: str | None = None
    ) -> dict[str, Any]:
        self._require_operator_owned(profile_id)
        path = self._operator_path(profile_id)
        with self._lock:
            if not path.is_file():
                raise AgentProfileError(404, "not_found", "unknown operator agent profile")
            self._check_expected(path, expected_fingerprint, creating=False)
            path.unlink()
            self.refresh()
        return {"profile_id": profile_id, "removed": True}

    def _check_expected(
        self, path: Path, expected_fingerprint: str | None, *, creating: bool
    ) -> None:
        if expected_fingerprint is None:
            if creating and path.is_file():
                raise AgentProfileError(
                    409, "conflict",
                    "an operator agent profile with this id already exists; edit it instead",
                )
            return
        try:
            stored = self._stored(path)
        except Exception:
            stored = None
        if stored is None:
            raise AgentProfileError(
                409, "conflict", "the profile being edited no longer exists; reload before saving"
            )
        if profile_fingerprint(stored) != expected_fingerprint:
            raise AgentProfileError(
                409, "conflict", "the profile changed since it was read; reload before saving"
            )
