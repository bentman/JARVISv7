from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from scripts import validate_backend


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
    return PreflightResult(
        tokens=["import:pytest", "ep:CUDAExecutionProvider"],
        dll_discovery_log=[],
        probe_errors={},
    )


def test_profile_subcommand_prints_fingerprint_first_line(monkeypatch, capsys) -> None:
    monkeypatch.setattr(validate_backend, "_load_profiler", lambda: lambda: _fake_report())
    monkeypatch.setattr(validate_backend, "resolve_required_extras", lambda profile: ["dev"])
    monkeypatch.setattr(
        validate_backend,
        "run_preflight",
        lambda profile, extras: _fake_preflight(),
    )

    exit_code = validate_backend.main(["profile"])
    output = capsys.readouterr().out.splitlines()

    assert exit_code == 0
    assert output[0].startswith("[fingerprint]")
    assert "preflight" in output[1]


def test_unit_subcommand_invokes_pytest_on_unit_dir(monkeypatch, capsys) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    monkeypatch.setattr(validate_backend, "_pytest_available", lambda: True)
    monkeypatch.setattr(validate_backend, "_load_profiler", lambda: lambda: _fake_report())
    monkeypatch.setattr(validate_backend, "resolve_required_extras", lambda profile: ["dev"])
    monkeypatch.setattr(
        validate_backend,
        "run_preflight",
        lambda profile, extras: _fake_preflight(),
    )

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(validate_backend.subprocess, "run", fake_run)

    exit_code = validate_backend.main(["unit"])
    capsys.readouterr()

    assert exit_code == 0
    assert any("backend/tests/unit" in part for part in calls[0][0])


def test_runtime_subcommand_accepts_families_and_devices_filters(monkeypatch, capsys) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(validate_backend, "_pytest_available", lambda: True)
    monkeypatch.setattr(validate_backend, "_load_profiler", lambda: lambda: _fake_report())
    monkeypatch.setattr(validate_backend, "resolve_required_extras", lambda profile: ["dev"])
    monkeypatch.setattr(
        validate_backend,
        "run_preflight",
        lambda profile, extras: _fake_preflight(),
    )
    monkeypatch.setattr(
        validate_backend.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or SimpleNamespace(returncode=0),
    )

    exit_code = validate_backend.main(
        ["runtime", "--families", "stt,wake", "--devices", "cuda,qnn"]
    )
    capsys.readouterr()

    assert exit_code == 0
    assert "-m" in calls[0]
    assert "live and (stt or wake) and (cuda or qnn)" in calls[0]


def test_ci_subcommand_suppresses_live_markers(monkeypatch, capsys) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(validate_backend, "_pytest_available", lambda: True)
    monkeypatch.setattr(validate_backend, "_load_profiler", lambda: lambda: _fake_report())
    monkeypatch.setattr(validate_backend, "resolve_required_extras", lambda profile: ["dev"])
    monkeypatch.setattr(
        validate_backend,
        "run_preflight",
        lambda profile, extras: _fake_preflight(),
    )
    monkeypatch.setattr(
        validate_backend.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or SimpleNamespace(returncode=0),
    )

    exit_code = validate_backend.main(["ci"])
    capsys.readouterr()

    assert exit_code == 0
    assert any("not live" in part for part in calls[0])


def test_exit_codes_map_documented_states_correctly(monkeypatch) -> None:
    monkeypatch.setattr(validate_backend, "_pytest_available", lambda: True)
    monkeypatch.setattr(
        validate_backend.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(returncode=5),
    )

    assert validate_backend._run_pytest(["backend/tests/unit"]) == 2

    monkeypatch.setattr(validate_backend, "_pytest_available", lambda: False)
    assert validate_backend._run_pytest(["backend/tests/unit"]) == 3
