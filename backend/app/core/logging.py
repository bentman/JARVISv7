from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Iterable, TextIO


def configure_logging(level: str = "INFO", trace_to: str | Path | None = None) -> logging.Logger:
    logger = logging.getLogger("jarvisv7")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(stream_handler)

    if trace_to is not None:
        trace_path = Path(trace_to)
        trace_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(trace_path / "trace.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(file_handler)

    return logger


def emit_host_fingerprint(
    profile: object,
    extras: Iterable[str],
    readiness: str = "not-checked",
    out: TextIO | None = None,
) -> None:
    if out is None:
        out = sys.stdout
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    arch = getattr(profile, "arch", "unknown")
    extras_text = ",".join(extras)
    profiled_at = getattr(profile, "profiled_at", "unknown")
    print(
        (
            f"[fingerprint] arch={arch} python={python_version} "
            f"extras=[{extras_text}] readiness={readiness} profiled={profiled_at}"
        ),
        file=out,
    )
