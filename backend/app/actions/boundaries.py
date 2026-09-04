from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.core.paths import REPO_ROOT

MAX_TIMEOUT_MS = 60_000
MAX_RESULT_BYTES = 64_000
ALLOWED_STORAGE_ROOTS: tuple[str, ...] = ("data", "cache", "reports", "models", "runtimes")
BOUNDED_EFFECT_CLASSES = frozenset({"privileged_execution"})
CANCELLABLE_EFFECT_CLASSES = frozenset({"privileged_execution", "destructive_action"})
BOUNDARY_KEYS = ("storage_roots", "timeout_ms", "cancellable", "max_result_bytes")
PROCESS_BOUNDARY_KEYS = ("subprocess", "argv_allowlist", "env_passthrough", "working_root")
ENV_WILDCARDS = ("*", "**")


class ActionCancelledError(Exception):
    pass


class BoundaryViolationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionBoundary:
    storage_roots: tuple[str, ...]
    timeout_ms: int
    cancellable: bool
    max_result_bytes: int

    @classmethod
    def from_mapping(cls, boundaries: dict[str, Any]) -> ExecutionBoundary:
        violations = boundary_violations(boundaries)
        if violations:
            raise BoundaryViolationError(violations[0])
        return cls(
            storage_roots=tuple(boundaries["storage_roots"]),
            timeout_ms=int(boundaries["timeout_ms"]),
            cancellable=bool(boundaries["cancellable"]),
            max_result_bytes=int(boundaries["max_result_bytes"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "storage_roots": list(self.storage_roots),
            "timeout_ms": self.timeout_ms,
            "cancellable": self.cancellable,
            "max_result_bytes": self.max_result_bytes,
        }

    def resolve_path(self, candidate: str | Path) -> Path:
        if not self.storage_roots:
            raise BoundaryViolationError("capability declares no storage roots")
        resolved = Path(candidate).expanduser()
        if not resolved.is_absolute():
            resolved = REPO_ROOT / resolved
        resolved = resolved.resolve()
        for root in self.storage_roots:
            allowed = (REPO_ROOT / root).resolve()
            if resolved == allowed or allowed in resolved.parents:
                return resolved
        raise BoundaryViolationError("path escapes the declared storage roots")


@dataclass(frozen=True, slots=True)
class ProcessBoundary:
    subprocess: bool
    argv_allowlist: tuple[str, ...]
    env_passthrough: tuple[str, ...]
    working_root: str

    @classmethod
    def from_mapping(cls, process: dict[str, Any]) -> ProcessBoundary:
        violations = process_violations(process)
        if violations:
            raise BoundaryViolationError(violations[0])
        return cls(
            subprocess=bool(process["subprocess"]),
            argv_allowlist=tuple(process["argv_allowlist"]),
            env_passthrough=tuple(process["env_passthrough"]),
            working_root=str(process["working_root"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "subprocess": self.subprocess,
            "argv_allowlist": list(self.argv_allowlist),
            "env_passthrough": list(self.env_passthrough),
            "working_root": self.working_root,
        }

    def resolve_working_directory(self) -> Path:
        if self.working_root not in ALLOWED_STORAGE_ROOTS:
            raise BoundaryViolationError("working_root is not an approved storage root")
        return (REPO_ROOT / self.working_root).resolve()

    def resolve_path(self, candidate: str | Path) -> Path:
        working = self.resolve_working_directory()
        resolved = Path(candidate).expanduser()
        if not resolved.is_absolute():
            resolved = working / resolved
        resolved = resolved.resolve()
        if resolved != working and working not in resolved.parents:
            raise BoundaryViolationError("path escapes the process working root")
        return resolved

    def scrub_environment(self, env: Mapping[str, str]) -> dict[str, str]:
        # Allowlist only: a secret in the parent environment must not reach a child by default.
        return {name: env[name] for name in self.env_passthrough if name in env}

    def validate_argv(self, argv: Sequence[str]) -> None:
        if not argv:
            raise BoundaryViolationError("argv must not be empty")
        if argv[0] not in self.argv_allowlist:
            raise BoundaryViolationError(f"argv[0] is not allowlisted: {argv[0]}")


def process_violations(process: dict[str, Any]) -> tuple[str, ...]:
    if not isinstance(process, dict):
        return ("process must be a mapping",)
    missing = [key for key in PROCESS_BOUNDARY_KEYS if key not in process]
    if missing:
        return tuple(f"process must declare {key}" for key in missing)

    violations: list[str] = []
    if not isinstance(process["subprocess"], bool):
        violations.append("subprocess must be a boolean")

    argv = process["argv_allowlist"]
    if not isinstance(argv, (list, tuple)) or any(not isinstance(item, str) for item in argv):
        violations.append("argv_allowlist must be a sequence of strings")
    elif not argv:
        violations.append("argv_allowlist must not be empty")

    env = process["env_passthrough"]
    if not isinstance(env, (list, tuple)) or any(not isinstance(item, str) for item in env):
        violations.append("env_passthrough must be a sequence of strings")
    elif any(item in ENV_WILDCARDS for item in env):
        violations.append("env_passthrough must be an explicit allowlist, not a wildcard")

    working_root = process["working_root"]
    if not isinstance(working_root, str) or working_root not in ALLOWED_STORAGE_ROOTS:
        violations.append(
            f"working_root must be one of: {', '.join(ALLOWED_STORAGE_ROOTS)}"
        )

    return tuple(violations)


def boundary_violations(boundaries: dict[str, Any]) -> tuple[str, ...]:
    if not isinstance(boundaries, dict):
        return ("boundaries must be a mapping",)
    violations: list[str] = []
    for key in BOUNDARY_KEYS:
        if key not in boundaries:
            violations.append(f"boundaries must declare {key}")
    if violations:
        return tuple(violations)

    roots = boundaries["storage_roots"]
    if not isinstance(roots, (list, tuple)) or any(not isinstance(root, str) for root in roots):
        violations.append("storage_roots must be a sequence of strings")
    else:
        unknown = [root for root in roots if root not in ALLOWED_STORAGE_ROOTS]
        if unknown:
            violations.append(
                f"storage_roots must be within {', '.join(ALLOWED_STORAGE_ROOTS)}: {unknown[0]}"
            )

    timeout_ms = boundaries["timeout_ms"]
    if not _is_int(timeout_ms) or not 1 <= timeout_ms <= MAX_TIMEOUT_MS:
        violations.append(f"timeout_ms must be an integer in 1..{MAX_TIMEOUT_MS}")

    if not isinstance(boundaries["cancellable"], bool):
        violations.append("cancellable must be a boolean")

    max_bytes = boundaries["max_result_bytes"]
    if not _is_int(max_bytes) or not 1 <= max_bytes <= MAX_RESULT_BYTES:
        violations.append(f"max_result_bytes must be an integer in 1..{MAX_RESULT_BYTES}")

    return tuple(violations)


def require_boundaries(
    effect_class: str,
    boundaries: dict[str, Any],
    timeout_policy: dict[str, Any],
    cancellation_policy: dict[str, Any],
) -> None:
    if not boundaries:
        if effect_class in BOUNDED_EFFECT_CLASSES:
            raise BoundaryViolationError(
                f"{effect_class} capabilities must declare boundaries: "
                f"{', '.join(BOUNDARY_KEYS)}"
            )
        return

    violations = boundary_violations(boundaries)
    if violations:
        raise BoundaryViolationError(violations[0])

    if boundaries["timeout_ms"] != timeout_policy.get("timeout_ms"):
        raise BoundaryViolationError("boundaries timeout_ms must match timeout_policy timeout_ms")
    if boundaries["cancellable"] != cancellation_policy.get("cancellable"):
        raise BoundaryViolationError("boundaries cancellable must match cancellation_policy cancellable")
    if effect_class in CANCELLABLE_EFFECT_CLASSES and not boundaries["cancellable"]:
        raise BoundaryViolationError(f"{effect_class} capabilities must be cancellable")
    if effect_class in BOUNDED_EFFECT_CLASSES and not boundaries["storage_roots"]:
        raise BoundaryViolationError(f"{effect_class} capabilities must declare storage roots")

    process = boundaries.get("process")
    if effect_class in BOUNDED_EFFECT_CLASSES and not process:
        raise BoundaryViolationError(
            f"{effect_class} capabilities must declare process boundaries: "
            f"{', '.join(PROCESS_BOUNDARY_KEYS)}"
        )
    if process is None:
        return
    process_issues = process_violations(process)
    if process_issues:
        raise BoundaryViolationError(process_issues[0])
    if effect_class in BOUNDED_EFFECT_CLASSES and not process["subprocess"]:
        raise BoundaryViolationError(f"{effect_class} capabilities must declare subprocess")
    if process["working_root"] not in boundaries["storage_roots"]:
        raise BoundaryViolationError("working_root must be one of the declared storage_roots")
    # A process that cannot be stopped is not governable.
    if not boundaries["cancellable"]:
        raise BoundaryViolationError("capabilities declaring process boundaries must be cancellable")


class ActionOperation:
    def __init__(
        self,
        session_id: str,
        turn_id: str,
        proposal_id: str,
        capability_id: str,
        boundary: ExecutionBoundary,
    ) -> None:
        self.session_id = session_id
        self.turn_id = turn_id
        self.proposal_id = proposal_id
        self.capability_id = capability_id
        self.boundary = boundary
        self.cancel = threading.Event()
        self.done = threading.Event()
        self.lock = threading.RLock()
        self.started = time.monotonic()

    def check(self) -> None:
        if self.cancel.is_set() or self.expired():
            raise ActionCancelledError(f"action cancelled: {self.capability_id}")

    def expired(self) -> bool:
        return self.elapsed_ms() > self.boundary.timeout_ms

    def elapsed_ms(self) -> float:
        return (time.monotonic() - self.started) * 1000

    def snapshot(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "capability_id": self.capability_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "cancel_requested": self.cancel.is_set(),
            "duration_ms": round(self.elapsed_ms(), 3),
        }


def run_bounded(
    operation: ActionOperation,
    handler: Callable[[ActionOperation], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    boundary = operation.boundary
    artifacts: dict[str, Any] = {}
    # A synchronous handler cannot be pre-empted in-process, so the deadline sets the
    # same cancel signal a caller would and enforcement is cooperative.
    deadline = threading.Timer(boundary.timeout_ms / 1000, operation.cancel.set)
    deadline.daemon = True
    operation.check()
    deadline.start()
    try:
        result = handler(operation)
    finally:
        deadline.cancel()
        operation.done.set()
    operation.check()
    artifacts["duration_ms"] = round(operation.elapsed_ms(), 3)
    if operation.expired():
        artifacts["timeout_exceeded"] = True
    return bound_result(result, boundary.max_result_bytes, artifacts), artifacts


def bound_result(
    result: dict[str, Any], max_result_bytes: int, artifacts: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise BoundaryViolationError("capability handlers must return a mapping")
    encoded = len(json.dumps(result, default=str).encode("utf-8"))
    if encoded <= max_result_bytes:
        return result
    artifacts["result_truncated"] = True
    artifacts["result_bytes"] = encoded
    return {"truncated": True, "byte_bound": max_result_bytes, "result_bytes": encoded}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
