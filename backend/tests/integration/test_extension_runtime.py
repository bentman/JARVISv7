from __future__ import annotations

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


def test_tool_requires_approval_then_executes_and_records_run_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    _write_tool_definition(runtime.config_dir)
    capability_id = _operation_id(runtime, "tool:writer")

    runtime.overlay.set_state(extension_id="tool:writer", state="disabled", expected_revision=None)
    denied = runtime.invoke("tool:writer", capability_id, {})
    assert denied.status == "denied"
    runtime.overlay.set_state(extension_id="tool:writer", state="enabled", expected_revision=1)

    proposed = runtime.invoke("tool:writer", capability_id, {})

    assert proposed.status == "awaiting_approval"
    assert not (runtime.data_dir / "marker.txt").exists()
    executed = runtime.actions.decide(
        proposal_id=proposed.proposal_id, outcome="approved", decided_by="operator"
    )

    assert executed.status == "success"
    assert (runtime.data_dir / "marker.txt").read_text(encoding="utf-8") == "ran"
    run = runtime.runs.list()[0]
    assert run["extension_id"] == "tool:writer"
    assert run["status"] == "success"
    assert executed.execution["result"]["output"]["exit_code"] == 0


def test_denied_tool_proposal_has_no_side_effect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    _write_tool_definition(runtime.config_dir)
    proposed = runtime.invoke("tool:writer", _operation_id(runtime, "tool:writer"), {})

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
    proposed = runtime.invoke("tool:writer", _operation_id(runtime, "tool:writer"), {})
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
        lambda definition, prompt, operation, **_kwargs: {
            "agent_id": definition.agent_id, "prompt": prompt, "operation_turn": operation.turn_id
        },
    )
    proposed = runtime.invoke("acp:agent", _operation_id(runtime, "acp:agent"), {"prompt": "summarize"})
    executed = runtime.actions.decide(
        proposal_id=proposed.proposal_id, outcome="approved", decided_by="operator"
    )

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

    def wait_for_permission(_definition, _prompt, _operation, *, request_permission, **_kwargs):
        return request_permission({"message": "approve tool?"})

    monkeypatch.setattr(acp, "run_acp", wait_for_permission)
    proposed = runtime.invoke("acp:agent", _operation_id(runtime, "acp:agent"), {"prompt": "work"})
    completed: list[object] = []
    thread = threading.Thread(
        target=lambda: completed.append(runtime.actions.decide(
            proposal_id=proposed.proposal_id, outcome="approved", decided_by="operator"
        )),
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

    assert runtime.actions.cancel(proposed.proposal_id) is True
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


def test_discovered_mcp_operations_survive_a_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    _write_mcp_definition(runtime.data_dir, _mcp_server_script(tmp_path))
    runtime.actions.refresh()

    discover = next(
        item for item in runtime.detail("mcp:fixture")["operations"] if item["name"] == "discover"
    )
    proposed = runtime.invoke("mcp:fixture", discover["capability_id"], {})
    # A stdio connection spawns a process, so discovery is approval-gated.
    view = runtime.actions.decide(
        proposal_id=proposed.proposal_id, outcome="approved", decided_by="operator"
    )
    assert view.status == "success", view

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
