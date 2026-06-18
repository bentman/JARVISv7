from __future__ import annotations

import shutil
import time
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import httpx
import psutil
import pytest

from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.core.settings import load_settings
from backend.app.hardware.preflight import PreflightResult, run_preflight
from backend.app.hardware.provisioning import resolve_required_extras
from backend.app.models.llm_profiles import resolve_llm_serve_profile
from backend.app.services.local_llm_sidecar import LocalLLMSidecarService


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


def ollama_base_url() -> str:
    return load_settings().ollama_base_url.strip()


@lru_cache(maxsize=1)
def _settings():
    return load_settings()


def llama_cpp_base_url() -> str:
    return _settings().llama_cpp_base_url.strip()


def llama_cpp_model_name() -> str | None:
    model_name = _settings().llama_cpp_model_name
    return model_name.strip() if model_name else None


SKIP_UNLESS_X64 = _profile_report().profile.arch != "amd64"
SKIP_UNLESS_ARM64 = _profile_report().profile.arch != "arm64"
SKIP_UNLESS_CUDA = not _has_token("ep:CUDAExecutionProvider")
SKIP_UNLESS_DIRECTML = not _has_token("ep:DmlExecutionProvider")
SKIP_UNLESS_QNN = not _has_token("ep:QNNExecutionProvider")
SKIP_UNLESS_OLLAMA = ollama_base_url() == ""
SKIP_UNLESS_PORCUPINE = not bool(_settings().picovoice_access_key)
SKIP_UNLESS_REDIS = shutil.which("redis-server") is None
SKIP_UNLESS_SEARXNG = shutil.which("searxng") is None
SKIP_UNLESS_DOCKER = shutil.which("docker") is None
SKIP_UNLESS_QAIRT = not bool(_settings().qairt_sdk_path)
SKIP_UNLESS_LIVE = not _settings().live_tests


@pytest.fixture(scope="session")
def profiler_fixture():
    return _profile_report()


@pytest.fixture(scope="session")
def preflight_fixture():
    profile = _profile_report().profile
    installed_extras = _observed_installed_extras()
    return run_preflight(profile, installed_extras)


def _wait_for_llama_cpp_ready(base_url: str, *, timeout_seconds: float = 45.0) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout_seconds
    last_reason = "not probed"
    url = base_url.rstrip("/")
    while time.monotonic() < deadline:
        try:
            health = httpx.get(f"{url}/health", timeout=2.0)
            health.raise_for_status()
            models = httpx.get(f"{url}/v1/models", timeout=2.0)
            models.raise_for_status()
            payload = models.json()
            if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                return True, "health and /v1/models reachable"
            last_reason = "/v1/models returned invalid payload"
        except Exception as exc:
            last_reason = str(exc)
        time.sleep(0.25)
    return False, last_reason


def _processes_for_binary(binary_path) -> list[psutil.Process]:
    try:
        selected = binary_path.resolve()
    except OSError:
        selected = binary_path.absolute()
    matches: list[psutil.Process] = []
    for process in psutil.process_iter(["exe", "cmdline", "name"]):
        try:
            exe = process.info.get("exe") or process.exe()
            if exe and Path(exe).resolve() == selected:
                matches.append(process)
                continue
            cmdline = process.info.get("cmdline") or process.cmdline()
            if cmdline and Path(cmdline[0]).resolve() == selected:
                matches.append(process)
                continue
        except (OSError, psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        try:
            if process.info.get("name") == binary_path.name:
                matches.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return matches


def _kill_processes(processes: list[psutil.Process], *, timeout_seconds: float = 5.0) -> None:
    for process in processes:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    psutil.wait_procs(processes, timeout=timeout_seconds)


@pytest.fixture(scope="session")
def live_llama_cpp_sidecar(profiler_fixture, preflight_fixture):
    resolution = resolve_llm_serve_profile(
        "voice_chat",
        profiler_fixture.profile,
        preflight_fixture,
        flags=profiler_fixture.flags,
    )
    if resolution.degraded_reason:
        pytest.skip(f"requires selected local llama.cpp artifacts: {resolution.degraded_reason}")

    service = LocalLLMSidecarService()
    status = service.start(resolution)
    if not status.running:
        reason = status.degraded_reason or status.last_error or "sidecar did not start"
        pytest.fail(f"llama.cpp sidecar failed to start: {reason}")

    ready, reason = _wait_for_llama_cpp_ready(resolution.base_url)
    if not ready:
        service.stop()
        pytest.fail(f"llama.cpp sidecar failed readiness polling: {reason}")

    try:
        yield SimpleNamespace(resolution=resolution, service=service)
    finally:
        service.stop()
        leftovers = _processes_for_binary(resolution.binary_path)
        if leftovers:
            _kill_processes(leftovers)
            pytest.fail(f"llama.cpp sidecar cleanup left running processes: {[process.pid for process in leftovers]}")
