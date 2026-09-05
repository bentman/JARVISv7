from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest
from backend.app.actions import ActionCancelledError, ActionOperation, ExecutionBoundary, boundaries
from backend.app.extensions.acp import AcpDefinition, run_acp


def _operation() -> ActionOperation:
    return ActionOperation(
        "session-sdk", "turn-sdk", "proposal-sdk", "extension-0123456789abcdef01234567",
        ExecutionBoundary(("data",), 5_000, True, 4_000),
    )


def _definition(script: Path) -> AcpDefinition:
    return AcpDefinition.from_mapping(
        "fixture-agent",
        {
            "command": [sys.executable, str(script)],
            "process": {
                "subprocess": True,
                "argv_allowlist": [sys.executable],
                "env_passthrough": [],
                "working_root": "data",
            },
        },
    )


def _write_agent(tmp_path: Path) -> Path:
    script = tmp_path / "fixture_agent.py"
    script.write_text(
        """
import asyncio

import acp
from acp.schema import InitializeResponse, NewSessionResponse, PromptResponse


class FixtureAgent:
    def __init__(self, connection):
        self.connection = connection
        self.cancelled = asyncio.Event()

    async def initialize(self, protocol_version, **_kwargs):
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(self, **_kwargs):
        return NewSessionResponse(session_id="fixture-session")

    async def prompt(self, session_id, prompt, **_kwargs):
        text = prompt[0].text
        await self.connection.session_update(
            session_id, acp.update_agent_message_text("update:" + text)
        )
        if text == "wait":
            await self.cancelled.wait()
            return PromptResponse(stop_reason="cancelled")
        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, **_kwargs):
        self.cancelled.set()


asyncio.run(acp.run_agent(lambda connection: FixtureAgent(connection)))
""".lstrip(),
        encoding="utf-8",
    )
    return script


def _prepare_working_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    monkeypatch.setattr(boundaries, "REPO_ROOT", repo)
    return repo


def test_acp_sdk_stdio_round_trip_reports_update_and_end_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_working_root(tmp_path, monkeypatch)
    events: list[dict[str, object]] = []

    result = run_acp(
        _definition(_write_agent(tmp_path)), "hello", _operation(),
        on_event=events.append,
        request_permission=lambda _request: None,
    )

    assert result["agent_id"] == "fixture-agent"
    assert result["session_id"] == "fixture-session"
    assert result["stop_reason"] == "end_turn"
    assert result["output"]["stopReason"] == "end_turn"
    assert events[0] == {"kind": "initialized", "agent_id": "fixture-agent"}
    assert any(event["kind"] == "session_update" for event in events)


def test_acp_sdk_stdio_cancellation_stops_the_pending_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_working_root(tmp_path, monkeypatch)
    operation = _operation()
    events: list[dict[str, object]] = []
    outcome: list[BaseException] = []

    def invoke() -> None:
        try:
            run_acp(
                _definition(_write_agent(tmp_path)), "wait", operation,
                on_event=events.append,
                request_permission=lambda _request: None,
            )
        except BaseException as exc:
            outcome.append(exc)

    thread = threading.Thread(target=invoke)
    thread.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not events:
        time.sleep(0.01)
    assert events and events[0]["kind"] == "initialized"

    operation.cancel.set()
    thread.join(timeout=3)

    assert not thread.is_alive()
    assert len(outcome) == 1 and isinstance(outcome[0], ActionCancelledError)
