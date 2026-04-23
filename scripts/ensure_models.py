from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.logging import configure_logging, emit_host_fingerprint
from backend.app.hardware.provisioning import resolve_required_extras


def _load_profiler():
    from backend.app.hardware.profiler import run_profiler

    return run_profiler


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ensure_models.py")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--trace-to")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--family")
    parser.add_argument("--model")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    configure_logging(level="DEBUG" if args.verbose else "INFO", trace_to=args.trace_to)
    profiler = _load_profiler()
    report = profiler()
    extras = resolve_required_extras(report.profile)
    emit_host_fingerprint(report.profile, extras, readiness="models-stub")
    print(json.dumps({"status": "no_models_required_in_slice_a"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
