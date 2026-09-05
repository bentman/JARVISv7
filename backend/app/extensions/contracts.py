from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from backend.app.actions.contracts import (
    AvailabilityState,
    ReadinessState,
    _require_mapping,
    _require_non_empty,
    _require_one_of,
    _validate_untrusted_claims,
)

ExtensionFamily = Literal[
    "setting", "personality", "provider", "search_provider",
    "prompt", "skill", "capability", "hook", "plugin",
]
TrustStatus = Literal["application", "operator", "external", "untrusted"]
ExtensionState = Literal["enabled", "disabled", "retired"]

EXTENSION_FAMILIES = {
    "setting", "personality", "provider", "search_provider",
    "prompt", "skill", "capability", "hook", "plugin",
}
TRUST_STATUSES = {"application", "operator", "external", "untrusted"}
EXTENSION_STATES = {"enabled", "disabled", "retired"}
READINESS_STATES = {"ready", "degraded", "unavailable"}
AVAILABILITY_STATES = {"available", "disabled", "misconfigured", "unknown"}
DEFINED_FAMILIES = {"hook", "plugin"}

SAFE_LOCAL_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


class ExtensionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExtensionDescriptor:
    extension_id: str
    family: ExtensionFamily
    local_id: str
    version: str
    display_name: str
    source: str
    provenance: str
    trust: TrustStatus
    state: ExtensionState
    readiness: ReadinessState
    availability: AvailabilityState
    unavailable_explanation: str = ""
    dependencies: tuple[str, ...] = ()
    collisions: tuple[str, ...] = ()
    metadata_claims: dict[str, Any] = field(default_factory=dict)
    definition: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "extension_id", "family", "local_id", "version",
            "display_name", "source", "provenance", "trust", "state",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_mapping("metadata_claims", self.metadata_claims)
        _require_mapping("definition", self.definition)
        _require_one_of("family", self.family, EXTENSION_FAMILIES)
        _require_one_of("trust", self.trust, TRUST_STATUSES)
        _require_one_of("state", self.state, EXTENSION_STATES)
        _require_one_of("readiness", self.readiness, READINESS_STATES)
        _require_one_of("availability", self.availability, AVAILABILITY_STATES)
        if not SAFE_LOCAL_ID.match(self.local_id):
            raise ExtensionError(f"local_id must match {SAFE_LOCAL_ID.pattern}: {self.local_id}")
        if self.extension_id != f"{self.family}:{self.local_id}":
            raise ExtensionError("extension_id must be '<family>:<local_id>'")
        if self.availability != "available":
            _require_non_empty("unavailable_explanation", self.unavailable_explanation)
        _validate_untrusted_claims(self.metadata_claims)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["dependencies"] = list(self.dependencies)
        payload["collisions"] = list(self.collisions)
        return payload


def extension_id(family: str, local_id: str) -> str:
    return f"{family}:{local_id}"


class ExtensionCatalog:
    def __init__(self) -> None:
        self._descriptors: dict[str, ExtensionDescriptor] = {}

    def register(self, descriptor: ExtensionDescriptor) -> ExtensionDescriptor:
        if descriptor.family in DEFINED_FAMILIES and not descriptor.definition:
            raise ExtensionError(
                f"{descriptor.family} extensions must declare a definition before registration"
            )
        if descriptor.extension_id in self._descriptors:
            raise ExtensionError(f"extension already registered: {descriptor.extension_id}")
        self._descriptors[descriptor.extension_id] = descriptor
        return descriptor

    def get(self, extension_id_value: str) -> ExtensionDescriptor | None:
        return self._descriptors.get(extension_id_value)

    def snapshot(self) -> list[dict[str, Any]]:
        return [self._descriptors[key].to_dict() for key in sorted(self._descriptors)]

    def families(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for descriptor in self._descriptors.values():
            counts[descriptor.family] = counts.get(descriptor.family, 0) + 1
        return dict(sorted(counts.items()))
