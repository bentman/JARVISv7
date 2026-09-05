from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import psutil
from backend.app.actions.boundaries import (
    ActionCancelledError,
    ActionOperation,
    BoundaryViolationError,
    ProcessBoundary,
    bound_result,
)

_POLL_SECONDS = 0.01
_STOP_SECONDS = 1.0


def run_process(
    operation: ActionOperation,
    process_boundary: ProcessBoundary,
    argv: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run application-supplied argv within the declared process boundary.

    This is an execution primitive, not an authorization mechanism.  Callers must
    supply argv after capability authorization and never construct it from shell text.
    """
    process_boundary.validate_argv(argv)
    operation.check()
    child_environment = process_boundary.scrub_environment(environment or os.environ)
    executable = _resolve_executable(argv[0], child_environment)
    command = [str(executable), *argv[1:]]
    working_directory = process_boundary.resolve_working_directory()
    working_directory.mkdir(parents=True, exist_ok=True)
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            command,
            cwd=working_directory,
            env=child_environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=os.name != "nt",
            creationflags=creationflags,
        )
    except BaseException:
        operation.done.set()
        raise
    stdout = bytearray()
    stderr = bytearray()
    output_lock = threading.Lock()
    output_exceeded = threading.Event()

    def collect(stream: Any, target: bytearray) -> None:
        while chunk := stream.read(4096):
            with output_lock:
                remaining = operation.boundary.max_result_bytes - len(stdout) - len(stderr)
                if remaining <= 0:
                    output_exceeded.set()
                    continue
                target.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    output_exceeded.set()

    stdout_thread = threading.Thread(target=collect, args=(process.stdout, stdout), daemon=True)
    stderr_thread = threading.Thread(target=collect, args=(process.stderr, stderr), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    cancelled = False
    try:
        while process.poll() is None:
            if operation.cancel.is_set() or operation.expired():
                cancelled = True
                break
            if output_exceeded.is_set():
                raise BoundaryViolationError("process output exceeded max_result_bytes")
            time.sleep(_POLL_SECONDS)
    except BaseException:
        _stop_process_tree(process.pid)
        raise
    finally:
        if cancelled:
            _stop_process_tree(process.pid)
        try:
            process.wait(timeout=_STOP_SECONDS)
        except subprocess.TimeoutExpired:
            _stop_process_tree(process.pid)
            process.wait(timeout=_STOP_SECONDS)
        if not cancelled and (stdout_thread.is_alive() or stderr_thread.is_alive()):
            _stop_leftover_process_group(process.pid)
        stdout_thread.join(timeout=_STOP_SECONDS)
        stderr_thread.join(timeout=_STOP_SECONDS)
        operation.done.set()

    if cancelled:
        raise ActionCancelledError(f"action cancelled: {operation.capability_id}")
    if output_exceeded.is_set():
        raise BoundaryViolationError("process output exceeded max_result_bytes")
    artifacts: dict[str, Any] = {
        "duration_ms": round(operation.elapsed_ms(), 3),
        "argv_executable": str(executable),
    }
    result = {
        "exit_code": process.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }
    return bound_result(result, operation.boundary.max_result_bytes, artifacts), artifacts


def _resolve_executable(value: str, environment: Mapping[str, str]) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        resolved = candidate.resolve()
        if not resolved.is_file():
            raise BoundaryViolationError(f"argv executable is unavailable: {value}")
        return resolved
    found = shutil.which(value, path=environment.get("PATH", ""))
    if found is None:
        raise BoundaryViolationError(f"argv executable is unavailable: {value}")
    return Path(found).resolve()


def _stop_process_tree(pid: int) -> None:
    """Terminate a child process and descendants on both supported host families."""
    try:
        parent = psutil.Process(pid)
        processes = [*parent.children(recursive=True), parent]
    except psutil.NoSuchProcess:
        return
    for child in reversed(processes):
        try:
            child.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    _, alive = psutil.wait_procs(processes, timeout=_STOP_SECONDS)
    for child in alive:
        try:
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    psutil.wait_procs(alive, timeout=_STOP_SECONDS)


def _stop_leftover_process_group(pid: int) -> None:
    """A successful POSIX parent may leave descendants holding its output pipes."""
    if os.name != "posix":
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


__all__ = ["run_process"]
