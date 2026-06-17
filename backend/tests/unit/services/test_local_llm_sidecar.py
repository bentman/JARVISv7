from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.models.llm_profiles import LLMServeProfileResolution
from backend.app.services.local_llm_sidecar import build_llama_server_command


def _write_file(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True)
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
        "--parallel",
        "1",
        "--cont-batching",
        "--warmup",
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
    assert command.argv[command.argv.index("--cache-ram") + 1] == "4096"


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
