from __future__ import annotations

import hashlib
import importlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from backend.app.core.capabilities import HardwareProfile


@dataclass(slots=True)
class PreflightResult:
    tokens: list[str]
    dll_discovery_log: list[str]
    probe_errors: dict[str, str]


_CACHE: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[str, str], ...]]] = {}
_Snapshot = tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[str, str], ...]]


_EXTRA_IMPORTS: dict[str, tuple[str, ...]] = {
    "hw-cpu-base": (),
    "hw-x64-base": ("onnxruntime", "onnx_asr", "kokoro_onnx", "openwakeword"),
    "hw-arm64-base": ("onnxruntime", "onnx_asr", "kokoro_onnx", "openwakeword"),
    "hw-gpu-nvidia-cuda": ("onnxruntime",),
    "hw-gpu-amd": ("onnxruntime",),
    "hw-gpu-intel": ("onnxruntime",),
    "hw-npu-qualcomm-qnn": ("onnxruntime",),
    "hw-wake-porcupine": ("pvporcupine",),
    "dev": ("pytest", "pytest_cov", "pytest_asyncio", "ruff", "mypy", "pre_commit"),
}


def _profile_cache_key(profile: HardwareProfile, installed_extras: list[str]) -> str:
    payload = asdict(profile).copy()
    payload.pop("profile_id", None)
    payload.pop("profiled_at", None)
    canonical = json.dumps(
        {"profile": payload, "installed_extras": list(installed_extras)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _snapshot(result: PreflightResult) -> _Snapshot:
    return (
        tuple(result.tokens),
        tuple(result.dll_discovery_log),
        tuple(result.probe_errors.items()),
    )


def _restore(snapshot: _Snapshot) -> PreflightResult:
    tokens, dll_discovery_log, probe_error_items = snapshot
    return PreflightResult(
        tokens=list(tokens),
        dll_discovery_log=list(dll_discovery_log),
        probe_errors=dict(probe_error_items),
    )


def _import_names_for_extra(extra: str) -> tuple[str, ...]:
    return _EXTRA_IMPORTS.get(extra, ())


def _ordered_import_names(installed_extras: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for extra in installed_extras:
        for import_name in _import_names_for_extra(extra):
            if import_name not in seen:
                ordered.append(import_name)
                seen.add(import_name)
    return ordered


def _available_dll_directory_api():
    return getattr(os, "add_dll_directory", None)


def _candidate_dll_roots(profile: HardwareProfile) -> list[tuple[str, Path]]:
    if profile.os_name != "windows":
        return []

    candidates: list[tuple[str, Path]] = []
    if profile.gpu_vendor == "nvidia" and profile.cuda_available:
        for env_name in ("CUDA_PATH", "CUDA_PATH_V12_0", "CUDA_PATH_V11_8"):
            env_value = os.getenv(env_name)
            if env_value:
                candidates.append(("cuda", Path(env_value)))
                break
    if profile.npu_vendor == "qualcomm":
        env_value = os.getenv("QAIRT_SDK_PATH")
        if env_value:
            candidates.append(("qairt", Path(env_value)))
    return candidates


def _bootstrap_dll_root(
    label: str,
    root: Path,
    tokens: list[str],
    dll_discovery_log: list[str],
) -> None:
    dll_api = _available_dll_directory_api()
    if not root.exists():
        dll_discovery_log.append(f"{label}:missing:{root}")
        return

    discovery_paths = [root, root / "bin", root / "lib"]
    added = False
    for path in discovery_paths:
        if not path.exists():
            continue
        try:
            if dll_api is not None:
                dll_api(str(path))
            added = True
            dll_discovery_log.append(f"{label}:added:{path}")
        except Exception as exc:
            dll_discovery_log.append(f"{label}:failed:{path}:{exc}")

    if added:
        token = f"dll:{label}"
        if token not in tokens:
            tokens.append(token)


def _bootstrap_windows_dlls(
    profile: HardwareProfile,
    tokens: list[str],
    dll_discovery_log: list[str],
) -> None:
    for label, root in _candidate_dll_roots(profile):
        _bootstrap_dll_root(label, root, tokens, dll_discovery_log)


def _probe_imports(
    installed_extras: list[str],
    tokens: list[str],
    probe_errors: dict[str, str],
) -> None:
    for import_name in _ordered_import_names(installed_extras):
        token = f"import:{import_name}"
        try:
            importlib.import_module(import_name)
        except Exception as exc:
            tokens.append(f"{token}:MISSING")
            probe_errors[import_name] = str(exc)
        else:
            tokens.append(token)


def _probe_execution_providers(tokens: list[str], probe_errors: dict[str, str]) -> None:
    try:
        onnxruntime = importlib.import_module("onnxruntime")
    except Exception as exc:
        probe_errors["onnxruntime.providers"] = str(exc)
        return

    try:
        providers = list(onnxruntime.get_available_providers())
    except Exception as exc:
        probe_errors["onnxruntime.providers"] = str(exc)
        return

    for provider in providers:
        token = f"ep:{provider}"
        if token not in tokens:
            tokens.append(token)


def run_preflight(profile: HardwareProfile, installed_extras: list[str]) -> PreflightResult:
    cache_key = _profile_cache_key(profile, installed_extras)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return _restore(cached)

    tokens: list[str] = []
    dll_discovery_log: list[str] = []
    probe_errors: dict[str, str] = {}

    _bootstrap_windows_dlls(profile, tokens, dll_discovery_log)
    _probe_imports(installed_extras, tokens, probe_errors)

    if "import:onnxruntime" in tokens:
        _probe_execution_providers(tokens, probe_errors)

    result = PreflightResult(
        tokens=tokens,
        dll_discovery_log=dll_discovery_log,
        probe_errors=probe_errors,
    )
    _CACHE[cache_key] = _snapshot(result)
    return _restore(_CACHE[cache_key])
