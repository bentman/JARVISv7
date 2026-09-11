from __future__ import annotations

import threading
from pathlib import Path

import pytest
from backend.app.actions.boundaries import (
    ActionCancelledError,
    ActionOperation,
    AgentIsolation,
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
    return ExecutionBoundary(**values)  # type: ignore[arg-type]


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
        run_bounded(operation(), lambda op: ["not", "a", "mapping"])  # type: ignore[arg-type, return-value]


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


# ---------------------------------------------------------------------------
# AgentIsolation tests
# ---------------------------------------------------------------------------


def _pb(**overrides: object) -> ProcessBoundary:
    values: dict[str, object] = {
        "subprocess": True,
        "argv_allowlist": ["python"],
        "env_passthrough": ["PATH"],
        "working_root": "data",
    }
    values.update(overrides)
    return ProcessBoundary.from_mapping(values)


def _agent(**overrides: object) -> AgentIsolation:
    defaults: dict[str, object] = {
        "process_boundary": _pb(),
        "agent_id": "agent-1",
        "max_output_bytes": 64000,
        "allowed_temp_roots": (),
        "credential_refs": (),
        "cleanup_on_exit": True,
    }
    defaults.update(overrides)
    return AgentIsolation(**defaults)  # type: ignore[arg-type]


class TestAgentIsolationCreation:
    def test_valid_creation(self) -> None:
        agent = _agent()
        assert agent.agent_id == "agent-1"
        assert agent.max_output_bytes == 64000
        assert agent.cleanup_on_exit is True
        assert agent.allowed_temp_roots == ()
        assert agent.credential_refs == ()

    def test_valid_agent_id_with_digits_and_dashes(self) -> None:
        agent = _agent(agent_id="a1-b2-c3")
        assert agent.agent_id == "a1-b2-c3"


class TestAgentIdValidation:
    def test_empty_agent_id_is_refused(self) -> None:
        with pytest.raises(BoundaryViolationError, match="agent_id must match"):
            _agent(agent_id="")

    def test_uppercase_agent_id_is_refused(self) -> None:
        with pytest.raises(BoundaryViolationError, match="agent_id must match"):
            _agent(agent_id="Agent-1")

    def test_special_chars_agent_id_is_refused(self) -> None:
        with pytest.raises(BoundaryViolationError, match="agent_id must match"):
            _agent(agent_id="agent_1!")

    def test_leading_dash_is_refused(self) -> None:
        with pytest.raises(BoundaryViolationError, match="agent_id must match"):
            _agent(agent_id="-agent")


class TestMaxOutputBytes:
    def test_too_low(self) -> None:
        with pytest.raises(BoundaryViolationError, match="max_output_bytes"):
            _agent(max_output_bytes=512)

    def test_too_high(self) -> None:
        with pytest.raises(BoundaryViolationError, match="max_output_bytes"):
            _agent(max_output_bytes=2_000_000_000)

    def test_lower_boundary_accepted(self) -> None:
        agent = _agent(max_output_bytes=1024)
        assert agent.max_output_bytes == 1024

    def test_upper_boundary_accepted(self) -> None:
        agent = _agent(max_output_bytes=1_000_000_000)
        assert agent.max_output_bytes == 1_000_000_000


class TestAllowedTempRoots:
    def test_valid_temp_roots(self) -> None:
        agent = _agent(allowed_temp_roots=("data/agent-tmp", "cache/agent-work"))
        assert agent.allowed_temp_roots == ("data/agent-tmp", "cache/agent-work")

    def test_temp_root_outside_allowed_storage_roots(self) -> None:
        with pytest.raises(BoundaryViolationError, match="allowed_temp_roots"):
            _agent(allowed_temp_roots=("models/weights",))

    def test_temp_root_with_unknown_prefix(self) -> None:
        with pytest.raises(BoundaryViolationError, match="allowed_temp_roots"):
            _agent(allowed_temp_roots=("etc/config",))

    def test_temp_root_matching_storage_root_exactly_is_refused(self) -> None:
        with pytest.raises(BoundaryViolationError, match="allowed_temp_roots"):
            _agent(allowed_temp_roots=("data",))


class TestSubprocessRequirement:
    def test_requires_subprocess_true(self) -> None:
        pb = ProcessBoundary.from_mapping({
            "subprocess": False,
            "argv_allowlist": ["python"],
            "env_passthrough": ["PATH"],
            "working_root": "data",
        })
        with pytest.raises(BoundaryViolationError, match="subprocess=True"):
            _agent(process_boundary=pb)


class TestValidateAgentEnvironment:
    def test_scrubs_sensitive_keys(self) -> None:
        agent = _agent(
            process_boundary=_pb(env_passthrough=["PATH", "HOME"])
        )
        env = {
            "PATH": "/usr/bin",
            "HOME": "/home/agent",
            "API_TOKEN": "secret-token",
            "DB_PASSWORD": "hunter2",
            "AWS_SECRET": "s3cret",
            "MY_CREDENTIAL": "cred-value",
            "PRIVATE_KEY": "key-data",
        }
        result = agent.validate_agent_environment(env)
        assert result == {"PATH": "/usr/bin", "HOME": "/home/agent"}

    def test_preserves_allowlisted_sensitive_keys(self) -> None:
        agent = _agent(
            process_boundary=_pb(env_passthrough=["PATH", "MY_TOKEN"])
        )
        env = {
            "PATH": "/usr/bin",
            "MY_TOKEN": "allowed-token",
            "UNRELATED_SECRET": "must-scrub",
        }
        result = agent.validate_agent_environment(env)
        assert result == {"PATH": "/usr/bin", "MY_TOKEN": "allowed-token"}

    def test_case_insensitive_sensitive_matching(self) -> None:
        agent = _agent(process_boundary=_pb(env_passthrough=["PATH"]))
        env = {
            "PATH": "/usr/bin",
            "api_token": "lowercase-secret",
            "Api_Key": "mixed-case-secret",
        }
        result = agent.validate_agent_environment(env)
        assert result == {"PATH": "/usr/bin"}


class TestResolveAgentWorkingDirectory:
    def test_resolves_within_working_root(self) -> None:
        agent = _agent()
        resolved = agent.resolve_agent_working_directory()
        expected = (REPO_ROOT / "data").resolve()
        assert resolved == expected

    def test_refuses_escape_via_relative_path(self) -> None:
        from unittest.mock import patch

        pb = ProcessBoundary.from_mapping({
            "subprocess": True,
            "argv_allowlist": ["python"],
            "env_passthrough": ["PATH"],
            "working_root": "data",
        })
        agent = _agent(process_boundary=pb)
        with patch.object(
            type(pb), "resolve_working_directory", return_value=Path("/etc/passwd"),
        ), pytest.raises(BoundaryViolationError, match="escapes"):
            agent.resolve_agent_working_directory()


class TestFromMapping:
    def test_with_defaults(self) -> None:
        agent = AgentIsolation.from_mapping("agent-1", {
            "process": {
                "subprocess": True,
                "argv_allowlist": ["python"],
                "env_passthrough": ["PATH"],
                "working_root": "data",
            },
        })
        assert agent.agent_id == "agent-1"
        assert agent.max_output_bytes == 64000
        assert agent.allowed_temp_roots == ()
        assert agent.credential_refs == ()
        assert agent.cleanup_on_exit is True

    def test_with_all_fields(self) -> None:
        agent = AgentIsolation.from_mapping("agent-2", {
            "process": {
                "subprocess": True,
                "argv_allowlist": ["git"],
                "env_passthrough": ["PATH", "HOME"],
                "working_root": "cache",
            },
            "max_output_bytes": 128000,
            "allowed_temp_roots": ["cache/agent-tmp"],
            "credential_refs": ["github-pat"],
            "cleanup_on_exit": False,
        })
        assert agent.agent_id == "agent-2"
        assert agent.max_output_bytes == 128000
        assert agent.allowed_temp_roots == ("cache/agent-tmp",)
        assert agent.credential_refs == ("github-pat",)
        assert agent.cleanup_on_exit is False

    def test_unknown_keys_rejected(self) -> None:
        with pytest.raises(BoundaryViolationError, match="unknown keys"):
            AgentIsolation.from_mapping("agent-1", {
                "process": {
                    "subprocess": True,
                    "argv_allowlist": ["python"],
                    "env_passthrough": ["PATH"],
                    "working_root": "data",
                },
                "bogus_field": True,
            })

    def test_missing_process_rejected(self) -> None:
        with pytest.raises(BoundaryViolationError, match="must include 'process'"):
            AgentIsolation.from_mapping("agent-1", {"max_output_bytes": 64000})

    def test_invalid_process_data_rejected(self) -> None:
        with pytest.raises(BoundaryViolationError):
            AgentIsolation.from_mapping("agent-1", {"process": {}})


class TestToDict:
    def test_roundtrip(self) -> None:
        agent = _agent(
            allowed_temp_roots=("data/agent-tmp",),
            credential_refs=("github-pat",),
        )
        serialized = agent.to_dict()
        restored = AgentIsolation.from_mapping(
            serialized["agent_id"],
            {
                "process": serialized["process_boundary"],
                "max_output_bytes": serialized["max_output_bytes"],
                "allowed_temp_roots": serialized["allowed_temp_roots"],
                "credential_refs": serialized["credential_refs"],
                "cleanup_on_exit": serialized["cleanup_on_exit"],
            },
        )
        assert restored.agent_id == agent.agent_id
        assert restored.max_output_bytes == agent.max_output_bytes
        assert restored.allowed_temp_roots == agent.allowed_temp_roots
        assert restored.credential_refs == agent.credential_refs
        assert restored.cleanup_on_exit == agent.cleanup_on_exit

    def test_to_dict_structure(self) -> None:
        agent = _agent()
        d = agent.to_dict()
        assert set(d.keys()) == {
            "process_boundary",
            "agent_id",
            "max_output_bytes",
            "allowed_temp_roots",
            "credential_refs",
            "cleanup_on_exit",
        }
        assert isinstance(d["process_boundary"], dict)
        assert isinstance(d["allowed_temp_roots"], list)
        assert isinstance(d["credential_refs"], list)


class TestCleanupOnExit:
    def test_default_true(self) -> None:
        agent = _agent()
        assert agent.cleanup_on_exit is True

    def test_explicit_false(self) -> None:
        agent = _agent(cleanup_on_exit=False)
        assert agent.cleanup_on_exit is False

    def test_from_mapping_default_true(self) -> None:
        agent = AgentIsolation.from_mapping("agent-1", {
            "process": {
                "subprocess": True,
                "argv_allowlist": ["python"],
                "env_passthrough": ["PATH"],
                "working_root": "data",
            },
        })
        assert agent.cleanup_on_exit is True
