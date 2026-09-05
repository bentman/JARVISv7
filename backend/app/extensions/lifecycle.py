from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backend.app.actions.contracts import EFFECT_CLASSES, EffectClass
from backend.app.extensions.contracts import ExtensionError

# Lifecycle points a future hook runner may attach to. Each name matches a moment the
# conversation engine already reaches, so a hook can never invent its own event.
HOOK_EVENTS: tuple[str, ...] = (
    "session_started",
    "turn_admitted",
    "transcript_committed",
    "prompt_assembled",
    "response_ready",
    "turn_persisted",
    "session_closed",
)

# A hook that only reads local state may run inline. Anything with a wider effect has to
# invoke a governed capability, so hooks cannot become a parallel execution path.
INLINE_HOOK_EFFECT_CLASSES: frozenset[str] = frozenset({"local_read"})

PLUGIN_LIFECYCLE_STATES: tuple[str, ...] = (
    "discovered", "installed", "enabled", "disabled", "retired",
)
PLUGIN_TRANSITIONS: dict[str, frozenset[str]] = {
    "discovered": frozenset({"installed", "retired"}),
    "installed": frozenset({"enabled", "disabled", "retired"}),
    "enabled": frozenset({"disabled", "retired"}),
    "disabled": frozenset({"enabled", "retired"}),
    "retired": frozenset(),
}


@dataclass(frozen=True, slots=True)
class HookDefinition:
    hook_id: str
    event: str
    effect_class: EffectClass
    capability_id: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if self.event not in HOOK_EVENTS:
            raise ExtensionError(f"hook event must be one of: {', '.join(HOOK_EVENTS)}")
        if self.effect_class not in EFFECT_CLASSES:
            raise ExtensionError(f"effect_class must be one of: {', '.join(sorted(EFFECT_CLASSES))}")
        if self.effect_class not in INLINE_HOOK_EFFECT_CLASSES and not self.capability_id:
            raise ExtensionError(
                f"a {self.effect_class} hook must invoke a governed capability, not execute inline"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PluginDefinition:
    plugin_id: str
    version: str
    state: str
    contained_extension_ids: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if self.state not in PLUGIN_LIFECYCLE_STATES:
            raise ExtensionError(
                f"plugin state must be one of: {', '.join(PLUGIN_LIFECYCLE_STATES)}"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contained_extension_ids"] = list(self.contained_extension_ids)
        return payload


def validate_plugin_transition(current: str, target: str) -> None:
    if current not in PLUGIN_LIFECYCLE_STATES:
        raise ExtensionError(f"unknown plugin state: {current}")
    if target not in PLUGIN_TRANSITIONS[current]:
        allowed = ", ".join(sorted(PLUGIN_TRANSITIONS[current])) or "nothing"
        raise ExtensionError(f"plugin cannot move from {current} to {target}; allowed: {allowed}")
