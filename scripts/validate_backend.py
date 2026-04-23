from __future__ import annotations

import argparse
import importlib.util
from dataclasses import asdict
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.logging import configure_logging, emit_host_fingerprint
from backend.app.core.paths import REPO_ROOT as APP_REPO_ROOT
from backend.app.hardware.preflight import run_preflight
from backend.app.hardware.provisioning import resolve_required_extras


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


def _runtime_marker_expr(families: str | None, devices: str | None) -> str:
    clauses: list[str] = ["live"]
    if families:
        family_terms = [item.strip() for item in families.split(",") if item.strip()]
        if family_terms:
            clauses.append("(" + " or ".join(family_terms) + ")")
    if devices:
        device_terms = [item.strip() for item in devices.split(",") if item.strip()]
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
    emit_host_fingerprint(report.profile, extras, readiness=_current_readiness_summary(preflight))

    if args.command == "profile":
        return _emit_profile_report(report, extras, preflight)
    if args.command == "unit":
        return _command_unit()
    if args.command == "integration":
        return _command_integration()
    if args.command == "runtime":
        return _command_runtime(args)
    if args.command == "regression":
        return _command_regression()
    if args.command == "matrix":
        return _command_matrix()
    if args.command == "all":
        return _command_all()
    if args.command == "ci":
        return _command_ci()
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
