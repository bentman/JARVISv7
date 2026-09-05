from __future__ import annotations

import os
from pathlib import Path

import pytest


def symlink_or_skip(source: Path, target: Path) -> None:
    try:
        target.symlink_to(source)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("requires Windows symlink privileges or Developer Mode")
        raise
