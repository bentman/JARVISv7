from __future__ import annotations

from pathlib import Path
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
    monkeypatch.setattr(validate_backend, "_write_report", lambda *args, **kwargs: None)

    exit_code = validate_backend.main(["profile"])
    output = capsys.readouterr().out.splitlines()

    assert exit_code == 0
    assert output[0].startswith("[fingerprint]")
    assert "preflight" in output[1]


def test_write_report_uses_timestamp_before_label(monkeypatch) -> None:
    monkeypatch.setattr(validate_backend, "_timestamp_slug", lambda: "20260424143000")

    directory = Path("cache") / "validate-backend-report-test"
    directory.mkdir(parents=True, exist_ok=True)
    path = validate_backend._write_report(directory, "regression", "body")

    try:
        assert path.name == "20260424143000-regression.txt"
        assert path.read_text(encoding="utf-8") == "body"
    finally:
        path.unlink(missing_ok=True)
        directory.rmdir()


def test_regression_report_helpers_emit_structured_rows() -> None:
    directory = Path("cache") / "validate-backend-regression-test"
    directory.mkdir(parents=True, exist_ok=True)
    xml_path = directory / "results.xml"
    xml_path.write_text(
        """<?xml version='1.0' encoding='utf-8'?>
<testsuite name='pytest' tests='2' failures='1' errors='0' skipped='1'>
  <testcase classname='tests.unit.example' name='test_pass'/>
  <testcase classname='tests.unit.example' name='test_skip'>
    <skipped message='skip'/>
  </testcase>
  <testcase classname='tests.unit.example' name='test_fail'>
    <failure message='boom'>boom</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )

    try:
        rows, summary = validate_backend._collect_regression_rows(xml_path)
        report = validate_backend._format_regression_report(
            started_at="2026-04-24T14:50:00Z",
            report_path=Path("reports") / "validation" / "20260424145000-regression.txt",
            fingerprint_line="[fingerprint] arch=amd64 python=3.12.10 extras=[dev] readiness=ready; tokens=1 profiled=unknown",
            command=["python", "-m", "pytest", "-q"],
            validator_code=1,
            pytest_return_code=1,
            rows=rows,
            summary=summary,
            stdout="pytest stdout",
            stderr="pytest stderr",
            xml_path=xml_path,
        )

        assert [row.status for row in rows] == ["PASS", "SKIP", "FAIL"]
        assert "JARVISv7 Backend Regression Validation started at 2026-04-24T14:50:00Z" in report
        assert "Report File: reports\\validation\\20260424145000-regression.txt" in report
        assert "UNIT TESTS" in report
        assert "[PASS] PASS: tests.unit.example::test_pass" in report
        assert "[SKIP] SKIP: tests.unit.example::test_skip" in report
        assert "[FAIL] FAIL: tests.unit.example::test_fail" in report
        assert "FAIL: unit: 2 tests, 1 failed, 1 skipped" in report
        assert "[INVARIANTS]" in report
        assert "UNIT=FAIL" in report
        assert "[FAIL] Validation failed - see suite output above" in report
        assert "PYTEST STDOUT" in report
        assert "pytest stderr" in report
    finally:
        xml_path.unlink(missing_ok=True)
        directory.rmdir()


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
