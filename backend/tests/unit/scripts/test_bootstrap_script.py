from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.hardware.preflight import PreflightResult
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


def _fake_preflight() -> PreflightResult:
    return PreflightResult(tokens=["import:onnxruntime"], dll_discovery_log=[], probe_errors={})


def test_bootstrap_halts_on_profiler_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        bootstrap,
        "_load_profiler",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    exit_code = bootstrap.main(["--dry-run"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "[CHECKPOINT 1/5] profile → FAIL" in output
    assert "boom" in output


def test_bootstrap_halts_on_provision_failure_with_checkpoint_reason(monkeypatch, capsys) -> None:
    monkeypatch.setattr(bootstrap, "_load_profiler", lambda: lambda: _fake_report())
    monkeypatch.setattr(bootstrap, "resolve_required_extras", lambda profile: ["dev"])
    monkeypatch.setattr(bootstrap, "run_preflight", lambda profile, extras: _fake_preflight())
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
    assert "[CHECKPOINT 2/5] provision → FAIL" in output


def test_bootstrap_checkpoint_numbering_is_stable(monkeypatch, capsys) -> None:
    monkeypatch.setattr(bootstrap, "_load_profiler", lambda: lambda: _fake_report())
    monkeypatch.setattr(bootstrap, "resolve_required_extras", lambda profile: ["dev"])
    monkeypatch.setattr(bootstrap, "run_preflight", lambda profile, extras: _fake_preflight())
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
