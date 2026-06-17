from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend.app.models.llm_profiles import LLMServeProfileResolution


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

    return LocalLLMSidecarCommand(
        argv=argv,
        ready=True,
        warnings=warnings,
    )


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
