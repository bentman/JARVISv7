from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.logging import configure_logging, emit_host_fingerprint
from backend.app.services.startup_context import load_startup_context, readiness_summary


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="run_backend.py")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--trace-to", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reload", action="store_true")
    return parser.parse_args(argv)


def _emit_fallback_fingerprint(out: TextIO) -> None:
    profile = type("Profile", (), {"arch": "unknown", "profiled_at": "unknown"})()
    emit_host_fingerprint(profile, [], readiness="profile-failed", out=out)


def main(argv: list[str] | None = None, out: TextIO | None = None) -> int:
    output = out or sys.stdout
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging(level="DEBUG" if args.verbose else "INFO", trace_to=args.trace_to)

    try:
        context = load_startup_context()
    except Exception as exc:
        _emit_fallback_fingerprint(output)
        print(f"PROFILER_UNAVAILABLE {exc}", file=output)
        return 1

    emit_host_fingerprint(context.profile, context.extras, readiness=readiness_summary(context), out=output)
    if args.dry_run:
        print(f"run_backend dry-run host={args.host} port={args.port} reload={args.reload}", file=output)
        return 0

    import uvicorn

    uvicorn.run(
        "backend.app.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
