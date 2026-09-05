from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from backend.app.actions.boundaries import (
    ActionOperation,
    BoundaryViolationError,
    ExecutionBoundary,
)
from backend.app.extensions.acp import AcpDefinition, run_acp


def _operation(capability_id: str = "privileged_execution") -> ActionOperation:
    return ActionOperation(
        "session", "api:proposal", "proposal", capability_id,
        ExecutionBoundary(("data",), 5_000, True, 2_000),
    )


def _definition() -> AcpDefinition:
    return AcpDefinition.from_mapping(
        "coding-agent",
        {
            "command": ["agent-bin", "serve"],
            "process": {
                "subprocess": True,
                "argv_allowlist": ["agent-bin"],
                "env_passthrough": [],
                "working_root": "data",
            },
        },
    )


def test_definition_requires_exact_argv_and_process_boundary() -> None:
    definition = _definition()

    assert definition.argv == ("agent-bin", "serve")

    with pytest.raises(ValueError, match="unknown fields"):
        AcpDefinition.from_mapping("agent", {"command": ["agent-bin"], "extra": True})


def test_run_rejects_cancelled_operation_before_spawn() -> None:
    from backend.app.actions.boundaries import ActionCancelledError
    operation = _operation("extension-real-capability-id")
    operation.cancel.set()
    with pytest.raises(ActionCancelledError):
        run_acp(
            _definition(),
            "summarize",
            operation,
            on_event=lambda _event: None,
            request_permission=lambda _request: None,
        )


def test_run_requires_a_subprocess_boundary() -> None:
    definition = AcpDefinition.from_mapping(
        "agent",
        {
            "command": ["agent-bin"],
            "process": {
                "subprocess": False,
                "argv_allowlist": ["agent-bin"],
                "env_passthrough": [],
                "working_root": "data",
            },
        },
    )

    with pytest.raises(BoundaryViolationError, match="subprocess process boundary"):
        run_acp(
            definition,
            "summarize",
            _operation(),
            on_event=lambda _event: None,
            request_permission=lambda _request: None,
        )


def test_run_uses_an_outbound_session_and_reports_the_final_response(monkeypatch) -> None:
    class Connection:
        async def initialize(self, *_args, **_kwargs):
            return SimpleNamespace(agent_capabilities={"prompt": True})

        async def new_session(self, *_args, **_kwargs):
            return SimpleNamespace(session_id="acp-session")

        async def prompt(self, *_args, **_kwargs):
            return SimpleNamespace(stop_reason="end_turn", model_dump=lambda **_kwargs: {"text": "done"})

        async def cancel(self, *_args, **_kwargs):
            raise AssertionError("successful prompt must not be cancelled")

    @asynccontextmanager
    async def fake_spawn(*_args, **_kwargs):
        yield Connection(), SimpleNamespace(pid=42)

    import backend.app.extensions.acp as bridge

    monkeypatch.setattr(bridge.acp, "spawn_agent_process", fake_spawn)
    monkeypatch.setattr(bridge, "_stop_process_tree", lambda _pid: None)
    events: list[dict] = []

    result = run_acp(
        _definition(),
        "summarize",
        _operation(),
        on_event=events.append,
        request_permission=lambda _request: None,
    )

    assert result == {
        "agent_id": "coding-agent",
        "session_id": "acp-session",
        "stop_reason": "end_turn",
        "output": {"text": "done"},
        "agent_capabilities": {"prompt": True},
        "pid": 42,
    }
    assert events == [{"kind": "initialized", "agent_id": "coding-agent"}]
