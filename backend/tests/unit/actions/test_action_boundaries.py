from __future__ import annotations

import threading
from pathlib import Path

import pytest
from backend.app.actions.boundaries import (
    ActionCancelledError,
    ActionOperation,
    BoundaryViolationError,
    ExecutionBoundary,
    ProcessBoundary,
    run_bounded,
)
from backend.app.core.paths import REPO_ROOT

CAPABILITY_ID = "local-note-write"


def boundary(**overrides) -> ExecutionBoundary:
    values = {
        "storage_roots": ("data",),
        "timeout_ms": 5000,
        "cancellable": True,
        "max_result_bytes": 2000,
    }
    values.update(overrides)
    return ExecutionBoundary(**values)


def operation(**overrides) -> ActionOperation:
    return ActionOperation("session-1", "api:proposal-1", "proposal-1", CAPABILITY_ID, boundary(**overrides))


def test_cancellation_stops_execution_before_the_result_is_returned() -> None:
    action = operation()
    observed: list[str] = []

    def handler(op: ActionOperation) -> dict:
        op.cancel.set()
        observed.append("ran")
        return {"ok": True}

    with pytest.raises(ActionCancelledError):
        run_bounded(action, handler)

    assert observed == ["ran"]
    assert action.done.is_set()


def test_an_expired_deadline_cancels_a_cooperative_handler() -> None:
    action = operation(timeout_ms=1)
    released = threading.Event()

    def handler(op: ActionOperation) -> dict:
        released.wait(1.0)
        op.check()
        return {"ok": True}

    with pytest.raises(ActionCancelledError):
        run_bounded(action, handler)

    assert action.expired()


def test_an_over_bound_result_is_replaced_rather_than_returned_whole() -> None:
    action = operation(max_result_bytes=64)
    secret = "x" * 500

    result, artifacts = run_bounded(action, lambda op: {"payload": secret})

    assert result == {"truncated": True, "byte_bound": 64, "result_bytes": artifacts["result_bytes"]}
    assert artifacts["result_truncated"] is True
    assert secret not in str(result)


def test_a_result_within_the_bound_is_returned_untouched() -> None:
    result, artifacts = run_bounded(operation(), lambda op: {"source_count": 2})

    assert result == {"source_count": 2}
    assert "result_truncated" not in artifacts
    assert artifacts["duration_ms"] >= 0


def test_handlers_must_return_a_mapping() -> None:
    with pytest.raises(BoundaryViolationError, match="capability handlers must return a mapping"):
        run_bounded(operation(), lambda op: ["not", "a", "mapping"])


def test_storage_roots_outside_the_approved_roots_are_refused() -> None:
    with pytest.raises(BoundaryViolationError, match="storage_roots must be within"):
        ExecutionBoundary.from_mapping(
            {"storage_roots": ["/etc"], "timeout_ms": 100, "cancellable": True, "max_result_bytes": 10}
        )


@pytest.mark.parametrize(
    "candidate",
    ["data/../../etc/passwd", "../etc/passwd", "/etc/passwd", "reports/summary.txt"],
)
def test_resolve_path_refuses_anything_outside_the_declared_roots(candidate: str) -> None:
    with pytest.raises(BoundaryViolationError, match="escapes the declared storage roots"):
        boundary().resolve_path(candidate)


def test_resolve_path_accepts_a_path_inside_a_declared_root() -> None:
    resolved = boundary().resolve_path("data/sessions/turn.json")

    assert resolved == (REPO_ROOT / "data" / "sessions" / "turn.json").resolve()
    assert Path(REPO_ROOT / "data").resolve() in resolved.parents


def test_a_capability_with_no_declared_roots_cannot_resolve_any_path() -> None:
    with pytest.raises(BoundaryViolationError, match="declares no storage roots"):
        boundary(storage_roots=()).resolve_path("data/sessions/turn.json")


def process(**overrides) -> dict:
    values = {
        "subprocess": True,
        "argv_allowlist": ["git"],
        "env_passthrough": ["PATH"],
        "working_root": "data",
    }
    values.update(overrides)
    return values


def test_a_process_boundary_scrubs_every_environment_key_it_did_not_allowlist() -> None:
    boundary = ProcessBoundary.from_mapping(process(env_passthrough=["PATH"]))

    scrubbed = boundary.scrub_environment(
        {
            "PATH": "/usr/bin",
            "JARVIS_SECRET_STORE_KEY": "must-not-leak",
            "TAVILY_API_KEY": "must-not-leak",
        }
    )

    assert scrubbed == {"PATH": "/usr/bin"}
    assert "must-not-leak" not in str(scrubbed)


def test_an_empty_environment_allowlist_scrubs_everything() -> None:
    boundary = ProcessBoundary.from_mapping(process(env_passthrough=[]))

    assert boundary.scrub_environment({"PATH": "/usr/bin"}) == {}


def test_a_wildcard_environment_allowlist_is_refused() -> None:
    with pytest.raises(BoundaryViolationError, match="explicit allowlist, not a wildcard"):
        ProcessBoundary.from_mapping(process(env_passthrough=["*"]))


def test_an_empty_argv_allowlist_is_refused() -> None:
    with pytest.raises(BoundaryViolationError, match="argv_allowlist must not be empty"):
        ProcessBoundary.from_mapping(process(argv_allowlist=[]))


def test_argv_must_name_an_allowlisted_executable() -> None:
    boundary = ProcessBoundary.from_mapping(process(argv_allowlist=["git"]))

    boundary.validate_argv(["git", "status"])

    with pytest.raises(BoundaryViolationError, match="argv\\[0\\] is not allowlisted: bash"):
        boundary.validate_argv(["bash", "-c", "echo pwned"])
    with pytest.raises(BoundaryViolationError, match="argv must not be empty"):
        boundary.validate_argv([])


def test_a_working_root_outside_the_approved_roots_is_refused() -> None:
    with pytest.raises(BoundaryViolationError, match="working_root must be one of"):
        ProcessBoundary.from_mapping(process(working_root="/etc"))


@pytest.mark.parametrize("candidate", ["../etc/passwd", "/etc/passwd", "data/../../etc"])
def test_a_process_path_cannot_escape_its_working_root(candidate: str) -> None:
    boundary = ProcessBoundary.from_mapping(process())

    with pytest.raises(BoundaryViolationError, match="escapes the process working root"):
        boundary.resolve_path(candidate)


def test_a_process_path_inside_the_working_root_resolves() -> None:
    boundary = ProcessBoundary.from_mapping(process())

    assert boundary.resolve_path("sessions/turn.json") == (
        REPO_ROOT / "data" / "sessions" / "turn.json"
    ).resolve()
