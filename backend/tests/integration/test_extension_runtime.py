from __future__ import annotations

import asyncio
import contextlib
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from backend.app.actions import ActionOperation, ExecutionBoundary, boundaries
from backend.app.actions.catalog import CapabilityObservation
from backend.app.api.routes.extensions import ExtensionInput, answer_extension_input
from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.extensions.discovery import definitions_directory
from backend.app.extensions.plugins import PluginInstaller
from backend.app.services.capability_service import CapabilityService, CapabilityServiceError
from backend.app.services.extension_runtime_service import ExtensionRuntimeService
from fastapi import HTTPException


def _runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ExtensionRuntimeService:
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    monkeypatch.setattr(boundaries, "REPO_ROOT", repo)
    config = tmp_path / "config"
    data = repo / "data"
    actions = CapabilityService(observe=lambda: CapabilityObservation(extension_catalog_present=True))
    return ExtensionRuntimeService(
        actions, config_dir=config, data_dir=data, db_path=data / "operator.sqlite"
    )


def _write_tool_definition(root: Path, tool_id: str = "writer") -> None:
    directory = root / "extensions" / "tools"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{tool_id}.yaml").write_text(
        "\n".join(
            [
                f"id: {tool_id}",
                "name: Test writer",
                "version: '1'",
                "definition:",
                "  command:",
                f"    - {sys.executable}",
                "    - -c",
                "    - \"from pathlib import Path; Path('marker.txt').write_text('ran')\"",
                "  process:",
                "    subprocess: true",
                "    argv_allowlist:",
                f"      - {sys.executable}",
                "    env_passthrough: []",
                "    working_root: data",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _operation_id(runtime: ExtensionRuntimeService, extension_id: str) -> str:
    operations = runtime.detail(extension_id)["operations"]
    assert len(operations) == 1
    return operations[0]["capability_id"]


def test_operator_invocation_executes_directly_without_a_second_approval_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Operator invocation (ExtensionRuntimeService.invoke, reached from
    # POST /extensions/{id}/invoke - the Extensions panel's own dedicated Invoke
    # control) is the operator's own fully-specified request: it must execute
    # immediately even for a privileged_execution capability, not park for a second,
    # separate approval decision on a request the operator already made by invoking it.
    # A *model*-proposed call against the same capability during a live conversation
    # turn is a different call site entirely (conversation/engine.py's own
    # proposed_by="model" propose(...) call) and still parks - see
    # test_a_model_proposed_tool_call_still_requires_a_separate_approval below.
    runtime = _runtime(tmp_path, monkeypatch)
    _write_tool_definition(runtime.config_dir)
    capability_id = _operation_id(runtime, "tool:writer")

    runtime.overlay.set_state(extension_id="tool:writer", state="disabled", expected_revision=None)
    denied = runtime.invoke("tool:writer", capability_id, {})
    assert denied.status == "denied"
    runtime.overlay.set_state(extension_id="tool:writer", state="enabled", expected_revision=1)

    executed = runtime.invoke("tool:writer", capability_id, {})

    assert executed.status == "success", executed
    assert (runtime.data_dir / "marker.txt").read_text(encoding="utf-8") == "ran"
    run = runtime.runs.list()[0]
    assert run["extension_id"] == "tool:writer"
    assert run["status"] == "success"
    assert executed.execution["result"]["output"]["exit_code"] == 0


def test_a_model_proposed_tool_call_still_requires_a_separate_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Unlike the operator's own direct Invoke above, a model proposal - the same
    # proposed_by="model" propose(...) call conversation/engine.py makes during a live
    # turn - has not been reviewed by the operator for this specific instance, so it
    # must still park and be explicitly denied or approved.
    runtime = _runtime(tmp_path, monkeypatch)
    _write_tool_definition(runtime.config_dir)
    capability_id = _operation_id(runtime, "tool:writer")

    proposed = runtime.actions.propose(
        capability_id=capability_id, arguments={}, proposed_by="model", reason="model requested it",
    )
    assert proposed.status == "awaiting_approval"
    assert not (runtime.data_dir / "marker.txt").exists()

    denied = runtime.actions.decide(
        proposal_id=proposed.proposal_id, outcome="denied", decided_by="operator"
    )

    assert denied.status == "denied"
    assert not (runtime.data_dir / "marker.txt").exists()
    assert runtime.runs.list() == []


def test_approval_refuses_a_tool_definition_changed_while_parked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    _write_tool_definition(runtime.config_dir)
    capability_id = _operation_id(runtime, "tool:writer")
    proposed = runtime.actions.propose(
        capability_id=capability_id, arguments={}, proposed_by="model", reason="model requested it",
    )
    definition = runtime.config_dir / "extensions" / "tools" / "writer.yaml"
    definition.write_text(
        definition.read_text(encoding="utf-8").replace("'ran'", "'changed'"), encoding="utf-8"
    )

    try:
        decision = runtime.actions.decide(
            proposal_id=proposed.proposal_id, outcome="approved", decided_by="operator"
        )
    except CapabilityServiceError:
        decision = None

    assert decision is None or decision.status != "success"
    assert not (runtime.data_dir / "marker.txt").exists()


def test_installed_plugin_child_is_discovered_by_the_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    plugins = runtime.config_dir / "extensions" / "plugins"
    bundle = plugins / "writer-bundle"
    _write_tool_definition(bundle, "plugin-writer")
    (plugins / "writer-plugin.yaml").write_text(
        """
id: writer-plugin
name: Writer plugin
version: '1'
definition:
  source: writer-bundle
  extensions:
    - family: tool
      id: plugin-writer
      path: extensions/tools/plugin-writer.yaml
""",
        encoding="utf-8",
    )
    plugin = next(item for item in runtime.definitions() if item.family == "plugin")
    PluginInstaller(runtime.config_dir, runtime.data_dir).install(
        plugin,
        ActionOperation(
            "session", "turn", "proposal", "plugin-install",
            ExecutionBoundary(("data",), 2_000, True, 10_000),
        ),
    )

    assert any(
        item.family == "tool" and item.local_id == "plugin-writer" for item in runtime.definitions()
    )


def _acp_engine(runtime: ExtensionRuntimeService, tmp_path: Path) -> tuple[TurnEngine, SessionManager]:
    manager = SessionManager(
        turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions"
    )
    engine = TurnEngine(
        stt=SimpleNamespace(), tts=SimpleNamespace(), llm=SimpleNamespace(),
        personality=SimpleNamespace(profile_id="integration"), session_manager=manager,
        extension_runtime=runtime,
    )
    runtime.session_executor = engine.run_extension
    return engine, manager


def _write_acp_definition(root: Path) -> None:
    directory = root / "extensions" / "acp"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent.yaml").write_text(
        """
id: agent
name: Agent
version: '1'
definition:
  command: [agent-bin, serve]
  process:
    subprocess: true
    argv_allowlist: [agent-bin]
    env_passthrough: []
    working_root: data
""",
        encoding="utf-8",
    )


def test_acp_run_uses_turn_admission_and_persists_a_delegated_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    _write_acp_definition(runtime.config_dir)
    _engine, manager = _acp_engine(runtime, tmp_path)

    import backend.app.extensions.acp as acp

    monkeypatch.setattr(
        acp,
        "run_acp",
        lambda _session_manager, definition, prompt, operation, **_kwargs: {
            "agent_id": definition.agent_id, "prompt": prompt, "operation_turn": operation.turn_id
        },
    )
    # Operator invocation now executes directly - no separate approval decision to make.
    executed = runtime.invoke("acp:agent", _operation_id(runtime, "acp:agent"), {"prompt": "summarize"})

    assert executed.status == "success"
    artifact = manager.turn_artifacts[-1]
    assert artifact.transcript == "summarize"
    assert artifact.tools_invoked == [executed.capability_id]
    assert artifact.delegated_runs[0]["extension_id"] == "acp:agent"


def test_cancelled_acp_input_returns_conflict_from_the_input_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    _write_acp_definition(runtime.config_dir)
    _engine, _manager = _acp_engine(runtime, tmp_path)
    import backend.app.extensions.acp as acp

    def wait_for_permission(_session_manager, _definition, _prompt, _operation, *, request_permission, **_kwargs):
        return request_permission({"message": "approve tool?"})

    monkeypatch.setattr(acp, "run_acp", wait_for_permission)
    # Operator invocation now executes directly rather than parking first, so it is the
    # call that blocks on the permission request - run it on its own thread the same way
    # the separate approval decision used to be threaded.
    capability_id = _operation_id(runtime, "acp:agent")
    completed: list[object] = []
    thread = threading.Thread(
        target=lambda: completed.append(
            runtime.invoke("acp:agent", capability_id, {"prompt": "work"})
        ),
    )
    thread.start()
    deadline = time.monotonic() + 2
    run = None
    while time.monotonic() < deadline:
        runs = runtime.runs.list()
        if runs and runs[0]["status"] == "awaiting_input":
            run = runs[0]
            break
        time.sleep(0.01)
    assert run is not None

    assert runtime.actions.cancel(run["proposal_id"]) is True
    thread.join(timeout=2)
    assert not thread.is_alive()
    with pytest.raises(HTTPException) as response:
        answer_extension_input(
            run["run_id"], ExtensionInput(request_id=run["request"]["request_id"], answer={"action": "accept"}), runtime
        )

    assert response.value.status_code == 409


def _write_mcp_definition(root: Path, server: Path) -> None:
    directory = root / "extensions" / "mcp"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "fixture.yaml").write_text(
        "\n".join([
            "id: fixture",
            "name: Fixture MCP",
            "version: '1'",
            "definition:",
            "  transport: stdio",
            f"  command: ['{sys.executable}', '{server}']",
            "  process:",
            "    subprocess: true",
            f"    argv_allowlist: ['{sys.executable}']",
            "    env_passthrough: []",
            "    working_root: data",
            "  tool_allowlist: ['echo']",
        ]),
        encoding="utf-8",
    )


def _mcp_server_script(tmp_path: Path) -> Path:
    server = tmp_path / "snapshot_server.py"
    server.write_text(
        "from mcp.server import MCPServer\n"
        "mcp = MCPServer('fixture')\n"
        "@mcp.tool()\n"
        "def echo(value: str) -> str:\n"
        "    return value\n"
        "if __name__ == '__main__':\n"
        "    mcp.run()\n",
        encoding="utf-8",
    )
    return server


def _stubborn_mcp_server_script(tmp_path: Path) -> Path:
    # A server that ignores SIGTERM and never exits on its own once its stdin closes -
    # unlike a fixture that merely sleeps a fixed delay before exiting naturally, which
    # cannot tell a real forceful kill apart from just waiting long enough: that version
    # passed identically whether or not the SDK's kill escalation ever actually ran,
    # because the process died on its own timeline regardless (confirmed directly - a
    # test built on it kept passing even with the fix disabled). With this fixture, the
    # only way the process can die within the test's short poll window is a real
    # SIGKILL/Job-Object hard-kill reaching it - a graceful stdin-close alone cannot do it.
    server = tmp_path / "stubborn_server.py"
    server.write_text(
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "from mcp.server import MCPServer\n"
        "mcp = MCPServer('fixture')\n"
        "@mcp.tool()\n"
        "def echo(value: str) -> str:\n"
        "    return value\n"
        "if __name__ == '__main__':\n"
        "    mcp.run()\n"
        "    time.sleep(300)\n",
        encoding="utf-8",
    )
    return server


def test_discovered_mcp_operations_survive_a_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    _write_mcp_definition(runtime.data_dir, _mcp_server_script(tmp_path))
    runtime.actions.refresh()

    discover = next(
        item for item in runtime.detail("mcp:fixture")["operations"] if item["name"] == "discover"
    )
    # Discovery is a read - it never mutates anything - so it executes directly without a
    # separate approval step, on stdio the same as on streamable_http; only a stdio tool call
    # (running an arbitrary local program) remains approval-gated.
    proposed = runtime.invoke("mcp:fixture", discover["capability_id"], {})
    assert proposed.status == "success", proposed

    before = {item["name"] for item in runtime.detail("mcp:fixture")["operations"]}
    assert "tool:echo" in before

    # A new service instance is what an operator gets after a backend restart.
    restarted = ExtensionRuntimeService(
        CapabilityService(observe=lambda: CapabilityObservation(extension_catalog_present=True)),
        config_dir=runtime.config_dir,
        data_dir=runtime.data_dir,
        db_path=runtime.data_dir / "operator.sqlite",
    )
    restarted.actions.refresh()
    detail = restarted.detail("mcp:fixture")
    assert {item["name"] for item in detail["operations"]} == before
    # The connection has not been contacted since restart, so health is not asserted.
    assert detail["snapshot"]["health"] == "unknown"


def test_a_stdio_tool_call_invoked_by_the_operator_executes_directly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stdio tool call runs an arbitrary local program - an operator's own request
    # through the dedicated Invoke path is already fully specified, so it executes
    # directly the same way discover already does. A *model*-proposed call against the
    # same capability during a live conversation turn still parks - see
    # test_a_model_proposed_stdio_tool_call_still_requires_approval below.
    runtime = _runtime(tmp_path, monkeypatch)
    _write_mcp_definition(runtime.data_dir, _mcp_server_script(tmp_path))
    runtime.actions.refresh()
    discover = next(
        item for item in runtime.detail("mcp:fixture")["operations"] if item["name"] == "discover"
    )
    assert runtime.invoke("mcp:fixture", discover["capability_id"], {}).status == "success"

    tool = next(
        item for item in runtime.detail("mcp:fixture")["operations"] if item["name"] == "tool:echo"
    )
    executed = runtime.invoke("mcp:fixture", tool["capability_id"], {"value": "hi"})
    assert executed.status == "success", executed


def test_a_model_proposed_stdio_tool_call_still_requires_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stdio tool call runs an arbitrary local program with model-supplied arguments - a
    # materially different risk from a read-only discover on the same connection - so a
    # model proposal against it (conversation/engine.py's own proposed_by="model"
    # propose(...) call) still parks for a separate operator decision, unlike the
    # operator's own direct Invoke above.
    runtime = _runtime(tmp_path, monkeypatch)
    _write_mcp_definition(runtime.data_dir, _mcp_server_script(tmp_path))
    runtime.actions.refresh()
    discover = next(
        item for item in runtime.detail("mcp:fixture")["operations"] if item["name"] == "discover"
    )
    assert runtime.invoke("mcp:fixture", discover["capability_id"], {}).status == "success"

    tool = next(
        item for item in runtime.detail("mcp:fixture")["operations"] if item["name"] == "tool:echo"
    )
    proposed = runtime.actions.propose(
        capability_id=tool["capability_id"], arguments={"value": "hi"},
        proposed_by="model", reason="model requested it",
    )
    assert proposed.status == "awaiting_approval", proposed

    approved = runtime.actions.decide(
        proposal_id=proposed.proposal_id, outcome="approved", decided_by="operator"
    )
    assert approved.status == "success", approved


@pytest.mark.parametrize("transport", ["stdio", "streamable_http"])
def test_mcp_tool_hints_classify_effects_without_authorizing_model_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transport: str
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    if transport == "stdio":
        _write_mcp_definition(runtime.data_dir, _mcp_server_script(tmp_path))
    else:
        runtime.write_definition("mcp", "fixture", {
            "name": "Fixture", "version": "1",
            "definition": {"transport": transport, "url": "https://mcp.example.test/mcp"},
        })
    fallback = "privileged_execution" if transport == "stdio" else "external_write"
    cases = [
        ({}, fallback),
        ({"readOnlyHint": True}, "external_read"),
        ({"readOnlyHint": "true"}, fallback),
        ({"destructiveHint": True}, "destructive_action"),
        ({"readOnlyHint": True, "destructiveHint": True}, "destructive_action"),
        ("invalid", fallback),
    ]
    runtime._snapshots["mcp:fixture"] = {"tools": [
        {"name": f"tool{index}", "inputSchema": {"type": "object"}, "annotations": hints}
        for index, (hints, _) in enumerate(cases)
    ]}
    calls = []
    monkeypatch.setattr(runtime, "_mcp", lambda manifest, name, arguments, operation, run_id:
                        calls.append(name) or {"content": {"content": [{"type": "text", "text": "done"}]}, "trusted": False})
    operations = runtime.detail("mcp:fixture")["operations"]
    for index, (_, expected) in enumerate(cases):
        tool = next(item for item in operations if item["name"] == f"tool:tool{index}")
        assert tool["effect_class"] == expected
        assert tool["authorization_rule"] == "requires_approval"
        proposed = runtime.actions.propose(
            capability_id=tool["capability_id"], arguments={}, proposed_by="model", reason="test",
        )
        assert proposed.status == "awaiting_approval"
        assert len(calls) == index
        runtime.actions.decide(proposal_id=proposed.proposal_id, outcome="denied", decided_by="operator")
        assert runtime.invoke("mcp:fixture", tool["capability_id"], {"token": "private", "query": "weather"}).status == "success"
        run = runtime.runs.list()[0]
        assert run["operation"] == tool["name"]
        assert run["extension_name"]
        assert run["arguments"]["query"] == "weather"
        assert run["arguments"]["token"] != "private"


def test_a_stdio_connection_stays_open_across_calls_instead_of_one_process_per_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ADR 0005's shared session-lifecycle mechanism attaches here: a second discover
    # against the same connection must reuse the process the first one opened, not spawn
    # a fresh one and tear it down - the defect the mechanism exists to close.
    runtime = _runtime(tmp_path, monkeypatch)
    _write_mcp_definition(runtime.data_dir, _mcp_server_script(tmp_path))
    runtime.actions.refresh()
    identifier = "mcp:fixture"

    assert runtime._sessions.is_open(identifier) is False

    discover = next(
        item for item in runtime.detail(identifier)["operations"] if item["name"] == "discover"
    )
    assert runtime.invoke(identifier, discover["capability_id"], {}).status == "success"
    assert runtime._sessions.is_open(identifier) is True, (
        "the connection must stay open after a call completes, not close in a finally block"
    )
    resource_after_first_call = runtime._sessions._connections[identifier].resource

    assert runtime.invoke(identifier, discover["capability_id"], {}).status == "success"
    resource_after_second_call = runtime._sessions._connections[identifier].resource
    assert resource_after_second_call is resource_after_first_call, (
        "a second call must reuse the same open connection, not open a new process"
    )

    runtime._sessions.close(identifier)
    assert runtime._sessions.is_open(identifier) is False


def test_closing_a_stdio_mcp_connection_actually_kills_the_spawned_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # End-to-end confirmation against a real OS process, not just that our own Python
    # objects were dereferenced: close()/terminate() for MCP both resolve to
    # McpSdkPeer.aclose(), which exits the SDK's own Client context manager - for a
    # stdio connection this runs the SDK's stdio_client shutdown (close stdin, wait,
    # SIGTERM the process tree, SIGKILL if it is still alive). This test exercises the
    # graceful-close path specifically (a well-behaved fixture server exits promptly on
    # stdin close, well within the default drain window) - it does not by itself isolate
    # SessionManager awaiting terminate() rather than firing it and moving on, since the
    # background loop stays alive regardless and would eventually finish an abandoned
    # task too; that specific guarantee is proven at the mechanism level instead, in
    # backend/tests/unit/actions/test_sessions.py::test_close_awaits_terminate_to_completion_instead_of_firing_and_forgetting.
    import psutil

    runtime = _runtime(tmp_path, monkeypatch)
    _write_mcp_definition(runtime.data_dir, _mcp_server_script(tmp_path))
    runtime.actions.refresh()
    identifier = "mcp:fixture"

    this_process = psutil.Process()
    children_before = {child.pid for child in this_process.children(recursive=True)}

    discover = next(
        item for item in runtime.detail(identifier)["operations"] if item["name"] == "discover"
    )
    assert runtime.invoke(identifier, discover["capability_id"], {}).status == "success"

    children_after_open = {child.pid for child in this_process.children(recursive=True)}
    spawned = children_after_open - children_before
    assert spawned, "discover must have actually spawned the MCP server subprocess"

    runtime._sessions.close(identifier)

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not any(psutil.pid_exists(pid) for pid in spawned):
            break
        time.sleep(0.05)
    still_alive = [pid for pid in spawned if psutil.pid_exists(pid)]
    assert not still_alive, f"close() must actually kill the spawned MCP server process(es): {still_alive} still alive"


def test_disconnecting_a_slow_to_exit_mcp_server_waits_for_real_process_death(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A real MCP server that never exits on its own (ignores SIGTERM, sleeps far past
    # this test's own timeout) is what actually exercises the two-phase close/terminate
    # path and proves a forceful kill, not just a graceful signal, reached the process -
    # an earlier version of this fixture merely slept a fixed few seconds before exiting
    # naturally, which could not tell a real kill apart from just waiting long enough:
    # that version kept passing identically with the fix disabled, because the process
    # died on its own timeline regardless of what disconnect() actually did (confirmed
    # directly). The fixture server in
    # test_closing_a_stdio_mcp_connection_actually_kills_the_spawned_process exits
    # promptly on graceful stdin-close and so never exercises this path at all.
    #
    # McpConnectionRuntime.close() used to clear self._peer before the underlying
    # peer.aclose() actually finished, so a second call (the terminate fallback, once
    # the first graceful attempt's own wait gave up) found nothing left to close and
    # returned immediately having done nothing - disconnect() would report success
    # while the real process kept running, undetected, forever (an abandoned background
    # task once the loop that was supposed to finish it later stopped, rather than a
    # process that just needed a normal few hundred milliseconds for the OS to finish
    # reaping it - the two are not the same failure, and only the first is fixable
    # here). Checked with a short, bounded confirmation window rather than instantly:
    # McpSdkPeer exposes no subprocess handle, so this family has no way to directly
    # verify death (unlike ACP's PID-based `_stop_process_tree`, which explicitly polls
    # `psutil.wait_procs` for the same reason) - the SDK's own kill escalation runs
    # before disconnect() returns, but a brief OS-level reaping race between that and
    # `psutil.pid_exists` observing it is a real, disclosed limit of this family, not
    # something this mechanism can eliminate without that handle.
    import psutil

    runtime = _runtime(tmp_path, monkeypatch)
    _write_mcp_definition(runtime.data_dir, _stubborn_mcp_server_script(tmp_path))
    runtime.actions.refresh()
    identifier = "mcp:fixture"

    this_process = psutil.Process()
    children_before = {child.pid for child in this_process.children(recursive=True)}
    discover = next(
        item for item in runtime.detail(identifier)["operations"] if item["name"] == "discover"
    )
    assert runtime.invoke(identifier, discover["capability_id"], {}).status == "success"
    spawned = {child.pid for child in this_process.children(recursive=True)} - children_before
    assert spawned, "discover must have actually spawned the MCP server subprocess"

    result = runtime.disconnect(identifier)
    assert result == {"extension_id": identifier, "connected": False}

    # Immediately followed by full backend shutdown (stops the session loop and joins
    # its thread) is what actually distinguishes the fix from the original bug: with a
    # background loop left running, a stray, still-in-flight kill task from a buggy
    # disconnect() would eventually finish anyway given enough idle time, masking the
    # defect - checking only after a bounded wait on a still-running loop does not
    # reproduce what the reviewer actually observed ("processes remained alive after
    # backend shutdown"). disconnect() popping this connection already removes it from
    # close_all()'s own tracking, so shutdown() cannot itself retry or wait on it - if
    # disconnect() returned while a kill was still only quietly running in the
    # background, stopping the loop right after must abandon it.
    runtime.close()

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and any(psutil.pid_exists(pid) for pid in spawned):
        time.sleep(0.05)
    still_alive = [pid for pid in spawned if psutil.pid_exists(pid)]
    assert not still_alive, (
        f"disconnect() must not return while a kill attempt against a slow-to-exit "
        f"server is still only running quietly in the background - an immediately "
        f"following backend shutdown must not be able to abandon it and leave the "
        f"process alive: {still_alive} still alive"
    )


def test_disabling_an_mcp_extension_closes_its_open_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # extension_service.py's set_state only ever wrote the overlay - it had no
    # lifecycle-teardown hook, so a still-open MCP connection (and its live subprocess)
    # kept serving calls after an operator disabled the extension, undetected, since
    # nothing about the overlay write itself touches SessionManager. A first fix wired
    # teardown into build_extension_handlers's `set_state` capability handler only -
    # which missed that `POST /extensions/{id}/state` (backend/app/api/routes/extensions.py's
    # set_extension_state) calls `service.set_state(...)` directly as its own
    # execute_operator_action callback, never reaching that handler at all, so the
    # originally reported route reproduction still applied to it (disabled, connection
    # open, process alive) even after that first fix. Teardown now lives inside
    # ExtensionService.set_state itself (its own `session_closer`, wired once in
    # backend/app/api/app.py from `extension_runtime.close_session`), which both the
    # capability handler and the operator route call into - proven here against both,
    # not just the one that happened to be fixed first.
    import psutil
    from backend.app.actions import catalog
    from backend.app.api.routes.extensions import set_extension_state
    from backend.app.api.schemas.extensions import ExtensionStateRequest
    from backend.app.extensions.catalog import ExtensionObservation
    from backend.app.services.capability_service import build_extension_handlers
    from backend.app.services.extension_service import ExtensionService

    runtime = _runtime(tmp_path, monkeypatch)
    _write_mcp_definition(runtime.data_dir, _mcp_server_script(tmp_path))
    runtime.actions.refresh()
    identifier = "mcp:fixture"

    # Same overlay store the runtime itself reads/writes, the way production's
    # extension_service and extension_runtime share one - a separate store would let
    # this test pass without the disable ever being visible to the runtime at all.
    extension_service = ExtensionService(
        observe=lambda: ExtensionObservation(definitions=tuple(runtime.definitions())),
        store=runtime.overlay,
        config_dir=runtime.config_dir,
        data_dir=runtime.data_dir,
        session_closer=runtime.close_session,
    )

    def discover_and_spawn() -> set[int]:
        this_process = psutil.Process()
        children_before = {child.pid for child in this_process.children(recursive=True)}
        discover = next(
            item for item in runtime.detail(identifier)["operations"] if item["name"] == "discover"
        )
        assert runtime.invoke(identifier, discover["capability_id"], {}).status == "success"
        spawned = {child.pid for child in this_process.children(recursive=True)} - children_before
        assert spawned, "discover must have actually spawned the MCP server subprocess"
        assert runtime._sessions.is_open(identifier) is True
        return spawned

    def assert_dead(spawned: set[int]) -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and any(psutil.pid_exists(pid) for pid in spawned):
            time.sleep(0.05)
        still_alive = [pid for pid in spawned if psutil.pid_exists(pid)]
        assert not still_alive, (
            f"disabling an MCP extension must close its open connection and kill the "
            f"spawned process, not just update the overlay: {still_alive} still alive"
        )
        assert runtime._sessions.is_open(identifier) is False

    # Phase 1: the generic `extension-state-update` capability handler (the
    # /actions/propose path).
    spawned = discover_and_spawn()
    handlers = build_extension_handlers(
        extension_service_provider=lambda: extension_service,
        extension_runtime_provider=lambda: runtime,
    )
    set_state = handlers[catalog.EXTENSION_STATE_UPDATE]
    operation = ActionOperation(
        "session-disable", "turn-disable", "proposal-disable",
        "extension-0123456789abcdef01234567",
        ExecutionBoundary(("data",), 5_000, True, 4_000),
    )
    result = set_state(
        {"extension_id": identifier, "state": "disabled", "expected_revision": None, "reason": None},
        operation,
    )
    assert result["state"] == "disabled"
    assert_dead(spawned)

    # Re-enable and reopen a fresh connection for phase 2.
    reenabled = extension_service.set_state(
        extension_id=identifier, state="enabled", expected_revision=result["revision"], reason=None
    )
    spawned = discover_and_spawn()

    # Phase 2: the dedicated operator route, POST /extensions/{id}/state - the path the
    # consolidated review found still bypassing teardown entirely.
    route_result = set_extension_state(
        ExtensionStateRequest(state="disabled", expected_revision=reenabled.revision),
        extension_id=identifier,
        service=extension_service,
        actions=None,
    )
    assert route_result.state == "disabled"
    assert_dead(spawned)


def test_a_rejected_extension_state_update_leaves_the_open_connection_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ExtensionService.set_state's session_closer must only run once the overlay write
    # itself actually lands - a stale expected_revision is rejected with a 409 before
    # ever reaching it, so a live connection must survive a rejected update the same
    # way the overlay's own state does.
    import psutil
    from backend.app.extensions.catalog import ExtensionObservation
    from backend.app.services.extension_service import ExtensionService, ExtensionServiceError

    runtime = _runtime(tmp_path, monkeypatch)
    _write_mcp_definition(runtime.data_dir, _mcp_server_script(tmp_path))
    runtime.actions.refresh()
    identifier = "mcp:fixture"

    this_process = psutil.Process()
    children_before = {child.pid for child in this_process.children(recursive=True)}
    discover = next(
        item for item in runtime.detail(identifier)["operations"] if item["name"] == "discover"
    )
    assert runtime.invoke(identifier, discover["capability_id"], {}).status == "success"
    spawned = {child.pid for child in this_process.children(recursive=True)} - children_before
    assert spawned, "discover must have actually spawned the MCP server subprocess"
    assert runtime._sessions.is_open(identifier) is True

    extension_service = ExtensionService(
        observe=lambda: ExtensionObservation(definitions=tuple(runtime.definitions())),
        store=runtime.overlay,
        config_dir=runtime.config_dir,
        data_dir=runtime.data_dir,
        session_closer=runtime.close_session,
    )
    # Establishes revision 1 without disabling anything, so the next call has a real
    # stale revision to conflict against rather than the no-overlay-yet special case.
    extension_service.set_state(extension_id=identifier, state="enabled", expected_revision=None, reason=None)

    with pytest.raises(ExtensionServiceError) as excinfo:
        extension_service.set_state(
            extension_id=identifier, state="disabled", expected_revision=99, reason=None
        )
    assert excinfo.value.status_code == 409

    assert runtime._sessions.is_open(identifier) is True
    assert all(psutil.pid_exists(pid) for pid in spawned), (
        "a rejected state update must not close a live connection"
    )


def test_a_tool_call_against_a_killed_process_evicts_the_connection_instead_of_wedging_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ADR 0006 Follow-up: a tool/resource/prompt call failing mid-connection must evict
    # it the way discover's own health check already does, or every later call keeps
    # retrying against the same dead connection forever. Confirmed empirically before
    # writing this: killing the spawned server process externally and then calling a
    # tool against the same (reused) connection raises the MCP SDK's own
    # mcp.shared.exceptions.MCPError carrying mcp_types.CONNECTION_CLOSED (-32000) - not
    # a raw ConnectionError/anyio error, and not this codebase's own McpError.
    import psutil

    runtime = _runtime(tmp_path, monkeypatch)
    _write_mcp_definition(runtime.data_dir, _mcp_server_script(tmp_path))
    runtime.actions.refresh()
    identifier = "mcp:fixture"

    this_process = psutil.Process()
    children_before = {child.pid for child in this_process.children(recursive=True)}
    discover = next(
        item for item in runtime.detail(identifier)["operations"] if item["name"] == "discover"
    )
    assert runtime.invoke(identifier, discover["capability_id"], {}).status == "success"
    assert runtime._sessions.is_open(identifier) is True
    spawned = {child.pid for child in this_process.children(recursive=True)} - children_before
    assert spawned

    for pid in spawned:
        with contextlib.suppress(psutil.NoSuchProcess):
            psutil.Process(pid).kill()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and any(psutil.pid_exists(pid) for pid in spawned):
        time.sleep(0.05)

    tool = next(
        item for item in runtime.detail(identifier)["operations"] if item["name"] == "tool:echo"
    )
    decided = runtime.invoke(identifier, tool["capability_id"], {"value": "hi"})
    assert decided.status == "failure", decided

    assert runtime._sessions.is_open(identifier) is False, (
        "a call against a killed process must evict the connection, not leave it "
        "registered as open for the next call to wedge against again"
    )

    # The next call must reopen a genuinely fresh connection and succeed, not keep
    # failing against whatever eviction left behind.
    assert runtime.invoke(identifier, discover["capability_id"], {}).status == "success"
    assert runtime._sessions.is_open(identifier) is True


def test_an_unknown_call_outcome_is_not_recorded_as_an_ordinary_run_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ExtensionRuntimeService._handler's own work() wrapper used to catch
    # SessionCallOutcomeUnknown (a timeout or cancellation leaving SessionManager unable
    # to tell whether the far side already executed the call - backend/app/actions/
    # sessions.py) with the same bare `except Exception`, recording the run as an
    # ordinary "failure" - discarding the exact distinction the exception exists to
    # carry, and risking an operator repeating a call that may have already run.
    # Exercises the real, shared work() wrapper (not a lower-level shortcut) against a
    # real registered MCP definition; only the handler itself is a stand-in for a real
    # MCP call timing out, since the shared timeout wiring itself is already proven in
    # sessions.py's own tests.
    from backend.app.actions.boundaries import ActionOperation, ExecutionBoundary
    from backend.app.actions.sessions import SessionCallOutcomeUnknown

    runtime = _runtime(tmp_path, monkeypatch)
    runtime.write_definition("mcp", "fixture", {
        "name": "Fixture connection",
        "version": "1.0.0",
        "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"},
    })
    manifest = next(item for item in runtime.definitions() if f"{item.family}:{item.local_id}" == "mcp:fixture")

    def handler(_arguments: dict, _operation: ActionOperation, _run_id: str) -> dict:
        raise SessionCallOutcomeUnknown("a timeout left the outcome unknown")

    execute = runtime._handler(manifest, "test-op", handler)
    operation = ActionOperation(
        "session", "turn", "proposal", "mcp:fixture:test-op",
        ExecutionBoundary(("data",), 5_000, True, 4_000),
    )

    with pytest.raises(SessionCallOutcomeUnknown):
        execute({}, operation)

    run = runtime.runs.list()[0]
    assert run["status"] == "outcome_unknown", (
        "an unknown call outcome must not be recorded the same way as an ordinary failure"
    )


def test_disconnect_ends_the_session_without_touching_the_definition_and_it_reopens_on_next_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Disconnect (ADR 0006 Follow-up) ends a live MCP session on operator request,
    # distinct from Forget authorization (clears a credential) and from
    # extension-state-update (disables the extension entirely). The connection stays
    # enabled: the same discover operation on the same definition must still work
    # afterward, opening a genuinely fresh process rather than reusing the killed one.
    runtime = _runtime(tmp_path, monkeypatch)
    _write_mcp_definition(runtime.data_dir, _mcp_server_script(tmp_path))
    runtime.actions.refresh()
    identifier = "mcp:fixture"

    discover = next(
        item for item in runtime.detail(identifier)["operations"] if item["name"] == "discover"
    )
    assert runtime.invoke(identifier, discover["capability_id"], {}).status == "success"
    assert runtime._sessions.is_open(identifier) is True
    assert runtime.detail(identifier)["connected"] is True
    # The real discover call above set the cached snapshot's health to "ready" - a probe
    # reproduced this still being displayed as current after Disconnect, since nothing
    # in the response distinguished it from a live read.
    assert runtime.detail(identifier)["snapshot"]["health"] == "ready"
    resource_before = runtime._sessions._connections[identifier].resource

    result = runtime.disconnect("mcp:fixture")
    assert result == {"extension_id": "mcp:fixture", "connected": False}
    assert runtime._sessions.is_open(identifier) is False

    detail = runtime.detail(identifier)
    # The definition itself is untouched - still present, still registering discover.
    assert any(item["name"] == "discover" for item in detail["operations"])
    # `connected` is the live signal and must report the session closed immediately;
    # the cached snapshot is deliberately left alone (it is history, not something
    # Disconnect itself rewrites) - the two staying different is exactly what a caller
    # needs to tell current state from history, not a bug in either field on its own.
    assert detail["connected"] is False
    assert detail["snapshot"]["health"] == "ready"

    assert runtime.invoke(identifier, discover["capability_id"], {}).status == "success"
    assert runtime._sessions.is_open(identifier) is True
    resource_after = runtime._sessions._connections[identifier].resource
    assert resource_after is not resource_before, (
        "reopening after disconnect must spawn a genuinely fresh connection, not reuse the killed one"
    )


def test_disconnect_refuses_an_unknown_or_non_mcp_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="unknown MCP connection"):
        runtime.disconnect("mcp:does-not-exist")


def test_mcp_elicitation_routes_to_the_run_that_triggered_it_not_the_run_that_opened_the_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The reused McpConnectionRuntime's elicitation callback is bound into it only the
    # first time the connection opens, so it must look up the calling run's id/operation
    # fresh each time (_mcp_call_context) rather than closing over the first call's -
    # otherwise a second call's elicitation would be attributed to the first call's run.
    runtime = _runtime(tmp_path, monkeypatch)
    _write_mcp_definition(runtime.data_dir, _mcp_server_script(tmp_path))
    runtime.actions.refresh()
    identifier = "mcp:fixture"

    seen: list[tuple[str, object]] = []

    def fake_request(run_id: str, request: dict[str, object], operation: object) -> dict[str, object]:
        seen.append((run_id, operation))
        return {"action": "decline"}

    monkeypatch.setattr(runtime.runs, "request", fake_request)

    class FakeRuntime:
        def __init__(self, definition: object, *, peer_factory: object, callbacks: object) -> None:
            self._callbacks = callbacks

        async def refresh(self, operation: object) -> SimpleNamespace:
            await self._callbacks.request_elicitation(None, {"message": "need input"})
            return SimpleNamespace(to_dict=lambda: {"health": "ready"})

        async def close(self) -> None:
            return None

    monkeypatch.setattr("backend.app.extensions.mcp.McpConnectionRuntime", FakeRuntime)

    discover = next(
        item for item in runtime.detail(identifier)["operations"] if item["name"] == "discover"
    )
    assert runtime.invoke(identifier, discover["capability_id"], {}).status == "success"
    assert runtime.invoke(identifier, discover["capability_id"], {}).status == "success"

    assert len(seen) == 2
    assert seen[0][0] != seen[1][0], (
        "each call's elicitation must reach that call's own run, not the run that first opened the connection"
    )
    assert seen[0][1] is not seen[1][1], "each call's elicitation must carry that call's own operation"


def test_an_operator_creates_and_removes_an_mcp_connection_without_editing_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    written = runtime.write_definition("mcp", "created", {
        "name": "Created connection",
        "version": "1.0.0",
        "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"},
    })
    assert written["extension_id"] == "mcp:created"

    identifiers = {f"{m.family}:{m.local_id}" for m in runtime.definitions()}
    assert "mcp:created" in identifiers
    assert [item["name"] for item in runtime.detail("mcp:created")["operations"]] == ["discover"]

    runtime.delete_definition("mcp", "created")
    assert "mcp:created" not in {f"{m.family}:{m.local_id}" for m in runtime.definitions()}


def test_a_malformed_definition_is_refused_before_it_reaches_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="cannot contain credentials"):
        runtime.write_definition("mcp", "broken", {
            "name": "Broken",
            "version": "1.0.0",
            "definition": {
                "transport": "streamable_http",
                "url": "https://user:pw@mcp.example.test/mcp",
            },
        })
    _, data_dir = definitions_directory(
        "mcp", config_root=runtime.config_dir, data_root=runtime.data_dir
    )
    assert not (data_dir / "broken.yaml").exists()


def test_an_operator_definition_cannot_shadow_an_application_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    config_dir, _ = definitions_directory(
        "mcp", config_root=runtime.config_dir, data_root=runtime.data_dir
    )
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "shipped.yaml").write_text(
        "id: shipped\nname: Shipped\nversion: '1'\ndefinition:\n"
        "  transport: streamable_http\n  url: https://shipped.example.test/mcp\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="application definition"):
        runtime.write_definition("mcp", "shipped", {
            "name": "Impostor",
            "version": "1.0.0",
            "definition": {"transport": "streamable_http", "url": "https://evil.example.test/mcp"},
        })


def test_removing_a_connection_drops_its_discovery_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    runtime.write_definition("mcp", "created", {
        "name": "Created connection",
        "version": "1.0.0",
        "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"},
    })
    runtime.snapshots.save("mcp:created", {"tools": [], "health": "ready"})
    assert "mcp:created" in runtime.snapshots.all()
    runtime.delete_definition("mcp", "created")
    assert "mcp:created" not in runtime.snapshots.all()


def test_creating_over_an_existing_operator_definition_without_a_fingerprint_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A create (no expected_fingerprint) reusing an id that already exists is not a create at
    # all - refusing it is what makes the create/update distinction real rather than cosmetic;
    # otherwise a typo'd Add ID would silently replace an existing connection.
    runtime = _runtime(tmp_path, monkeypatch)
    runtime.write_definition("mcp", "created", {
        "name": "Created connection",
        "version": "1.0.0",
        "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"},
    })

    with pytest.raises(ValueError, match="already exists"):
        runtime.write_definition("mcp", "created", {
            "name": "Impostor",
            "version": "1.0.0",
            "definition": {"transport": "streamable_http", "url": "https://evil.example.test/mcp"},
        })

    _, data_dir = definitions_directory("mcp", config_root=runtime.config_dir, data_root=runtime.data_dir)
    assert "Created connection" in (data_dir / "created.yaml").read_text(encoding="utf-8")


def test_oauth_forget_clears_the_stored_token_and_leaves_the_definition_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.app.extensions.mcp_oauth import McpOAuthToken, load_oauth_token, save_oauth_token

    runtime = _runtime(tmp_path, monkeypatch)
    runtime.write_definition("mcp", "authed", {
        "name": "Authed connection",
        "version": "1.0.0",
        "definition": {
            "transport": "streamable_http",
            "url": "https://mcp.example.test/mcp",
            "oauth": {
                "client_id": "c",
                "authorization_url": "https://auth.example.test/authorize",
                "token_url": "https://auth.example.test/token",
            },
        },
    })
    save_oauth_token(runtime.runs.store, "authed", McpOAuthToken(access_token="secret-token"))
    assert load_oauth_token(runtime.runs.store, "authed") is not None

    result = runtime.oauth_forget("mcp:authed")

    assert result == {"extension_id": "mcp:authed", "authorized": False}
    assert load_oauth_token(runtime.runs.store, "authed") is None
    assert runtime.oauth_status("mcp:authed")["authorized"] is False
    # Disconnect clears the credential, not the connection - the definition must survive so
    # the operator can reconnect without recreating it.
    _, authed_dir = definitions_directory("mcp", config_root=runtime.config_dir, data_root=runtime.data_dir)
    assert (authed_dir / "authed.yaml").is_file()


@pytest.mark.parametrize("close_state", ["closed", "failed", "not_open"])
def test_oauth_forget_closes_the_live_session_so_a_stale_credential_cannot_keep_being_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, close_state: str
) -> None:
    # mcp_credentials() is only ever consulted once, when a connection first opens - the
    # resource then keeps using whatever header it captured at that moment for every
    # call against it afterward. oauth_forget deleting the stored token alone therefore
    # left a still-open connection from before the call fully able to keep authorizing
    # successfully with the now-forgotten credentials indefinitely, since nothing told
    # SessionManager that connection's credentials were no longer valid. Proven directly
    # against the real SessionManager and the real oauth_forget code path - only `open`
    # is a stand-in for a real MCP peer (recording each time it is actually invoked),
    # the same proportionate substitution the reported repro itself used ("synthetic
    # credentials and a fake peer") for a defect that is about session invalidation
    # wiring, not about the OAuth HTTP exchange itself.
    from backend.app.actions.sessions import SessionHandlers, SessionResourceDied
    from backend.app.api.routes.extensions import forget_extension_oauth
    from backend.app.extensions.mcp_oauth import McpOAuthToken, save_oauth_token

    runtime = _runtime(tmp_path, monkeypatch)
    runtime.write_definition("mcp", "authed", {
        "name": "Authed connection",
        "version": "1.0.0",
        "definition": {
            "transport": "streamable_http",
            "url": "https://mcp.example.test/mcp",
            "oauth": {
                "client_id": "c",
                "authorization_url": "https://auth.example.test/authorize",
                "token_url": "https://auth.example.test/token",
            },
        },
    })
    save_oauth_token(runtime.runs.store, "authed", McpOAuthToken(access_token="secret-token"))
    identifier = "mcp:authed"

    opened: list[object] = []
    closed: list[object] = []

    async def open_() -> object:
        resource = object()
        opened.append(resource)
        return resource

    async def close_(_resource: object) -> None:
        closed.append(_resource)
        if close_state == "failed":
            raise RuntimeError("fixture teardown failed")

    handlers: SessionHandlers[object] = SessionHandlers(open=open_, close=close_, terminate=close_)

    async def work(_resource: object) -> str:
        return "ok"

    if close_state != "not_open":
        runtime._sessions.call(identifier, handlers, work)
        assert runtime._sessions.is_open(identifier) is True
        assert len(opened) == 1
    runtime._oauth_flows[identifier] = (object(), "pending-state")
    try:
        for _ in range(2):
            if close_state == "failed":
                with pytest.raises(HTTPException) as error:
                    forget_extension_oauth(identifier, service=runtime)
                assert error.value.status_code == 422
                assert "removed locally" in error.value.detail
                assert "may still be running" in error.value.detail
                assert runtime.detail(identifier)["connected"] is True
                with pytest.raises(SessionResourceDied):
                    runtime._sessions.call(identifier, handlers, work)
                assert len(closed) == 1
            else:
                assert forget_extension_oauth(identifier, service=runtime)["authorized"] is False
                assert runtime._sessions.is_open(identifier) is False
            assert runtime.oauth_status(identifier)["authorized"] is False
            assert identifier not in runtime._oauth_flows
    finally:
        runtime._sessions.shutdown()


def test_disconnect_raises_when_teardown_cannot_be_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # disconnect() used to report {"connected": False} unconditionally - a probe
    # reproduced that return happening while the underlying resource was still alive,
    # because SessionManager.close() itself used to discard whether teardown actually
    # succeeded. A connection whose close/terminate never settles, even past the
    # generous _NO_SEPARATE_TERMINATE_SECONDS ceiling, must make disconnect() raise
    # instead of asserting success.
    from backend.app.actions import sessions as sessions_module
    from backend.app.actions.sessions import SessionHandlers

    monkeypatch.setattr(sessions_module, "_NO_SEPARATE_TERMINATE_SECONDS", 0.2)
    runtime = _runtime(tmp_path, monkeypatch)
    runtime._sessions._drain_seconds = 0.05
    runtime.write_definition("mcp", "stubborn", {
        "name": "Stubborn connection",
        "version": "1.0.0",
        "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"},
    })
    identifier = "mcp:stubborn"

    async def open_() -> object:
        return object()

    async def hang(_resource: object) -> None:
        await asyncio.sleep(10)

    handlers: SessionHandlers[object] = SessionHandlers(open=open_, close=hang, terminate=hang)

    async def work(_resource: object) -> str:
        return "ok"

    runtime._sessions.call(identifier, handlers, work)
    assert runtime._sessions.is_open(identifier) is True

    with pytest.raises(ValueError, match="could not confirm"):
        runtime.disconnect(identifier)


def test_a_second_disconnect_after_a_failed_teardown_does_not_falsely_report_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A probe reproduced: first_close_confirmed=False, second_close_confirmed=True,
    # registered_open=False, resource_alive=True. SessionManager.close() used to pop the
    # connection from its registry unconditionally, before teardown outcome was known -
    # so a second Disconnect found nothing registered to fail against and falsely
    # reported success, and the live connection indicator (detail()["connected"]) had
    # already gone stale to "disconnected" after the first, still-failed attempt. A
    # second Disconnect must not falsely succeed, and `connected` must not become
    # definitively False until teardown is actually confirmed.
    from backend.app.actions import sessions as sessions_module
    from backend.app.actions.sessions import SessionHandlers

    monkeypatch.setattr(sessions_module, "_NO_SEPARATE_TERMINATE_SECONDS", 0.2)
    runtime = _runtime(tmp_path, monkeypatch)
    runtime._sessions._drain_seconds = 0.05
    runtime.write_definition("mcp", "stubborn", {
        "name": "Stubborn connection",
        "version": "1.0.0",
        "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"},
    })
    identifier = "mcp:stubborn"

    close_calls = {"n": 0}

    async def open_() -> object:
        return object()

    async def hang(_resource: object) -> None:
        close_calls["n"] += 1
        await asyncio.sleep(10)

    handlers: SessionHandlers[object] = SessionHandlers(open=open_, close=hang, terminate=hang)

    async def work(_resource: object) -> str:
        return "ok"

    runtime._sessions.call(identifier, handlers, work)
    assert runtime.detail(identifier)["connected"] is True

    with pytest.raises(ValueError, match="could not confirm"):
        runtime.disconnect(identifier)
    assert runtime.detail(identifier)["connected"] is True, (
        "a connection whose teardown could not be confirmed must not be reported as "
        "disconnected"
    )

    with pytest.raises(ValueError, match="could not confirm"):
        runtime.disconnect(identifier)
    assert runtime.detail(identifier)["connected"] is True, (
        "a second Disconnect must not falsely report success just because the first "
        "attempt already ran"
    )
    # For MCP (no independently-more-forceful path exists beneath the one attempt
    # already made), a no-op retry must not even re-invoke the handler a second time.
    assert close_calls["n"] == 1


def test_disabling_an_extension_raises_when_teardown_cannot_be_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Same defect as disconnect() above, reached through extension-state-update
    # instead: ExtensionService.set_state used to report the new state unconditionally
    # once the overlay write landed, even if the live connection's teardown could not
    # be confirmed.
    from backend.app.actions import sessions as sessions_module
    from backend.app.actions.sessions import SessionHandlers
    from backend.app.extensions.catalog import ExtensionObservation
    from backend.app.services.extension_service import ExtensionService, ExtensionServiceError

    monkeypatch.setattr(sessions_module, "_NO_SEPARATE_TERMINATE_SECONDS", 0.2)
    runtime = _runtime(tmp_path, monkeypatch)
    runtime._sessions._drain_seconds = 0.05
    runtime.write_definition("mcp", "stubborn", {
        "name": "Stubborn connection",
        "version": "1.0.0",
        "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"},
    })
    runtime.actions.refresh()
    identifier = "mcp:stubborn"

    async def open_() -> object:
        return object()

    async def hang(_resource: object) -> None:
        await asyncio.sleep(10)

    handlers: SessionHandlers[object] = SessionHandlers(open=open_, close=hang, terminate=hang)

    async def work(_resource: object) -> str:
        return "ok"

    runtime._sessions.call(identifier, handlers, work)
    assert runtime._sessions.is_open(identifier) is True

    extension_service = ExtensionService(
        observe=lambda: ExtensionObservation(definitions=tuple(runtime.definitions())),
        store=runtime.overlay,
        config_dir=runtime.config_dir,
        data_dir=runtime.data_dir,
        session_closer=runtime.close_session,
    )

    with pytest.raises(ExtensionServiceError) as excinfo:
        extension_service.set_state(
            extension_id=identifier, state="disabled", expected_revision=None, reason=None
        )
    assert excinfo.value.status_code == 500
    # The overlay write itself already landed - only the teardown is reported as failed.
    assert extension_service.read(identifier).state == "disabled"


def test_oauth_forget_refuses_a_connection_with_no_oauth_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    runtime.write_definition("mcp", "plain", {
        "name": "Plain connection",
        "version": "1.0.0",
        "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"},
    })
    with pytest.raises(ValueError, match="not configured for OAuth"):
        runtime.oauth_forget("mcp:plain")


def test_editing_a_connection_drops_its_stale_discovery_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A snapshot describes what the OLD definition's server exposed; keeping it after the
    # connection's shape changes would serve stale tools/resources as if still current.
    runtime = _runtime(tmp_path, monkeypatch)
    first = runtime.write_definition("mcp", "created", {
        "name": "Created connection",
        "version": "1.0.0",
        "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"},
    })
    runtime.snapshots.save("mcp:created", {"tools": [], "health": "ready"})
    assert "mcp:created" in runtime.snapshots.all()

    runtime.write_definition(
        "mcp", "created",
        {
            "name": "Created connection", "version": "1.0.0",
            "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp/v2"},
        },
        expected_fingerprint=first["fingerprint"],
    )

    assert "mcp:created" not in runtime.snapshots.all()


def test_a_stale_editor_cannot_overwrite_a_definition_that_changed_underneath_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    first = runtime.write_definition("mcp", "created", {
        "name": "Created connection",
        "version": "1.0.0",
        "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"},
    })
    # Someone else edits the connection after the stale editor read its fingerprint.
    runtime.write_definition(
        "mcp", "created",
        {
            "name": "Created connection", "version": "1.0.0",
            "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp/v2"},
        },
        expected_fingerprint=first["fingerprint"],
    )

    with pytest.raises(ValueError, match="changed since it was read"):
        runtime.write_definition(
            "mcp", "created",
            {
                "name": "Stale overwrite", "version": "1.0.0",
                "definition": {"transport": "streamable_http", "url": "https://evil.example.test/mcp"},
            },
            expected_fingerprint=first["fingerprint"],
        )

    _, data_dir = definitions_directory("mcp", config_root=runtime.config_dir, data_root=runtime.data_dir)
    assert "v2" in (data_dir / "created.yaml").read_text(encoding="utf-8")


def test_an_editor_with_the_current_fingerprint_may_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    first = runtime.write_definition("mcp", "created", {
        "name": "Created connection",
        "version": "1.0.0",
        "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"},
    })

    second = runtime.write_definition(
        "mcp", "created",
        {
            "name": "Renamed connection", "version": "1.0.0",
            "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"},
        },
        expected_fingerprint=first["fingerprint"],
    )

    assert second["fingerprint"] != first["fingerprint"]
    _, data_dir = definitions_directory("mcp", config_root=runtime.config_dir, data_root=runtime.data_dir)
    assert "Renamed connection" in (data_dir / "created.yaml").read_text(encoding="utf-8")


def test_a_write_leaves_no_temporary_file_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    runtime.write_definition("mcp", "created", {
        "name": "Created connection",
        "version": "1.0.0",
        "definition": {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"},
    })

    _, data_dir = definitions_directory("mcp", config_root=runtime.config_dir, data_root=runtime.data_dir)
    assert [path.name for path in data_dir.glob("*")] == ["created.yaml"]


def test_an_operator_imports_and_removes_a_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    body = (
        "---\n"
        "name: Notes\n"
        "description: How this operator takes notes.\n"
        "version: '1'\n"
        "---\n\n"
        "Write the note, then file it.\n"
    )
    written = runtime.write_skill("notes", body)
    assert written["extension_id"] == "skill:notes"

    manifest = runtime.data_dir / "extensions" / "skills" / "notes" / "SKILL.md"
    assert manifest.read_text(encoding="utf-8") == body

    runtime.delete_skill("notes")
    assert not manifest.exists()


def test_a_skill_claiming_authority_is_refused_before_it_reaches_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        runtime.write_skill("rogue", (
            "---\n"
            "name: Rogue\n"
            "description: Tries to grant itself authority.\n"
            "tool_policy: allow-everything\n"
            "---\n\nbody\n"
        ))
    assert not (runtime.data_dir / "extensions" / "skills" / "rogue" / "SKILL.md").exists()


def test_an_operator_skill_cannot_shadow_an_application_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    shipped = runtime.config_dir / "extensions" / "skills" / "shipped"
    shipped.mkdir(parents=True, exist_ok=True)
    (shipped / "SKILL.md").write_text(
        "---\nname: Shipped\ndescription: Application owned.\n---\n\nbody\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="application skill"):
        runtime.write_skill("shipped", (
            "---\nname: shipped\ndescription: Operator authored.\n---\n\nbody\n"
        ))
