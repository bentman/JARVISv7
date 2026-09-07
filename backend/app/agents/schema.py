from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

INVOCATION_MODES = {"direct", "router_selected", "as_tool", "handoff"}
MEMORY_SCOPES = {"none", "working", "episodic", "semantic", "full"}
APPROVAL_CLASSES = {"none", "standard", "strict"}
AUTHORITY_FIELDS = {
    "tool_policy",
    "routing_policy",
    "memory_policy",
    "safety_overrides",
    "hidden_instructions",
}

_SAFE_PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_PROFILE_ID_MAX_LEN = 64
_TIMEOUT_MIN_MS = 1000
_TIMEOUT_MAX_MS = 600000

_REQUIRED_KEYS = {
    "profile_id",
    "display_name",
    "purpose",
    "instructions",
    "invocation_modes",
    "capability_ids",
    "memory_scope",
    "approval_class",
    "timeout_ms",
    "cancellable",
    "output_contract",
    "provider_model_policy",
}


def _validate_non_empty_string(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_profile_id(value: str) -> None:
    _validate_non_empty_string("profile_id", value)
    if len(value) > _PROFILE_ID_MAX_LEN:
        raise ValueError(f"profile_id must be at most {_PROFILE_ID_MAX_LEN} characters")
    if not _SAFE_PROFILE_ID_RE.fullmatch(value):
        raise ValueError("profile_id must contain only lowercase letters, numbers, and hyphens")


def _validate_invocation_modes(modes: tuple[str, ...]) -> None:
    if not isinstance(modes, tuple) or not modes:
        raise ValueError("invocation_modes must be a non-empty list")
    for mode in modes:
        if not isinstance(mode, str) or mode not in INVOCATION_MODES:
            allowed = ", ".join(sorted(INVOCATION_MODES))
            raise ValueError(
                f"invalid invocation_mode: {mode!r}; expected one of: {allowed}"
            )


def _validate_capability_ids(capability_ids: tuple[str, ...]) -> None:
    if not isinstance(capability_ids, tuple):
        raise ValueError("capability_ids must be a list")
    for cap_id in capability_ids:
        if not isinstance(cap_id, str) or not cap_id.strip():
            raise ValueError("capability_ids entries must be non-empty strings")


def _validate_output_contract(contract: dict[str, Any]) -> None:
    if not isinstance(contract, dict):
        raise ValueError("output_contract must be a mapping")
    if "type" not in contract:
        raise ValueError("output_contract must contain a 'type' key")


@dataclass(frozen=True, slots=True)
class AgentProfile:
    profile_id: str
    display_name: str
    purpose: str
    instructions: str
    invocation_modes: tuple[str, ...]
    capability_ids: tuple[str, ...]
    memory_scope: str
    approval_class: str
    timeout_ms: int
    cancellable: bool
    output_contract: dict[str, Any]
    provider_model_policy: dict[str, Any]

    def __post_init__(self) -> None:
        _validate_profile_id(self.profile_id)
        _validate_non_empty_string("display_name", self.display_name)
        _validate_non_empty_string("purpose", self.purpose)
        _validate_non_empty_string("instructions", self.instructions)
        _validate_invocation_modes(self.invocation_modes)
        _validate_capability_ids(self.capability_ids)
        if self.memory_scope not in MEMORY_SCOPES:
            allowed = ", ".join(sorted(MEMORY_SCOPES))
            raise ValueError(
                f"invalid memory_scope: {self.memory_scope!r}; expected one of: {allowed}"
            )
        if self.approval_class not in APPROVAL_CLASSES:
            allowed = ", ".join(sorted(APPROVAL_CLASSES))
            raise ValueError(
                f"invalid approval_class: {self.approval_class!r}; expected one of: {allowed}"
            )
        if not isinstance(self.timeout_ms, int) or not (
            _TIMEOUT_MIN_MS <= self.timeout_ms <= _TIMEOUT_MAX_MS
        ):
            raise ValueError(
                f"timeout_ms must be between {_TIMEOUT_MIN_MS} and {_TIMEOUT_MAX_MS}"
            )
        if not isinstance(self.cancellable, bool):
            raise ValueError("cancellable must be a boolean")
        _validate_output_contract(self.output_contract)
        if not isinstance(self.provider_model_policy, dict):
            raise ValueError("provider_model_policy must be a mapping")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentProfile:
        _reject_authority_fields(data)
        _check_required_keys(data)
        return cls(
            profile_id=data["profile_id"],
            display_name=data["display_name"],
            purpose=data["purpose"],
            instructions=data["instructions"],
            invocation_modes=tuple(data["invocation_modes"]),
            capability_ids=tuple(data.get("capability_ids", [])),
            memory_scope=data["memory_scope"],
            approval_class=data["approval_class"],
            timeout_ms=data["timeout_ms"],
            cancellable=data["cancellable"],
            output_contract=data["output_contract"],
            provider_model_policy=data.get("provider_model_policy", {}),
        )


def _reject_authority_fields(data: dict[str, Any]) -> None:
    found = set(data) & AUTHORITY_FIELDS
    if found:
        names = ", ".join(sorted(found))
        raise ValueError(f"agent profile contains prohibited authority fields: {names}")


def _check_required_keys(data: dict[str, Any]) -> None:
    missing = sorted(key for key in _REQUIRED_KEYS if key not in data)
    if missing:
        raise ValueError(f"agent profile missing required fields: {', '.join(missing)}")
