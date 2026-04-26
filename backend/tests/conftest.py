from __future__ import annotations

import os
import shutil
from functools import lru_cache
from types import SimpleNamespace

import pytest

from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.hardware.preflight import PreflightResult, run_preflight
from backend.app.hardware.provisioning import resolve_required_extras


def _load_profiler():
    from backend.app.hardware.profiler import run_profiler

    return run_profiler


def _fallback_report():
    profile = HardwareProfile()
    flags = CapabilityFlags()
    return SimpleNamespace(profile=profile, flags=flags)


@lru_cache(maxsize=1)
def _profile_report():
    try:
        profiler = _load_profiler()
        return profiler()
    except Exception:
        return _fallback_report()


@lru_cache(maxsize=1)
def _preflight_report() -> PreflightResult:
    profile = _profile_report().profile
    installed_extras = resolve_required_extras(profile)
    return run_preflight(profile, installed_extras)


def _has_token(token: str) -> bool:
    return token in _preflight_report().tokens


def _observed_installed_extras() -> list[str]:
    return resolve_required_extras(_profile_report().profile)


SKIP_UNLESS_X64 = _profile_report().profile.arch != "amd64"
SKIP_UNLESS_ARM64 = _profile_report().profile.arch != "arm64"
SKIP_UNLESS_CUDA = not _has_token("ep:CUDAExecutionProvider")
SKIP_UNLESS_DIRECTML = not _has_token("ep:DmlExecutionProvider")
SKIP_UNLESS_QNN = not _has_token("ep:QNNExecutionProvider")
SKIP_UNLESS_OLLAMA = os.getenv("JARVISV7_OLLAMA_URL", "").strip() == ""
SKIP_UNLESS_REDIS = shutil.which("redis-server") is None
SKIP_UNLESS_SEARXNG = shutil.which("searxng") is None
SKIP_UNLESS_DOCKER = shutil.which("docker") is None
SKIP_UNLESS_QAIRT = os.getenv("QAIRT_SDK_PATH") is None
SKIP_UNLESS_LIVE = os.getenv("JARVISV7_LIVE_TESTS", "").strip().lower() not in {"1", "true", "yes"}


@pytest.fixture(scope="session")
def profiler_fixture():
    return _profile_report()


@pytest.fixture(scope="session")
def preflight_fixture():
    profile = _profile_report().profile
    installed_extras = _observed_installed_extras()
    return run_preflight(profile, installed_extras)
