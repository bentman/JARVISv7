from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from scripts import bootstrap


@dataclass(slots=True)
class _Report:
    profile: HardwareProfile
    flags: CapabilityFlags


def _fake_report() -> _Report:
    return _Report(
        profile=HardwareProfile(arch="amd64", os_name="windows"),
        flags=CapabilityFlags(supports_local_stt=True),
    )


def _fake_preflight() -> SimpleNamespace:
    return SimpleNamespace(
        tokens=["import:onnxruntime"],
        dll_discovery_log=[],
        probe_errors={},
    )


def _fake_preflight_helpers():
    return (
        lambda profile, extras: _fake_preflight(),
        lambda preflight, profile: ("cpu", True, "stt ready"),
        lambda preflight, profile: ("cpu", True, "tts ready"),
        lambda preflight, profile: ("ollama", True, "llm ready"),
        lambda preflight, profile: ("cpu", True, "wake ready"),
    )


def test_bootstrap_has_no_dependency_bearing_checkpoint4_top_level_imports() -> None:
    source = Path(bootstrap.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_imports = {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert "backend.app.hardware.preflight" not in top_level_imports
    assert "backend.app.hardware.readiness" not in top_level_imports


def test_bootstrap_halts_on_profiler_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        bootstrap,
        "_load_profiler",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    exit_code = bootstrap.main(["--dry-run"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "[CHECKPOINT 1/5] profile -> FAIL" in output
    assert "boom" in output


def test_bootstrap_halts_on_provision_failure_with_checkpoint_reason(monkeypatch, capsys) -> None:
    monkeypatch.setattr(bootstrap, "_load_profiler", lambda: lambda: _fake_report())
    monkeypatch.setattr(bootstrap, "resolve_required_extras", lambda profile: ["dev"])
    monkeypatch.setattr(bootstrap, "_load_preflight_readiness_helpers", _fake_preflight_helpers)
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(
            returncode=1 if "provision.py" in " ".join(command) else 0
        ),
    )

    exit_code = bootstrap.main([])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "[CHECKPOINT 2/5] provision -> FAIL" in output


def test_bootstrap_checkpoint_numbering_is_stable(monkeypatch, capsys) -> None:
    monkeypatch.setattr(bootstrap, "_load_profiler", lambda: lambda: _fake_report())
    monkeypatch.setattr(bootstrap, "resolve_required_extras", lambda profile: ["dev"])
    monkeypatch.setattr(bootstrap, "_load_preflight_readiness_helpers", _fake_preflight_helpers)
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(returncode=0),
    )

    exit_code = bootstrap.main([])
    output = capsys.readouterr().out.splitlines()

    assert exit_code == 0
    assert [line.split("]")[0] for line in output if line.startswith("[CHECKPOINT")] == [
        "[CHECKPOINT 1/5",
        "[CHECKPOINT 2/5",
        "[CHECKPOINT 3/5",
        "[CHECKPOINT 4/5",
        "[CHECKPOINT 5/5",
    ]
