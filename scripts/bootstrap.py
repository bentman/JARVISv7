from __future__ import annotations

import argparse
import json
import subprocess
import sys

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.logging import configure_logging, emit_host_fingerprint
from backend.app.hardware.preflight import run_preflight
from backend.app.hardware.provisioning import resolve_required_extras
from backend.app.hardware.readiness import (
    derive_llm_device_readiness,
    derive_stt_device_readiness,
    derive_tts_device_readiness,
    derive_wake_device_readiness,
)
from backend.app.core.paths import REPO_ROOT as APP_REPO_ROOT


def _load_profiler():
    from backend.app.hardware.profiler import run_profiler

    return run_profiler


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="bootstrap.py")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--trace-to")
    parser.add_argument("--profile", action="store_true")
    return parser.parse_args(argv)


def _checkpoint(index: int, total: int, name: str, ok: bool, reason: str) -> None:
    state = "PASS" if ok else "FAIL"
    print(f"[CHECKPOINT {index}/{total}] {name} → {state} ({reason})")


def _run_command(command: list[str], dry_run: bool) -> tuple[int, str]:
    if dry_run:
        return 0, f"dry-run: would run {' '.join(command)}"
    completed = subprocess.run(command, cwd=APP_REPO_ROOT, check=False)
    if completed.returncode == 0:
        return 0, "completed"
    return completed.returncode, f"exit={completed.returncode}"


def _emit_header(profile, extras) -> None:
    emit_host_fingerprint(profile, extras, readiness="bootstrap-start")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging(level="DEBUG" if args.verbose else "INFO", trace_to=args.trace_to)

    total = 5
    try:
        profiler = _load_profiler()
        report = profiler()
        profile = report.profile
        extras = resolve_required_extras(profile)
        _emit_header(profile, extras)
        _checkpoint(1, total, "profile", True, "run_profiler() completed")
    except Exception as exc:
        _emit_header(type("P", (), {"arch": "unknown", "profiled_at": "unknown"})(), [])
        _checkpoint(1, total, "profile", False, str(exc))
        return 1

    code, reason = _run_command(
        [sys.executable, "scripts/provision.py", "install"],
        args.dry_run,
    )
    _checkpoint(2, total, "provision", code == 0, reason)
    if code != 0:
        return code

    code, reason = _run_command(
        [sys.executable, "scripts/ensure_models.py"],
        args.dry_run,
    )
    _checkpoint(3, total, "ensure_models", code == 0, reason)
    if code != 0:
        return code

    try:
        preflight = run_preflight(profile, extras)
        stt = derive_stt_device_readiness(preflight, profile)
        tts = derive_tts_device_readiness(preflight, profile)
        llm = derive_llm_device_readiness(preflight, profile)
        wake = derive_wake_device_readiness(preflight, profile)
        reason = json.dumps(
            {
                "tokens": preflight.tokens,
                "stt": stt,
                "tts": tts,
                "llm": llm,
                "wake": wake,
            },
            sort_keys=True,
        )
        _checkpoint(4, total, "preflight", not preflight.probe_errors, reason)
        if preflight.probe_errors:
            return 1
    except Exception as exc:
        _checkpoint(4, total, "preflight", False, str(exc))
        return 1

    code, reason = _run_command(
        [sys.executable, "scripts/validate_backend.py", "profile"],
        args.dry_run,
    )
    _checkpoint(5, total, "validate_profile", code == 0, reason)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
