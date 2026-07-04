from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

import psutil

from backend.app.models.llm_profiles import LLMServeProfileResolution


class SidecarProcess(Protocol):
    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def kill(self) -> None: ...


ProcessFactory = Callable[[list[str]], SidecarProcess]
HealthProbe = Callable[[str], tuple[bool, str]]
ProcessReaper = Callable[[Path, float], None]


@dataclass(frozen=True, slots=True)
class LocalLLMSidecarCommand:
    argv: list[str]
    ready: bool
    degraded_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def degraded_reason(self) -> str | None:
        if not self.degraded_reasons:
            return None
        return "; ".join(self.degraded_reasons)


@dataclass(frozen=True, slots=True)
class LocalLLMSidecarStatus:
    state: str
    running: bool
    pid: int | None = None
    model_id: str | None = None
    serve_profile_id: str | None = None
    route: str | None = None
    accelerator: str | None = None
    base_url: str | None = None
    last_command: list[str] = field(default_factory=list)
    degraded_reason: str | None = None
    last_error: str | None = None
    health_ready: bool | None = None
    health_reason: str | None = None
    restart_required: bool = False


_VALUE_FLAGS: dict[str, str] = {
    "ctx_size": "--ctx-size",
    "threads": "--threads",
    "threads_batch": "--threads-batch",
    "batch_size": "--batch-size",
    "ubatch_size": "--ubatch-size",
    "gpu_layers": "--gpu-layers",
    "cache_type_k": "--cache-type-k",
    "cache_type_v": "--cache-type-v",
    "cache_ram_mb": "--cache-ram",
    "parallel": "--parallel",
    "split_mode": "--split-mode",
    "main_gpu": "--main-gpu",
    "flash_attn": "--flash-attn",
    "device": "--device",
}

_BOOL_FLAGS: dict[str, tuple[str, str]] = {
    "cont_batching": ("--cont-batching", "--no-cont-batching"),
    "warmup": ("--warmup", "--no-warmup"),
}

_TURN_ISOLATION_VALUE_FLAGS: tuple[tuple[str, str], ...] = (
    ("cache_ram_mb", "0"),
    ("parallel", "1"),
)
_TURN_ISOLATION_BOOL_FLAGS: tuple[tuple[str, bool], ...] = (
    ("cont_batching", False),
)
_TURN_ISOLATION_KEYS = {
    key for key, _value in (*_TURN_ISOLATION_VALUE_FLAGS, *_TURN_ISOLATION_BOOL_FLAGS)
}


class LocalLLMSidecarService:
    def __init__(
        self,
        *,
        process_factory: ProcessFactory | None = None,
        health_probe: HealthProbe | None = None,
        process_reaper: ProcessReaper | None = None,
        stop_timeout_seconds: float = 5.0,
    ) -> None:
        self._process_factory = process_factory or _default_process_factory
        self._health_probe = health_probe
        self._process_reaper = process_reaper or _reap_processes_for_binary
        self._stop_timeout_seconds = stop_timeout_seconds
        self._process: SidecarProcess | None = None
        self._last_resolution: LLMServeProfileResolution | None = None
        self._last_command: LocalLLMSidecarCommand | None = None
        self._last_error: str | None = None
        self._restart_required = False

    def status(self) -> LocalLLMSidecarStatus:
        running = self._is_running()
        health_ready: bool | None = None
        health_reason: str | None = None
        if running and self._last_resolution is not None and self._health_probe is not None:
            try:
                health_ready, health_reason = self._health_probe(self._last_resolution.base_url)
            except Exception as exc:
                health_ready = False
                health_reason = str(exc)
        state = _status_state(running, self._restart_required, self._last_error)
        return self._status(
            state=state,
            running=running,
            health_ready=health_ready,
            health_reason=health_reason,
        )

    def start(self, resolution: LLMServeProfileResolution) -> LocalLLMSidecarStatus:
        command = build_llama_server_command(resolution)
        if not command.ready:
            self._last_resolution = resolution
            self._last_command = command
            self._last_error = command.degraded_reason
            self._restart_required = False
            return self._status(state="degraded", running=False)

        if self._is_running():
            if self._same_running_target(resolution):
                return self.status()
            self._restart_required = True
            self._last_error = "restart-required"
            return self._status(state="restart-required", running=True, restart_required=True)

        try:
            process = self._process_factory(list(command.argv))
        except Exception as exc:
            self._process = None
            self._last_resolution = resolution
            self._last_command = command
            self._last_error = f"Degraded-sidecar-start-failed: {exc}"
            self._restart_required = False
            return self._status(state="degraded", running=False)

        self._process = process
        self._last_resolution = resolution
        self._last_command = command
        self._last_error = None
        self._restart_required = False
        return self.status()

    def stop(self) -> LocalLLMSidecarStatus:
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=self._stop_timeout_seconds)
            except (TimeoutError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=self._stop_timeout_seconds)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=self._stop_timeout_seconds)
        binary_path = self._last_binary_path()
        if binary_path is not None:
            self._process_reaper(binary_path, self._stop_timeout_seconds)
        self._process = None
        self._restart_required = False
        return self._status(state="stopped", running=False)

    def restart(self, resolution: LLMServeProfileResolution) -> LocalLLMSidecarStatus:
        self.stop()
        return self.start(resolution)

    def _is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _same_running_target(self, resolution: LLMServeProfileResolution) -> bool:
        if self._last_resolution is None:
            return False
        return _resolution_signature(self._last_resolution) == _resolution_signature(resolution)

    def _last_binary_path(self) -> Path | None:
        if self._last_command is not None and self._last_command.argv:
            return Path(self._last_command.argv[0])
        if self._last_resolution is not None:
            return self._last_resolution.binary_path
        return None

    def _status(
        self,
        *,
        state: str,
        running: bool,
        health_ready: bool | None = None,
        health_reason: str | None = None,
        restart_required: bool | None = None,
    ) -> LocalLLMSidecarStatus:
        resolution = self._last_resolution
        command = self._last_command
        process = self._process if running else None
        return LocalLLMSidecarStatus(
            state=state,
            running=running,
            pid=getattr(process, "pid", None),
            model_id=resolution.model_id if resolution else None,
            serve_profile_id=resolution.serve_profile_id if resolution else None,
            route=resolution.route if resolution else None,
            accelerator=resolution.accelerator if resolution else None,
            base_url=resolution.base_url if resolution else None,
            last_command=list(command.argv) if command else [],
            degraded_reason=self._last_error,
            last_error=self._last_error,
            health_ready=health_ready,
            health_reason=health_reason,
            restart_required=self._restart_required if restart_required is None else restart_required,
        )


def build_llama_server_command(resolution: LLMServeProfileResolution) -> LocalLLMSidecarCommand:
    degraded_reasons = _path_degraded_reasons(resolution.binary_path, resolution.local_model_path)
    warnings: list[str] = []
    if degraded_reasons:
        return LocalLLMSidecarCommand(argv=[], ready=False, degraded_reasons=degraded_reasons)

    host, port = _host_port(resolution.base_url)
    argv = [
        str(resolution.binary_path),
        "--model",
        str(resolution.local_model_path),
        "--host",
        host,
        "--port",
        str(port),
    ]

    for key, value in resolution.launch.items():
        if key in _TURN_ISOLATION_KEYS:
            continue
        if key in _VALUE_FLAGS:
            translated = _translate_value(key, value)
            if translated is None:
                warnings.append(f"unsupported launch value: {key}={value!r}")
                continue
            argv.extend([_VALUE_FLAGS[key], translated])
            continue
        if key in _BOOL_FLAGS:
            translated_flag = _translate_bool(key, value)
            if translated_flag is None:
                warnings.append(f"unsupported launch value: {key}={value!r}")
                continue
            argv.append(translated_flag)
            continue
        warnings.append(f"unsupported launch key: {key}")

    for key, value in _TURN_ISOLATION_VALUE_FLAGS:
        argv.extend([_VALUE_FLAGS[key], value])
    for key, value in _TURN_ISOLATION_BOOL_FLAGS:
        argv.append(_BOOL_FLAGS[key][0] if value else _BOOL_FLAGS[key][1])

    return LocalLLMSidecarCommand(
        argv=argv,
        ready=True,
        warnings=warnings,
    )


def _default_process_factory(argv: list[str]) -> SidecarProcess:
    binary_path = Path(argv[0])
    cwd = binary_path.parent if binary_path.parent.is_dir() else None
    return subprocess.Popen(argv, cwd=cwd)  # noqa: S603


def _reap_processes_for_binary(binary_path: Path, timeout_seconds: float) -> None:
    resolved_binary = _normalized_path(binary_path)
    matches: list[psutil.Process] = []
    current_pid = psutil.Process().pid
    for process in psutil.process_iter(["pid", "exe", "cmdline", "name"]):
        if process.info.get("pid") == current_pid:
            continue
        if _process_matches_binary(process, resolved_binary):
            matches.append(process)

    if not matches:
        return

    for process in matches:
        try:
            process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    gone, alive = psutil.wait_procs(matches, timeout=timeout_seconds)
    del gone
    for process in alive:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    psutil.wait_procs(alive, timeout=timeout_seconds)


def _process_matches_binary(process: psutil.Process, binary_path: Path) -> bool:
    try:
        exe = process.info.get("exe") or process.exe()
        if exe and _normalized_path(Path(exe)) == binary_path:
            return True
        cmdline = process.info.get("cmdline") or process.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return process.info.get("name") == binary_path.name
    if not cmdline:
        return process.info.get("name") == binary_path.name
    if _normalized_path(Path(cmdline[0])) == binary_path:
        return True
    return process.info.get("name") == binary_path.name


def _normalized_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _resolution_signature(resolution: LLMServeProfileResolution) -> tuple[str, str, str]:
    return (resolution.model_id, resolution.serve_profile_id, str(resolution.local_model_path))


def _status_state(running: bool, restart_required: bool, last_error: str | None) -> str:
    if restart_required:
        return "restart-required"
    if running:
        return "running"
    if last_error:
        return "degraded"
    return "stopped"


def _path_degraded_reasons(binary_path: Path, model_path: Path) -> list[str]:
    reasons: list[str] = []
    if not binary_path.is_file() or binary_path.stat().st_size <= 0:
        reasons.append("Degraded-no-sidecar-binary")
    if not model_path.is_file() or model_path.stat().st_size <= 0:
        reasons.append("Degraded-no-local-model-artifact")
    return reasons


def _host_port(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    if not parsed.hostname:
        raise ValueError(f"invalid llama.cpp base URL: {base_url}")
    return parsed.hostname, parsed.port or 8080


def _translate_value(key: str, value: Any) -> str | None:
    if value is None:
        return None
    if key in {"threads", "threads_batch"} and value == "auto":
        return "-1"
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        text = str(value)
        if text:
            return text
    return None


def _translate_bool(key: str, value: Any) -> str | None:
    if not isinstance(value, bool):
        return None
    enabled_flag, disabled_flag = _BOOL_FLAGS[key]
    return enabled_flag if value else disabled_flag
