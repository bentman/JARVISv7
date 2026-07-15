from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

import httpx
import psutil

from backend.app.models.llm_profiles import LLMServeProfileResolution

_ORIGINAL_GET = httpx.get


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
    startup_phase_durations_ms: dict[str, float] = field(default_factory=dict)


_STARTUP_PHASES = (
    "endpoint_adoption_probe",
    "stale_port_cleanup",
    "sidecar_process_launch",
    "health_readiness",
    "models_readiness",
)


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
        self._adopted_endpoint_base_url: str | None = None
        self._adopted_endpoint_reason: str | None = None
        self._startup_phase_durations_ms = _empty_startup_phase_durations()

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
        if not running and self._adopted_endpoint_base_url is not None:
            health_ready, health_reason = self._probe_adopted_endpoint()
            running = bool(health_ready)
        state = _status_state(running, self._restart_required, self._last_error)
        return self._status(
            state=state,
            running=running,
            health_ready=health_ready,
            health_reason=health_reason,
        )

    def start(self, resolution: LLMServeProfileResolution) -> LocalLLMSidecarStatus:
        return self._start(resolution, reclaim_stale_port=True)

    def _start(
        self,
        resolution: LLMServeProfileResolution,
        *,
        reclaim_stale_port: bool,
    ) -> LocalLLMSidecarStatus:
        self._startup_phase_durations_ms = _empty_startup_phase_durations()
        command = build_llama_server_command(resolution)
        if not command.ready:
            self._clear_adoption()
            self._last_resolution = resolution
            self._last_command = command
            self._last_error = command.degraded_reason
            self._restart_required = False
            return self._status(state="degraded", running=False)

        if self._is_running():
            if self._same_running_target(resolution):
                return self.status()
            self._clear_adoption()
            self._restart_required = True
            self._last_error = "restart-required"
            return self._status(state="restart-required", running=True, restart_required=True)

        # Check if endpoint is already served by an existing llama-server process
        base_url = resolution.base_url.rstrip("/")
        phase_started_at = time.monotonic()
        try:
            endpoint_ready, endpoint_reason = _probe_endpoint_healthy(base_url, resolution.model_id)
        finally:
            self._record_startup_phase("endpoint_adoption_probe", phase_started_at)
        if endpoint_ready:
            # Endpoint is already healthy - adopt it without spawning
            self._last_resolution = resolution
            self._last_command = command
            self._last_error = None
            self._restart_required = False
            self._adopted_endpoint_base_url = base_url
            self._adopted_endpoint_reason = endpoint_reason
            # Return status with running=True but no managed process
            return self._status(
                state="running",
                running=True,
                health_ready=True,
                health_reason=endpoint_reason,
            )

        # Port reclamation on start. A transition away from an adopted endpoint
        # must not reap the external server that this service does not own.
        if reclaim_stale_port:
            phase_started_at = time.monotonic()
            try:
                _, port = _host_port(resolution.base_url)
                binary_name = resolution.binary_path.name if resolution.binary_path else "llama-server"
                _reap_processes_on_port(port, binary_name, self._stop_timeout_seconds)
            except Exception:
                pass
            finally:
                self._record_startup_phase("stale_port_cleanup", phase_started_at)

        phase_started_at = time.monotonic()
        try:
            process = self._process_factory(list(command.argv))
        except Exception as exc:
            self._clear_adoption()
            self._process = None
            self._last_resolution = resolution
            self._last_command = command
            self._last_error = f"Degraded-sidecar-start-failed: {exc}"
            self._restart_required = False
            return self._status(state="degraded", running=False)
        finally:
            self._record_startup_phase("sidecar_process_launch", phase_started_at)

        self._clear_adoption()
        self._process = process
        self._last_resolution = resolution
        self._last_command = command
        self._last_error = None
        self._restart_required = False
        return self.status()

    def stop(self) -> LocalLLMSidecarStatus:
        if self._adopted_endpoint_base_url is not None and self._process is None:
            self._clear_adoption()
            self._restart_required = False
            return self._status(state="stopped", running=False)

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
        if process is not None:
            binary_path = self._last_binary_path()
        else:
            binary_path = None
        if binary_path is not None:
            self._process_reaper(binary_path, self._stop_timeout_seconds)

        # Port reclamation on stop
        port = None
        if self._last_resolution is not None:
            try:
                _, port = _host_port(self._last_resolution.base_url)
            except Exception:
                pass
        if port is not None:
            binary_path = self._last_binary_path()
            binary_name = binary_path.name if binary_path else "llama-server"
            _reap_processes_on_port(port, binary_name, self._stop_timeout_seconds)

        self._process = None
        self._clear_adoption()
        self._restart_required = False
        return self._status(state="stopped", running=False)

    def restart(self, resolution: LLMServeProfileResolution) -> LocalLLMSidecarStatus:
        adopted_endpoint = self._adopted_endpoint_base_url is not None and self._process is None
        self.stop()
        return self._start(resolution, reclaim_stale_port=not adopted_endpoint)

    def update_startup_phase_durations(self, durations_ms: dict[str, float]) -> None:
        for phase in ("health_readiness", "models_readiness"):
            if phase in durations_ms:
                self._startup_phase_durations_ms[phase] = max(0.0, float(durations_ms[phase]))

    def _record_startup_phase(self, phase: str, started_at: float) -> None:
        self._startup_phase_durations_ms[phase] = _elapsed_ms(started_at)

    def _is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _clear_adoption(self) -> None:
        self._adopted_endpoint_base_url = None
        self._adopted_endpoint_reason = None

    def _probe_adopted_endpoint(self) -> tuple[bool, str]:
        if self._adopted_endpoint_base_url is None:
            return False, "no adopted endpoint"
        if self._health_probe is not None:
            try:
                return self._health_probe(self._adopted_endpoint_base_url)
            except Exception as exc:
                return False, str(exc)
        target_model_id = self._last_resolution.model_id if self._last_resolution else None
        return _probe_endpoint_healthy(self._adopted_endpoint_base_url, target_model_id)

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
            startup_phase_durations_ms=dict(self._startup_phase_durations_ms),
        )


def _empty_startup_phase_durations() -> dict[str, float]:
    return {phase: 0.0 for phase in _STARTUP_PHASES}


def _elapsed_ms(started_at: float) -> float:
    return max(0.0, (time.monotonic() - started_at) * 1000.0)


def _probe_endpoint_healthy(base_url: str, target_model_id: str | None = None) -> tuple[bool, str]:
    """Probe if the llama.cpp endpoint is already healthy and serving the target model if specified.

    Returns (True, reason) if endpoint responds to /health or /v1/models (and matches target_model_id if provided).
    Returns (False, reason) if endpoint is unreachable, unhealthy, or model mismatch.
    This is a non-blocking single-probe check (no retry loop).
    """
    url = base_url.rstrip("/")
    with httpx.Client() as client:
        if target_model_id is not None:
            try:
                # Must query /v1/models to verify the model ID matches
                get_func = httpx.get if httpx.get is not _ORIGINAL_GET else client.get
                models = get_func(f"{url}/v1/models", timeout=1.0)
                models.raise_for_status()
                payload = models.json()
                if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                    model_ids: list[str] = []
                    for item in payload["data"]:
                        if isinstance(item, dict) and "id" in item:
                            mid = item["id"]
                            if isinstance(mid, str):
                                model_ids.append(mid)
                    
                    matched = False
                    for mid in model_ids:
                        if mid == target_model_id:
                            matched = True
                            break
                        # Basename or name matching to handle paths or extensions
                        try:
                            mid_path = Path(mid)
                            if mid_path.name == target_model_id or mid_path.stem == target_model_id:
                                matched = True
                                break
                            target_path = Path(target_model_id)
                            if target_path.name == mid or target_path.stem == mid:
                                matched = True
                                break
                        except Exception:
                            pass
                        if target_model_id in mid or mid in target_model_id:
                            matched = True
                            break

                    if matched:
                        return True, f"endpoint healthy at {base_url} serving model {target_model_id}"
                    return False, f"endpoint model mismatch: expected {target_model_id}, found {model_ids}"
                return False, "endpoint returned invalid /v1/models payload"
            except Exception as exc:
                return False, f"endpoint unreachable or models check failed: {exc}"

        try:
            # Try /health first (quickest check)
            get_func = httpx.get if httpx.get is not _ORIGINAL_GET else client.get
            health = get_func(f"{url}/health", timeout=1.0)
            health.raise_for_status()
            return True, f"endpoint healthy at {base_url}"
        except Exception:
            pass

        try:
            # Try /v1/models as fallback
            get_func = httpx.get if httpx.get is not _ORIGINAL_GET else client.get
            models = get_func(f"{url}/v1/models", timeout=1.0)
            models.raise_for_status()
            payload = models.json()
            if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                return True, f"endpoint healthy at {base_url}"
            return False, "endpoint returned invalid /v1/models payload"
        except Exception as exc:
            return False, f"endpoint unreachable: {exc}"


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


def _reap_processes_on_port(port: int, binary_name: str, timeout_seconds: float) -> None:
    matches: list[psutil.Process] = []
    current_pid = psutil.Process().pid
    for process in psutil.process_iter(["pid", "name"]):
        if process.info.get("pid") == current_pid:
            continue
        name = process.info.get("name")
        if not name:
            continue
        proc_name_norm = name.lower().removesuffix(".exe")
        bin_name_norm = binary_name.lower().removesuffix(".exe")
        if proc_name_norm != bin_name_norm:
            continue
        try:
            conns = process.connections(kind="inet")
            for conn in conns:
                if conn.laddr and conn.laddr.port == port:
                    matches.append(process)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

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
