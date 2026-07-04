from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from backend.app.models.llm_profiles import LLMServeProfileResolution
from backend.app.services import local_llm_sidecar
from backend.app.services.local_llm_sidecar import LocalLLMSidecarService, build_llama_server_command


class _FakeProcess:
    def __init__(self, pid: int = 1234) -> None:
        self.pid = pid
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def poll(self) -> int | None:
        return 0 if self.terminated or self.killed else None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        return 0

    def kill(self) -> None:
        self.killed = True


class _SlowStopProcess(_FakeProcess):
    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        if self.terminated and not self.killed:
            raise subprocess.TimeoutExpired(cmd="llama-server", timeout=timeout)
        return 0


def _write_file(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _resolution(
    tmp_path: Path,
    *,
    profile_id: str = "windows_amd64_cpu",
    accelerator: str = "cpu",
    base_url: str = "http://127.0.0.1:8080",
    binary_exists: bool = True,
    model_exists: bool = True,
    launch: dict[str, object] | None = None,
) -> LLMServeProfileResolution:
    binary_path = tmp_path / "bin" / profile_id / "llama-server.exe"
    model_path = tmp_path / "models" / "assistant-small-q4" / "model.gguf"
    if binary_exists:
        _write_file(binary_path, b"exe")
    if model_exists:
        _write_file(model_path, b"gguf")
    return LLMServeProfileResolution(
        model_id="assistant-small-q4",
        route="voice_chat",
        serve_profile_id=profile_id,
        local_model_path=model_path,
        binary_path=binary_path,
        base_url=base_url,
        accelerator=accelerator,
        launch=launch
        if launch is not None
        else {
            "ctx_size": 4096,
            "threads": "auto",
            "threads_batch": "auto",
            "batch_size": 1024,
            "ubatch_size": 256,
            "gpu_layers": 0,
            "cache_type_k": "f16",
            "cache_type_v": "f16",
            "parallel": 1,
            "cont_batching": True,
            "warmup": True,
        },
        generation_defaults={"temperature": 0.4},
        selected_reason=f"selected current-host CPU serve profile {profile_id}",
    )


def test_builds_windows_amd64_cpu_argv_without_launching(tmp_path: Path) -> None:
    resolution = _resolution(tmp_path)

    command = build_llama_server_command(resolution)

    assert command.ready is True
    assert command.degraded_reasons == []
    assert command.warnings == []
    assert command.argv == [
        str(resolution.binary_path),
        "--model",
        str(resolution.local_model_path),
        "--host",
        "127.0.0.1",
        "--port",
        "8080",
        "--ctx-size",
        "4096",
        "--threads",
        "-1",
        "--threads-batch",
        "-1",
        "--batch-size",
        "1024",
        "--ubatch-size",
        "256",
        "--gpu-layers",
        "0",
        "--cache-type-k",
        "f16",
        "--cache-type-v",
        "f16",
        "--warmup",
        "--cache-ram",
        "0",
        "--parallel",
        "1",
        "--no-cont-batching",
    ]


def test_builds_windows_arm64_cpu_argv(tmp_path: Path) -> None:
    resolution = _resolution(
        tmp_path,
        profile_id="windows_arm64_cpu",
        launch={
            "ctx_size": 4096,
            "gpu_layers": 0,
            "cache_ram_mb": 4096,
            "parallel": 1,
            "cont_batching": True,
            "warmup": True,
        },
    )

    command = build_llama_server_command(resolution)

    assert command.ready is True
    assert command.argv[:7] == [
        str(resolution.binary_path),
        "--model",
        str(resolution.local_model_path),
        "--host",
        "127.0.0.1",
        "--port",
        "8080",
    ]
    assert "--cache-ram" in command.argv
    assert command.argv[command.argv.index("--cache-ram") + 1] == "0"
    assert "--no-cont-batching" in command.argv
    assert "--cont-batching" not in command.argv


def test_builds_amd64_cuda_argv_when_files_exist(tmp_path: Path) -> None:
    resolution = _resolution(
        tmp_path,
        profile_id="windows_amd64_cuda",
        accelerator="gpu.cuda",
        launch={
            "ctx_size": 4096,
            "gpu_layers": "auto",
            "split_mode": "layer",
            "main_gpu": 0,
            "flash_attn": "auto",
            "cache_type_k": "f16",
            "cache_type_v": "f16",
            "cache_ram_mb": 8192,
        },
    )

    command = build_llama_server_command(resolution)

    assert command.ready is True
    assert "--gpu-layers" in command.argv
    assert command.argv[command.argv.index("--gpu-layers") + 1] == "auto"
    assert "--split-mode" in command.argv
    assert "--main-gpu" in command.argv
    assert "--flash-attn" in command.argv
    assert command.argv[command.argv.index("--cache-ram") + 1] == "0"
    assert command.argv[command.argv.index("--parallel") + 1] == "1"
    assert "--no-cont-batching" in command.argv


def test_builds_arm64_adreno_opencl_argv_without_hardcoded_device(tmp_path: Path) -> None:
    resolution = _resolution(
        tmp_path,
        profile_id="windows_arm64_gpu_qualcomm_adreno_opencl",
        accelerator="gpu.opencl.adreno",
        launch={
            "ctx_size": 4096,
            "threads": "auto",
            "threads_batch": "auto",
            "batch_size": 2048,
            "ubatch_size": 512,
            "gpu_layers": "auto",
            "cache_type_k": "f16",
            "cache_type_v": "f16",
            "cache_ram_mb": 4096,
            "parallel": 1,
            "cont_batching": True,
            "warmup": True,
        },
    )

    command = build_llama_server_command(resolution)

    assert command.ready is True
    assert "--gpu-layers" in command.argv
    assert command.argv[command.argv.index("--gpu-layers") + 1] == "auto"
    assert "--device" not in command.argv
    assert command.argv[command.argv.index("--cache-ram") + 1] == "0"
    assert command.argv[command.argv.index("--parallel") + 1] == "1"
    assert "--no-cont-batching" in command.argv


def test_managed_launch_isolation_overrides_profile_cache_and_slot_reuse(tmp_path: Path) -> None:
    resolution = _resolution(
        tmp_path,
        launch={
            "ctx_size": 4096,
            "cache_ram_mb": 4096,
            "parallel": 4,
            "cont_batching": True,
        },
    )

    command = build_llama_server_command(resolution)

    assert command.ready is True
    assert command.warnings == []
    assert command.argv.count("--cache-ram") == 1
    assert command.argv[command.argv.index("--cache-ram") + 1] == "0"
    assert command.argv.count("--parallel") == 1
    assert command.argv[command.argv.index("--parallel") + 1] == "1"
    assert "--no-cont-batching" in command.argv
    assert "--cont-batching" not in command.argv


def test_arm64_qnn_missing_binary_closes_as_degraded(tmp_path: Path) -> None:
    command = build_llama_server_command(
        _resolution(
            tmp_path,
            profile_id="windows_arm64_qnn",
            accelerator="npu.qnn",
            binary_exists=False,
            launch={
                "ctx_size": 4096,
                "device": "qnn",
                "cache_ram_mb": 4096,
            },
        )
    )

    assert command.ready is False
    assert command.argv == []
    assert command.degraded_reasons == ["Degraded-no-sidecar-binary"]


def test_missing_model_path_closes_as_degraded(tmp_path: Path) -> None:
    command = build_llama_server_command(_resolution(tmp_path, model_exists=False))

    assert command.ready is False
    assert command.argv == []
    assert command.degraded_reasons == ["Degraded-no-local-model-artifact"]


def test_missing_binary_and_model_paths_close_as_degraded(tmp_path: Path) -> None:
    command = build_llama_server_command(
        _resolution(tmp_path, binary_exists=False, model_exists=False)
    )

    assert command.ready is False
    assert command.argv == []
    assert command.degraded_reasons == [
        "Degraded-no-sidecar-binary",
        "Degraded-no-local-model-artifact",
    ]


def test_unsupported_launch_keys_are_reported_without_silent_noop(tmp_path: Path) -> None:
    command = build_llama_server_command(
        _resolution(
            tmp_path,
            launch={
                "ctx_size": 4096,
                "unsupported_future_flag": "value",
                "threads": ["bad"],
            },
        )
    )

    assert command.ready is True
    assert command.warnings == [
        "unsupported launch key: unsupported_future_flag",
        "unsupported launch value: threads=['bad']",
    ]
    assert "--ctx-size" in command.argv
    assert "--threads" not in command.argv


def test_invalid_base_url_fails_before_command_is_returned(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid llama.cpp base URL"):
        build_llama_server_command(_resolution(tmp_path, base_url="not-a-url"))


def test_lifecycle_start_uses_mocked_process_creation_and_records_status(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    process = _FakeProcess(pid=2468)
    service = LocalLLMSidecarService(process_factory=lambda argv: calls.append(argv) or process)
    resolution = _resolution(tmp_path)

    status = service.start(resolution)

    assert status.state == "running"
    assert status.running is True
    assert status.pid == 2468
    assert status.model_id == "assistant-small-q4"
    assert status.serve_profile_id == "windows_amd64_cpu"
    assert status.last_command == calls[0]
    assert calls[0][0] == str(resolution.binary_path)


def test_default_process_factory_uses_binary_parent_as_working_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    binary_path = _write_file(tmp_path / "runtime" / "llama-server.exe")

    class DummyProcess:
        pid = 123

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def kill(self) -> None:
            return None

    def fake_popen(argv: list[str], *, cwd: Path | None = None) -> DummyProcess:
        captured["argv"] = argv
        captured["cwd"] = cwd
        return DummyProcess()

    monkeypatch.setattr(local_llm_sidecar.subprocess, "Popen", fake_popen)

    process = local_llm_sidecar._default_process_factory([str(binary_path), "--help"])

    assert process.pid == 123
    assert captured["argv"] == [str(binary_path), "--help"]
    assert captured["cwd"] == binary_path.parent


def test_lifecycle_start_is_idempotent_for_same_running_profile(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    service = LocalLLMSidecarService(
        process_factory=lambda argv: calls.append(argv) or _FakeProcess(pid=1111)
    )
    resolution = _resolution(tmp_path)

    first = service.start(resolution)
    second = service.start(resolution)

    assert first.state == "running"
    assert second.state == "running"
    assert second.pid == 1111
    assert len(calls) == 1


def test_lifecycle_stop_is_idempotent(tmp_path: Path) -> None:
    process = _FakeProcess()
    service = LocalLLMSidecarService(process_factory=lambda argv: process)
    service.start(_resolution(tmp_path))

    stopped = service.stop()
    stopped_again = service.stop()

    assert process.terminated is True
    assert process.wait_calls == 1
    assert stopped.state == "stopped"
    assert stopped.running is False
    assert stopped_again.state == "stopped"
    assert stopped_again.running is False


def test_lifecycle_stop_reaps_selected_binary_process(tmp_path: Path) -> None:
    process = _FakeProcess()
    reaped: list[tuple[Path, float]] = []
    service = LocalLLMSidecarService(
        process_factory=lambda argv: process,
        process_reaper=lambda path, timeout: reaped.append((path, timeout)),
        stop_timeout_seconds=3.0,
    )
    resolution = _resolution(tmp_path)
    service.start(resolution)

    stopped = service.stop()

    assert process.terminated is True
    assert reaped == [(resolution.binary_path, 3.0)]
    assert stopped.state == "stopped"
    assert stopped.running is False


def test_lifecycle_stop_reaps_even_when_launcher_handle_exited(tmp_path: Path) -> None:
    process = _FakeProcess()
    reaped: list[Path] = []
    service = LocalLLMSidecarService(
        process_factory=lambda argv: process,
        process_reaper=lambda path, timeout: reaped.append(path),
    )
    resolution = _resolution(tmp_path, profile_id="windows_arm64_cpu")
    service.start(resolution)
    process.terminated = True

    stopped = service.stop()

    assert process.wait_calls == 0
    assert reaped == [resolution.binary_path]
    assert stopped.state == "stopped"
    assert stopped.running is False


def test_lifecycle_stop_kills_process_when_terminate_times_out(tmp_path: Path) -> None:
    process = _SlowStopProcess()
    service = LocalLLMSidecarService(process_factory=lambda argv: process)
    service.start(_resolution(tmp_path))

    stopped = service.stop()

    assert process.terminated is True
    assert process.killed is True
    assert process.wait_calls == 2
    assert stopped.state == "stopped"
    assert stopped.running is False


def test_lifecycle_start_failure_reports_degraded_reason(tmp_path: Path) -> None:
    def fail_start(argv: list[str]) -> _FakeProcess:
        raise RuntimeError("spawn failed")

    service = LocalLLMSidecarService(process_factory=fail_start)

    status = service.start(_resolution(tmp_path))

    assert status.state == "degraded"
    assert status.running is False
    assert status.degraded_reason == "Degraded-sidecar-start-failed: spawn failed"
    assert status.last_error == "Degraded-sidecar-start-failed: spawn failed"


def test_lifecycle_start_with_missing_command_inputs_reports_degraded_without_spawn(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    service = LocalLLMSidecarService(
        process_factory=lambda argv: calls.append(argv) or _FakeProcess()
    )

    status = service.start(_resolution(tmp_path, binary_exists=False))

    assert status.state == "degraded"
    assert status.running is False
    assert status.degraded_reason == "Degraded-no-sidecar-binary"
    assert calls == []


def test_lifecycle_changed_profile_reports_restart_required(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    service = LocalLLMSidecarService(
        process_factory=lambda argv: calls.append(argv) or _FakeProcess(pid=3333)
    )
    service.start(_resolution(tmp_path, profile_id="windows_amd64_cpu"))

    status = service.start(_resolution(tmp_path, profile_id="windows_arm64_cpu"))

    assert status.state == "restart-required"
    assert status.running is True
    assert status.restart_required is True
    assert status.degraded_reason == "restart-required"
    assert len(calls) == 1


def test_lifecycle_restart_replaces_running_process_deterministically(tmp_path: Path) -> None:
    processes = [_FakeProcess(pid=1001), _FakeProcess(pid=1002)]
    calls: list[list[str]] = []

    def factory(argv: list[str]) -> _FakeProcess:
        calls.append(argv)
        return processes[len(calls) - 1]

    service = LocalLLMSidecarService(process_factory=factory)
    service.start(_resolution(tmp_path, profile_id="windows_amd64_cpu"))

    status = service.restart(_resolution(tmp_path, profile_id="windows_arm64_cpu"))

    assert processes[0].terminated is True
    assert status.state == "running"
    assert status.pid == 1002
    assert status.serve_profile_id == "windows_arm64_cpu"
    assert len(calls) == 2


def test_lifecycle_status_delegates_health_probe_when_running(tmp_path: Path) -> None:
    service = LocalLLMSidecarService(
        process_factory=lambda argv: _FakeProcess(),
        health_probe=lambda base_url: (True, f"healthy:{base_url}"),
    )
    resolution = _resolution(tmp_path, base_url="http://127.0.0.1:18080")

    service.start(resolution)
    status = service.status()

    assert status.health_ready is True
    assert status.health_reason == "healthy:http://127.0.0.1:18080"
