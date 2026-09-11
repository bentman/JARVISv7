from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest
from backend.app.actions import ActionCancelledError, ActionOperation, ExecutionBoundary, boundaries
from backend.app.actions.sessions import SessionManager
from backend.app.extensions.acp import AcpDefinition, run_acp


def _operation(timeout_ms: int = 5_000, session_id: str = "session-sdk") -> ActionOperation:
    return ActionOperation(
        session_id, "turn-sdk", "proposal-sdk", "extension-0123456789abcdef01234567",
        ExecutionBoundary(("data",), timeout_ms, True, 4_000),
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


def _write_resumable_agent(tmp_path: Path) -> Path:
    # Advertises sessionCapabilities.resume and implements resume_session, unlike
    # _write_agent's FixtureAgent - a fresh process (as if respawned after a crash)
    # always creates session id "resumable-session" and answers resume_session for it,
    # so a test can prove run_acp actually calls resume rather than always starting new.
    #
    # Conversation history is persisted to a file in the process's own cwd (the same
    # working_directory the test controls via _prepare_working_root) and reloaded on
    # resume_session, rather than kept only in memory - a resumed-but-empty session
    # would prove the resume call happened without proving any conversation content
    # actually came back. resume_session also sends a session_update before returning,
    # the same way a real agent might report recovered state mid-resume - this is what
    # exercises the client callbacks being bound before open_session, not only before
    # send_prompt: an unbound client raises TypeError on this message instead of
    # delivering it.
    script = tmp_path / "resumable_fixture_agent.py"
    script.write_text(
        """
import asyncio
from pathlib import Path

import acp
from acp.schema import (
    AgentCapabilities,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    ResumeSessionResponse,
    SessionCapabilities,
    SessionResumeCapabilities,
)

HISTORY_FILE = Path("resumable_history.txt")


class ResumableFixtureAgent:
    def __init__(self, connection):
        self.connection = connection
        self.history = HISTORY_FILE.read_text(encoding="utf-8").splitlines() if HISTORY_FILE.exists() else []

    async def initialize(self, protocol_version, **_kwargs):
        return InitializeResponse(
            protocol_version=protocol_version,
            agent_capabilities=AgentCapabilities(
                session_capabilities=SessionCapabilities(resume=SessionResumeCapabilities()),
            ),
        )

    async def new_session(self, **_kwargs):
        return NewSessionResponse(session_id="resumable-session")

    async def resume_session(self, session_id, **_kwargs):
        await self.connection.session_update(
            session_id, acp.update_agent_message_text("recovered:" + ",".join(self.history))
        )
        return ResumeSessionResponse()

    async def prompt(self, session_id, prompt, **_kwargs):
        self.history.append(prompt[0].text)
        HISTORY_FILE.write_text("\\n".join(self.history), encoding="utf-8")
        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, **_kwargs):
        pass


asyncio.run(acp.run_agent(lambda connection: ResumableFixtureAgent(connection), use_unstable_protocol=True))
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
    sessions = SessionManager()

    result = run_acp(
        sessions, _definition(_write_agent(tmp_path)), "hello", _operation(),
        on_event=events.append,
        request_permission=lambda _request: None,
    )
    sessions.close_all()

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
    sessions = SessionManager()

    def invoke() -> None:
        try:
            run_acp(
                sessions, _definition(_write_agent(tmp_path)), "wait", operation,
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
    sessions.close_all()

    assert not thread.is_alive()
    assert len(outcome) == 1 and isinstance(outcome[0], ActionCancelledError)


def test_acp_sdk_reuses_the_spawned_process_across_repeated_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ADR 0005's shared session-lifecycle mechanism attaches here: a second prompt
    # against the same agent must reuse the process and session the first one opened,
    # not spawn a fresh agent and session per prompt - the defect the mechanism exists
    # to close, mirrored from MCP's own reuse test.
    _prepare_working_root(tmp_path, monkeypatch)
    sessions = SessionManager()
    definition = _definition(_write_agent(tmp_path))
    connection_id = f"acp:{definition.agent_id}:session-sdk"  # matches _operation()'s session_id

    assert sessions.is_open(connection_id) is False

    first = run_acp(
        sessions, definition, "hello", _operation(),
        on_event=lambda _event: None, request_permission=lambda _request: None,
    )
    assert sessions.is_open(connection_id) is True, (
        "the connection must stay open after a prompt completes, not close in a finally block"
    )

    second = run_acp(
        sessions, definition, "hello again", _operation(),
        on_event=lambda _event: None, request_permission=lambda _request: None,
    )
    assert second["session_id"] == first["session_id"], (
        "a second prompt must reuse the same session, not open a fresh one"
    )
    assert second["pid"] == first["pid"], (
        "a second prompt must reuse the same spawned agent process, not a new one"
    )

    sessions.close(connection_id)
    assert sessions.is_open(connection_id) is False


def test_acp_sdk_isolates_separate_host_conversations_against_the_same_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Connection identity is namespaced by host conversation (operation.session_id), not
    # only by agent, so two different conversations invoking the same agent definition
    # get their own process and session rather than sharing one - confirmed as a real
    # defect before this fix: with two different session_id values, a real subprocess
    # returned the first conversation's content in response to the second's prompt.
    _prepare_working_root(tmp_path, monkeypatch)
    sessions = SessionManager()
    definition = _definition(_write_resumable_agent(tmp_path))

    conversation_one = run_acp(
        sessions, definition, "hello from conversation one", _operation(session_id="conv-1"),
        on_event=lambda _event: None, request_permission=lambda _request: None,
    )
    conversation_two = run_acp(
        sessions, definition, "hello from conversation two", _operation(session_id="conv-2"),
        on_event=lambda _event: None, request_permission=lambda _request: None,
    )

    assert conversation_one["pid"] != conversation_two["pid"], (
        "two different host conversations against the same agent must spawn separate "
        "processes, not share one - sharing one means sharing the agent's own conversation state"
    )
    assert sessions.is_open(f"acp:{definition.agent_id}:conv-1") is True
    assert sessions.is_open(f"acp:{definition.agent_id}:conv-2") is True

    # A second prompt within conversation one must still reuse conversation one's own
    # process (the existing reuse guarantee), not conversation two's.
    conversation_one_again = run_acp(
        sessions, definition, "hello again from conversation one", _operation(session_id="conv-1"),
        on_event=lambda _event: None, request_permission=lambda _request: None,
    )
    assert conversation_one_again["pid"] == conversation_one["pid"]

    sessions.close_all()


def test_acp_sdk_routes_a_reused_connections_events_to_the_call_that_sent_the_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The connection (and its ACP client object) is opened once and reused, but each
    # call passes its own on_event/request_permission. A session_update the agent sends
    # while handling the second prompt must reach the second call's collector, not the
    # first call's - the callback-capture bug a reused connection can otherwise reintroduce.
    _prepare_working_root(tmp_path, monkeypatch)
    sessions = SessionManager()
    definition = _definition(_write_agent(tmp_path))

    first_events: list[dict[str, object]] = []
    run_acp(
        sessions, definition, "hello", _operation(),
        on_event=first_events.append, request_permission=lambda _request: None,
    )

    second_events: list[dict[str, object]] = []
    run_acp(
        sessions, definition, "hello again", _operation(),
        on_event=second_events.append, request_permission=lambda _request: None,
    )

    sessions.close_all()

    first_updates = [e for e in first_events if e["kind"] == "session_update"]
    second_updates = [e for e in second_events if e["kind"] == "session_update"]
    assert len(first_updates) == 1 and first_updates[0]["update"]["content"]["text"] == "update:hello", (
        "the first call's own update must reach its own collector"
    )
    assert len(second_updates) == 1 and second_updates[0]["update"]["content"]["text"] == "update:hello again", (
        "the second call's update must reach the second call's collector, not the first's"
    )


def test_acp_sdk_a_prompt_against_a_killed_agent_process_evicts_the_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ADR 0005 Follow-up: ACP has no equivalent to MCP's discover-triggered eviction, so
    # a killed agent process would otherwise wedge the connection - every later prompt
    # would keep retrying against the same dead connection forever. Confirmed
    # empirically before writing this: killing the spawned agent process externally and
    # then prompting the same (reused) session raises a plain
    # `ConnectionError("Connection closed")` from the ACP SDK's own transport.
    import psutil

    _prepare_working_root(tmp_path, monkeypatch)
    sessions = SessionManager()
    definition = _definition(_write_agent(tmp_path))
    connection_id = f"acp:{definition.agent_id}:session-sdk"  # matches _operation()'s session_id

    # This test spawns three real processes in sequence (open, respawn-after-kill,
    # reopen-again) - a generous timeout keeps it from flaking under system load
    # rather than reflecting anything the mechanism itself needs to be fast at.
    first = run_acp(
        sessions, definition, "hello", _operation(timeout_ms=20_000),
        on_event=lambda _event: None, request_permission=lambda _request: None,
    )
    assert sessions.is_open(connection_id) is True
    pid = first["pid"]

    psutil.Process(pid).kill()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and psutil.pid_exists(pid):
        time.sleep(0.05)
    assert not psutil.pid_exists(pid)

    from backend.app.actions.sessions import SessionResourceDiedError

    with pytest.raises(SessionResourceDiedError):
        run_acp(
            sessions, definition, "hello again", _operation(timeout_ms=20_000),
            on_event=lambda _event: None, request_permission=lambda _request: None,
        )
    assert sessions.is_open(connection_id) is False, (
        "a prompt against a killed process must evict the connection, not leave it "
        "registered as open for the next prompt to wedge against again"
    )

    # The next prompt must reopen a genuinely fresh connection and succeed.
    second = run_acp(
        sessions, definition, "hello once more", _operation(timeout_ms=20_000),
        on_event=lambda _event: None, request_permission=lambda _request: None,
    )
    assert second["pid"] != pid
    sessions.close_all()


def test_acp_sdk_resumes_the_prior_session_after_the_process_is_killed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ADR 0005 Follow-up: session/resume closes the conversation-continuity gap left
    # after a connection is evicted and reopened - the mechanism only guarantees a fresh
    # connection is reachable, not that a specific prior session survives on it, and it
    # is this adapter's job to actually call session/resume, not just make it reachable.
    # This agent advertises sessionCapabilities.resume and answers resume_session, unlike
    # test_acp_sdk_a_prompt_against_a_killed_agent_process_evicts_the_connection's plain
    # FixtureAgent, which does neither - that test proves eviction; this one proves what
    # happens on the reopened connection afterward.
    import psutil

    _prepare_working_root(tmp_path, monkeypatch)
    sessions = SessionManager()
    definition = _definition(_write_resumable_agent(tmp_path))
    connection_id = f"acp:{definition.agent_id}:session-sdk"  # matches _operation()'s session_id

    remembered: dict[str, str] = {}

    def get_resumable_session_id() -> str | None:
        return remembered.get(connection_id)

    def remember_session_id(session_id: str) -> None:
        remembered[connection_id] = session_id

    # As above: three real process spawns in sequence, so a generous timeout keeps this
    # from flaking under system load rather than reflecting a real responsiveness need.
    first_events: list[dict[str, object]] = []
    first = run_acp(
        sessions, definition, "hello", _operation(timeout_ms=20_000),
        on_event=first_events.append, request_permission=lambda _request: None,
        get_resumable_session_id=get_resumable_session_id, remember_session_id=remember_session_id,
    )
    assert first["session_id"] == "resumable-session"
    assert remembered[connection_id] == "resumable-session"
    assert not any(event["kind"] == "resumed" for event in first_events), (
        "the very first open has nothing to resume - it must start a fresh session"
    )

    pid = first["pid"]
    psutil.Process(pid).kill()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and psutil.pid_exists(pid):
        time.sleep(0.05)
    assert not psutil.pid_exists(pid)

    from backend.app.actions.sessions import SessionResourceDiedError

    with pytest.raises(SessionResourceDiedError):
        run_acp(
            sessions, definition, "hello again", _operation(timeout_ms=20_000),
            on_event=lambda _event: None, request_permission=lambda _request: None,
            get_resumable_session_id=get_resumable_session_id, remember_session_id=remember_session_id,
        )
    assert sessions.is_open(connection_id) is False

    second_events: list[dict[str, object]] = []
    second = run_acp(
        sessions, definition, "hello once more", _operation(timeout_ms=20_000),
        on_event=second_events.append, request_permission=lambda _request: None,
        get_resumable_session_id=get_resumable_session_id, remember_session_id=remember_session_id,
    )

    assert second["pid"] != pid, "the reopened connection must spawn a genuinely new process"
    assert second["session_id"] == "resumable-session", (
        "the reopened connection must resume the same session id, not start a new one"
    )
    resumed_events = [e for e in second_events if e["kind"] == "resumed"]
    assert resumed_events == [{"kind": "resumed", "agent_id": "fixture-agent", "session_id": "resumable-session"}], (
        "the adapter must actually call session/resume against the freshly spawned "
        "process, not merely reuse the old session id label without asking the agent"
    )

    # The agent sends a session_update during resume_session itself (before send_prompt
    # ever runs) carrying content it recovered from the conversation history it
    # persisted before being killed - this is what proves real conversation content
    # came back, not merely a coincidentally-matching session id label, and it is also
    # what exercises the client callbacks being bound before open_session runs rather
    # than only before send_prompt: an unbound client would raise TypeError delivering
    # this exact message instead of it appearing here.
    session_updates = [e for e in second_events if e["kind"] == "session_update"]
    assert session_updates, "resume_session's own update must reach the caller, not crash or be silently dropped"
    recovered_text = session_updates[0]["update"]["content"]["text"]
    assert recovered_text == "recovered:hello", (
        "the resumed session must recover the actual conversation content the first "
        "prompt produced before the process was killed, not start from nothing"
    )

    sessions.close_all()
