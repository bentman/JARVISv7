from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest
from backend.app.actions.boundaries import (
    ActionCancelledError,
    ActionOperation,
    BoundaryViolationError,
    ExecutionBoundary,
    ProcessBoundary,
)
from backend.app.actions.process import run_process


def _operation(*, timeout_ms: int = 2_000, max_result_bytes: int = 2_000) -> ActionOperation:
    return ActionOperation(
        "session-1",
        "turn-1",
        "proposal-1",
        "skill-script",
        ExecutionBoundary(("data",), timeout_ms, True, max_result_bytes),
    )


def _process_boundary(*, environment: tuple[str, ...] = ()) -> ProcessBoundary:
    return ProcessBoundary(True, (sys.executable,), environment, "data")


def test_runs_explicit_argv_from_the_approved_working_root() -> None:
    result, artifacts = run_process(
        _operation(), _process_boundary(), (sys.executable, "-c", "print('ready')")
    )

    assert result == {"exit_code": 0, "stdout": "ready\n", "stderr": ""}
    assert artifacts["argv_executable"] == str(Path(sys.executable).resolve())


def test_scrubs_parent_environment_before_launching_child() -> None:
    result, _ = run_process(
        _operation(),
        _process_boundary(environment=("SAFE",)),
        (sys.executable, "-c", "import os; print(os.getenv('SAFE'), os.getenv('SECRET'))"),
        environment={"SAFE": "visible", "SECRET": "must-not-leak"},
    )

    assert result["stdout"] == "visible None\n"


def test_normalizes_captured_output_line_endings() -> None:
    result, _ = run_process(
        _operation(),
        _process_boundary(),
        (
            sys.executable,
            "-c",
            "import sys; "
            "sys.stdout.buffer.write(b'ready\\r\\nagain\\r'); "
            "sys.stderr.buffer.write(b'err\\r\\n')",
        ),
    )

    assert result["stdout"] == "ready\nagain\n"
    assert result["stderr"] == "err\n"


def test_rejects_unapproved_executable_before_launching() -> None:
    with pytest.raises(BoundaryViolationError, match="not allowlisted"):
        run_process(_operation(), _process_boundary(), ("sh", "-c", "echo no"))


def test_does_not_resolve_an_executable_from_the_parent_path_when_path_is_scrubbed() -> None:
    boundary = ProcessBoundary(True, ("python",), (), "data")

    with pytest.raises(BoundaryViolationError, match="executable is unavailable"):
        run_process(_operation(), boundary, ("python", "-c", "print('no')"), environment={})


def test_timeout_stops_the_process_and_marks_the_operation_done() -> None:
    operation = _operation(timeout_ms=30)

    with pytest.raises(ActionCancelledError):
        run_process(operation, _process_boundary(), (sys.executable, "-c", "import time; time.sleep(5)"))

    assert operation.done.is_set()


def test_explicit_cancellation_stops_the_process_and_marks_the_operation_done() -> None:
    operation = _operation()
    timer = threading.Timer(0.03, operation.cancel.set)
    timer.start()
    try:
        with pytest.raises(ActionCancelledError):
            run_process(operation, _process_boundary(), (sys.executable, "-c", "import time; time.sleep(5)"))
    finally:
        timer.cancel()

    assert operation.done.is_set()


def test_output_over_the_action_bound_is_rejected() -> None:
    with pytest.raises(BoundaryViolationError, match="output exceeded"):
        run_process(
            _operation(max_result_bytes=64),
            _process_boundary(),
            (sys.executable, "-c", "print('x' * 1000)"),
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups provide orphan cleanup")
def test_successful_parent_does_not_leave_a_descendant_holding_output_pipes() -> None:
    started = time.monotonic()
    result, _ = run_process(
        _operation(),
        _process_boundary(),
        (
            sys.executable,
            "-c",
            "import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)']); print('parent')",
        ),
    )

    assert result["exit_code"] == 0
    assert time.monotonic() - started < 0.8
