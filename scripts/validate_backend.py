from __future__ import annotations

import argparse
import io
import importlib.util
from dataclasses import asdict, dataclass
import json
from datetime import datetime, timezone
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.logging import configure_logging, emit_host_fingerprint
from backend.app.core.paths import REPO_ROOT as APP_REPO_ROOT
from backend.app.hardware.preflight import run_preflight
from backend.app.hardware.provisioning import resolve_required_extras

REPORTS_DIR = APP_REPO_ROOT / "reports"
DIAGNOSTICS_DIR = REPORTS_DIR / "diagnostics"
VALIDATION_DIR = REPORTS_DIR / "validation"
BENCHMARKS_DIR = REPORTS_DIR / "benchmarks"
CACHE_DIR = APP_REPO_ROOT / "cache" / "validate_backend"


def _load_profiler():
    from backend.app.hardware.profiler import run_profiler

    return run_profiler


def _load_context():
    profiler = _load_profiler()
    report = profiler()
    profile = report.profile
    extras = resolve_required_extras(profile)
    preflight = run_preflight(profile, extras)
    return report, extras, preflight


def _current_readiness_summary(preflight) -> str:
    status = "ready" if not preflight.probe_errors else "degraded"
    return f"{status}; tokens={len(preflight.tokens)}"


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _capture_host_fingerprint(profile, extras, readiness: str) -> str:
    buffer = io.StringIO()
    emit_host_fingerprint(profile, extras, readiness=readiness, out=buffer)
    return buffer.getvalue().strip()


def _write_report(directory: Path, stem: str, content: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_timestamp_slug()}-{stem}.txt"
    path.write_text(content, encoding="utf-8")
    return path


def _write_report_at_path(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@dataclass(slots=True)
class _RegressionTestRow:
    status: str
    classname: str
    test_name: str


@dataclass(slots=True)
class _RegressionSuiteSummary:
    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0

    @property
    def has_failures(self) -> bool:
        return self.failures > 0 or self.errors > 0


def _relative_report_path(path: Path) -> str:
    if path.is_absolute():
        return str(path.relative_to(APP_REPO_ROOT)).replace("/", "\\")
    return str(path).replace("/", "\\")


def _regression_temp_xml_path() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{_timestamp_slug()}-regression-junit.xml"


def _read_int_attribute(element: ET.Element, name: str) -> int:
    value = element.get(name, "0")
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _collect_regression_rows(xml_path: Path) -> tuple[list[_RegressionTestRow], _RegressionSuiteSummary]:
    if not xml_path.exists():
        return [], _RegressionSuiteSummary()

    try:
        root = ET.parse(xml_path).getroot()
    except (ET.ParseError, OSError):
        return [], _RegressionSuiteSummary()
    rows: list[_RegressionTestRow] = []
    for testcase in root.findall(".//testcase"):
        classname = testcase.get("classname") or "unknown"
        test_name = testcase.get("name") or "unknown"
        if testcase.find("skipped") is not None:
            status = "SKIP"
        elif testcase.find("failure") is not None or testcase.find("error") is not None:
            status = "FAIL"
        else:
            status = "PASS"
        rows.append(_RegressionTestRow(status=status, classname=classname, test_name=test_name))

    suite_elements: list[ET.Element]
    if root.tag == "testsuites":
        suite_elements = list(root.findall("testsuite"))
    else:
        suite_elements = [root]

    summary = _RegressionSuiteSummary()
    for suite in suite_elements:
        summary.tests += _read_int_attribute(suite, "tests")
        summary.failures += _read_int_attribute(suite, "failures")
        summary.errors += _read_int_attribute(suite, "errors")
        summary.skipped += _read_int_attribute(suite, "skipped")

    if summary.tests == 0:
        summary.tests = len(rows)
    if summary.failures == 0 and summary.errors == 0 and rows:
        summary.failures = sum(1 for row in rows if row.status == "FAIL")
    if summary.skipped == 0 and rows:
        summary.skipped = sum(1 for row in rows if row.status == "SKIP")
    return rows, summary


def _format_regression_suite_summary(summary: _RegressionSuiteSummary, validator_code: int) -> str:
    if validator_code == 0 and not summary.has_failures:
        return f"PASS: unit: {summary.tests} tests"

    parts = [f"FAIL: unit: {summary.tests} tests"]
    if summary.failures:
        parts.append(f"{summary.failures} failed")
    elif validator_code != 0:
        parts.append("0 failed")
    if summary.errors:
        parts.append(f"{summary.errors} errors")
    if summary.skipped:
        parts.append(f"{summary.skipped} skipped")
    return ", ".join(parts)


def _format_regression_report(
    *,
    started_at: str,
    report_path: Path,
    fingerprint_line: str,
    command: list[str],
    validator_code: int,
    pytest_return_code: int,
    rows: list[_RegressionTestRow],
    summary: _RegressionSuiteSummary,
    stdout: str,
    stderr: str,
    xml_path: Path | None,
) -> str:
    report_lines: list[str] = [
        f"JARVISv7 Backend Regression Validation started at {started_at}",
        f"Report File: {_relative_report_path(report_path)}",
        f"Host Fingerprint: {fingerprint_line}",
        f"Pytest Command: {' '.join(command)}",
        f"Pytest Return Code: {pytest_return_code}",
        f"Validator Return Code: {validator_code}",
    ]
    if xml_path is not None:
        report_lines.append(f"JUnit XML: {_relative_report_path(xml_path)}")
    report_lines.extend(
        [
            "",
            "UNIT TESTS",
        ]
    )

    if rows:
        for row in rows:
            report_lines.append(f"[{row.status}] {row.status}: {row.classname}::{row.test_name}")
    else:
        report_lines.append("No JUnit XML test rows were produced.")

    suite_summary = _format_regression_suite_summary(summary, validator_code)
    report_lines.extend(
        [
            suite_summary,
            "",
            "VALIDATION SUMMARY",
            "[INVARIANTS]",
            f"UNIT={'PASS' if validator_code == 0 else 'FAIL'}",
            "[PASS] JARVISv7 backend regression is validated!"
            if validator_code == 0
            else "[FAIL] Validation failed - see suite output above",
            "",
            "PYTEST STDOUT",
            stdout.rstrip("\n") or "<empty>",
            "",
            "PYTEST STDERR",
            stderr.rstrip("\n") or "<empty>",
        ]
    )
    return "\n".join(report_lines) + "\n"


def _pytest_available() -> bool:
    return importlib.util.find_spec("pytest") is not None


def _build_pytest_command(targets: list[str], marker_expr: str | None = None) -> list[str]:
    command = [sys.executable, "-m", "pytest", "-q"]
    if marker_expr:
        command.extend(["-m", marker_expr])
    command.extend(targets)
    return command


def _run_pytest(targets: list[str], marker_expr: str | None = None) -> int:
    if not _pytest_available():
        print("pytest is not installed in backend/.venv")
        return 3

    command = _build_pytest_command(targets, marker_expr=marker_expr)
    completed = subprocess.run(command, cwd=APP_REPO_ROOT, check=False)
    if completed.returncode == 5:
        return 2
    return completed.returncode


def _run_pytest_with_report(
    command_name: str,
    targets: list[str],
    marker_expr: str | None = None,
    *,
    report_directory: Path = VALIDATION_DIR,
    fingerprint_line: str,
) -> int:
    if not _pytest_available():
        message = "pytest is not installed in backend/.venv"
        report = "\n".join(
            [
                f"title: validate_backend {command_name}",
                f"timestamp_utc: {_current_timestamp()}",
                f"host_fingerprint: {fingerprint_line}",
                f"command: {' '.join(_build_pytest_command(targets, marker_expr=marker_expr))}",
                "return_code: 3",
                "summary: SKIPPED",
                "stdout:",
                message,
                "stderr:",
                "",
            ]
        )
        _write_report(report_directory, command_name, report)
        print(message)
        return 3

    command = _build_pytest_command(targets, marker_expr=marker_expr)
    completed = subprocess.run(
        command,
        cwd=APP_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.stdout:
        sys.stdout.write(completed.stdout)
    if completed.stderr:
        sys.stderr.write(completed.stderr)

    validator_code = 2 if completed.returncode == 5 else completed.returncode
    summary = {0: "PASS", 1: "FAIL", 2: "SKIPPED", 3: "ENVIRONMENT_UNSATISFIED"}.get(
        validator_code,
        "FAIL",
    )
    report = "\n".join(
        [
            f"title: validate_backend {command_name}",
            f"timestamp_utc: {_current_timestamp()}",
            f"host_fingerprint: {fingerprint_line}",
            f"command: {' '.join(command)}",
            f"subprocess_return_code: {completed.returncode}",
            f"validator_return_code: {validator_code}",
            f"summary: {summary}",
            "stdout:",
            completed.stdout.rstrip("\n"),
            "stderr:",
            completed.stderr.rstrip("\n"),
            "",
        ]
    )
    _write_report(report_directory, command_name, report)
    return validator_code


def _runtime_marker_expr(families: str | None, devices: str | None) -> str:
    clauses: list[str] = ["live"]
    if families:
        family_terms = [item.strip() for item in families.split(",") if item.strip()]
        if family_terms:
            clauses.append("(" + " or ".join(family_terms) + ")")
    if devices:
        device_terms = [
            item.strip() for item in devices.split(",") if item.strip() and item.strip() != "cpu"
        ]
        if device_terms:
            clauses.append("(" + " or ".join(device_terms) + ")")
    return " and ".join(clauses)


def _regression_targets() -> list[str]:
    targets = ["backend/tests/unit/hardware", "backend/tests/unit/scripts"]
    runtime_hardware = APP_REPO_ROOT / "backend" / "tests" / "runtime" / "hardware"
    if runtime_hardware.exists() and any(runtime_hardware.glob("test_*.py")):
        targets.append("backend/tests/runtime/hardware")
    return targets


def _parse_args(argv: list[str]) -> argparse.Namespace:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--verbose", action="store_true")
    shared.add_argument("--dry-run", action="store_true")
    shared.add_argument("--trace-to")
    shared.add_argument("--profile", action="store_true")

    parser = argparse.ArgumentParser(prog="validate_backend.py", parents=[shared])
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("profile", parents=[shared])
    subparsers.add_parser("unit", parents=[shared])
    subparsers.add_parser("integration", parents=[shared])

    runtime = subparsers.add_parser("runtime", parents=[shared])
    runtime.add_argument("--families")
    runtime.add_argument("--devices")

    subparsers.add_parser("regression", parents=[shared])
    subparsers.add_parser("matrix", parents=[shared])
    subparsers.add_parser("all", parents=[shared])
    subparsers.add_parser("ci", parents=[shared])
    return parser.parse_args(argv)


def _emit_profile_report(report, extras, preflight) -> int:
    payload = {
        "profile": asdict(report.profile),
        "flags": asdict(report.flags),
        "preflight": {
            "tokens": preflight.tokens,
            "dll_discovery_log": preflight.dll_discovery_log,
            "probe_errors": preflight.probe_errors,
        },
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


def _command_unit() -> int:
    return _run_pytest(["backend/tests/unit"])


def _command_integration() -> int:
    return _run_pytest(["backend/tests/integration"])


def _command_runtime(args: argparse.Namespace) -> int:
    marker_expr = _runtime_marker_expr(args.families, args.devices)
    return _run_pytest(["backend/tests/runtime"], marker_expr=marker_expr)


def _command_regression() -> int:
    return _run_pytest(_regression_targets())


def _command_matrix() -> int:
    return _run_pytest(["backend/tests/runtime/acceleration_matrix"])


def _combine_codes(codes: list[int]) -> int:
    if any(code == 3 for code in codes):
        return 3
    if any(code == 1 for code in codes):
        return 1
    if any(code == 2 for code in codes):
        return 2
    return 0


def _command_all() -> int:
    return _combine_codes([_command_unit(), _command_integration(), _command_regression()])


def _command_ci() -> int:
    marker_expr = "not live"
    return _combine_codes(
        [
            _run_pytest(["backend/tests/unit"], marker_expr=marker_expr),
            _run_pytest(["backend/tests/integration"], marker_expr=marker_expr),
            _run_pytest(_regression_targets(), marker_expr=marker_expr),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    configure_logging(level="DEBUG" if args.verbose else "INFO", trace_to=args.trace_to)

    report, extras, preflight = _load_context()
    readiness = _current_readiness_summary(preflight)
    fingerprint_line = _capture_host_fingerprint(report.profile, extras, readiness=readiness)
    print(fingerprint_line)

    if args.command == "profile":
        payload = {
            "profile": asdict(report.profile),
            "flags": asdict(report.flags),
            "preflight": {
                "tokens": preflight.tokens,
                "dll_discovery_log": preflight.dll_discovery_log,
                "probe_errors": preflight.probe_errors,
            },
        }
        body = "\n".join([fingerprint_line, json.dumps(payload, sort_keys=True)])
        _write_report(
            DIAGNOSTICS_DIR,
            "profile",
            "\n".join(
                [
                    "title: validate_backend profile",
                    f"timestamp_utc: {_current_timestamp()}",
                    f"host_fingerprint: {fingerprint_line}",
                    "return_code: 0",
                    "summary: PASS",
                    "stdout:",
                    body,
                    "stderr:",
                    "",
                ]
            ),
        )
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "unit":
        return _command_unit()
    if args.command == "integration":
        return _command_integration()
    if args.command == "runtime":
        return _command_runtime(args)
    if args.command == "regression":
        started_at = _current_timestamp()
        report_path = VALIDATION_DIR / f"{_timestamp_slug()}-regression.txt"
        xml_path = _regression_temp_xml_path()
        command = _build_pytest_command(_regression_targets())
        command.extend(["--junitxml", str(xml_path)])

        print(f"JARVISv7 Backend Regression Validation started at {started_at}")
        print(f"Report File: {_relative_report_path(report_path)}")
        print(f"Host Fingerprint: {fingerprint_line}")
        print(f"Pytest Command: {' '.join(command)}")

        if not _pytest_available():
            validator_code = 3
            pytest_return_code = 3
            rows, summary = [], _RegressionSuiteSummary()
            stdout = "pytest is not installed in backend/.venv"
            stderr = ""
        else:
            completed = subprocess.run(
                command,
                cwd=APP_REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            pytest_return_code = completed.returncode
            validator_code = 2 if completed.returncode == 5 else completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
            rows, summary = _collect_regression_rows(xml_path)

        if rows:
            print("UNIT TESTS")
            for row in rows:
                print(f"[{row.status}] {row.status}: {row.classname}::{row.test_name}")
        else:
            print("UNIT TESTS")
            print("No JUnit XML test rows were produced.")

        print(_format_regression_suite_summary(summary, validator_code))
        print()
        print("VALIDATION SUMMARY")
        print("[INVARIANTS]")
        print(f"UNIT={'PASS' if validator_code == 0 else 'FAIL'}")
        if validator_code == 0:
            print("[PASS] JARVISv7 backend regression is validated!")
        else:
            print("[FAIL] Validation failed - see suite output above")
        print()
        print("PYTEST STDOUT")
        print(stdout.rstrip("\n") or "<empty>")
        print()
        print("PYTEST STDERR")
        print(stderr.rstrip("\n") or "<empty>")

        report = _format_regression_report(
            started_at=started_at,
            report_path=report_path,
            fingerprint_line=fingerprint_line,
            command=command,
            validator_code=validator_code,
            pytest_return_code=pytest_return_code,
            rows=rows,
            summary=summary,
            stdout=stdout,
            stderr=stderr,
            xml_path=xml_path if xml_path.exists() else None,
        )
        _write_report_at_path(report_path, report)
        xml_path.unlink(missing_ok=True)
        return validator_code
    if args.command == "matrix":
        return _command_matrix()
    if args.command == "all":
        return _command_all()
    if args.command == "ci":
        return _command_ci()
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
