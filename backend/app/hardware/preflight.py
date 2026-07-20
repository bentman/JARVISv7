from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from backend.app.core.capabilities import HardwareProfile
from backend.app.core.paths import REPO_ROOT


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
    "hw-npu-qualcomm-qnn": ("onnxruntime", "transformers"),
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


def _import_names_for_extra(extra: str, profile: HardwareProfile) -> tuple[str, ...]:
    return _EXTRA_IMPORTS.get(extra, ())


def _ordered_import_names(installed_extras: list[str], profile: HardwareProfile) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for extra in installed_extras:
        for import_name in _import_names_for_extra(extra, profile):
            if import_name not in seen:
                ordered.append(import_name)
                seen.add(import_name)
    return ordered


def _has_extra(installed_extras: list[str], extra: str) -> bool:
    return extra in installed_extras


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
            candidates.append(("QnnHtp", Path(env_value)))
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
    if label == "QnnHtp":
        candidate_files = [path / "QnnHtp.dll" for path in discovery_paths]
        discovered_file = next((path for path in candidate_files if path.exists()), None)
        if discovered_file is None:
            dll_discovery_log.append(f"{label}:missing:{root}")
            return
        discovery_paths = [discovered_file.parent]

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


def _probe_adreno_opencl_sidecar(
    profile: HardwareProfile,
    tokens: list[str],
    dll_discovery_log: list[str],
) -> None:
    if (
        profile.os_name != "windows"
        or profile.arch != "arm64"
        or profile.gpu_vendor != "qualcomm"
        or not profile.gpu_available
    ):
        return

    runtime_dir = REPO_ROOT / "runtimes" / "llama.cpp" / "windows-arm64-adreno-opencl"
    required_files = (
        runtime_dir / "llama-server.exe",
        runtime_dir / "OpenCL.dll",
    )
    if not all(path.is_file() and path.stat().st_size > 0 for path in required_files):
        tokens.append("opencl:adreno:MISSING")
        dll_discovery_log.append(f"OpenCL:missing:{runtime_dir}")
        return

    dll_api = _available_dll_directory_api()
    try:
        if dll_api is not None:
            dll_api(str(runtime_dir))
        dll_discovery_log.append(f"OpenCL:added:{runtime_dir}")
    except Exception as exc:
        dll_discovery_log.append(f"OpenCL:failed:{runtime_dir}:{exc}")

    tokens.append("opencl:adreno")
    tokens.append("dll:OpenCL")


def _probe_imports(
    installed_extras: list[str],
    tokens: list[str],
    probe_errors: dict[str, str],
    profile: HardwareProfile,
) -> None:
    for import_name in _ordered_import_names(installed_extras, profile):
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


def _activate_qnn_execution_provider_if_applicable(
    profile: HardwareProfile,
    installed_extras: list[str],
    tokens: list[str],
    probe_errors: dict[str, str],
    dll_discovery_log: list[str],
) -> None:
    if profile.npu_vendor != "qualcomm" or not _has_extra(installed_extras, "hw-npu-qualcomm-qnn"):
        return

    try:
        from backend.app.hardware.qnn_provider import activate_qnn_execution_provider
    except Exception as exc:
        probe_errors["onnxruntime.qnn.provider_activation"] = str(exc)
        return

    result = activate_qnn_execution_provider()
    if result.dll_directory_path is not None:
        dll_discovery_log.append(f"QNNProvider:added:{result.dll_directory_path}")
    if result.provider_library_path is not None:
        dll_discovery_log.append(f"QNNProvider:library:{result.provider_library_path}")
    if result.provider_registered:
        tokens.append("qnn:provider_library_registered")
    elif result.error:
        probe_errors["onnxruntime.qnn.provider_activation"] = result.error


def _probe_distribution(
    distribution_name: str,
    tokens: list[str],
    probe_errors: dict[str, str],
) -> bool:
    token = f"import:{distribution_name}"
    try:
        importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError as exc:
        tokens.append(f"{token}:MISSING")
        probe_errors[distribution_name] = str(exc)
        return False
    except Exception as exc:
        tokens.append(f"{token}:MISSING")
        probe_errors[distribution_name] = str(exc)
        return False
    else:
        tokens.append(token)
        return True


def _discover_packaged_qnn_htp_path(probe_errors: dict[str, str]) -> Path | None:
    candidate_roots: list[Path] = []
    try:
        onnxruntime = importlib.import_module("onnxruntime")
    except Exception as exc:
        probe_errors["onnxruntime.qnn.htp_discovery"] = str(exc)
    else:
        module_file = getattr(onnxruntime, "__file__", None)
        if module_file:
            candidate_roots.append(Path(module_file).resolve().parent)

    try:
        onnxruntime_qnn = importlib.import_module("onnxruntime_qnn")
    except Exception as exc:
        probe_errors["onnxruntime.qnn.package_discovery"] = str(exc)
    else:
        module_file = getattr(onnxruntime_qnn, "__file__", None)
        if module_file:
            candidate_roots.append(Path(module_file).resolve().parent)

    if not candidate_roots:
        probe_errors["onnxruntime.qnn.htp_discovery"] = "onnxruntime package roots unavailable"
        return None

    return next(
        (
            path
            for module_root in candidate_roots
            for path in module_root.rglob("QnnHtp.dll")
            if path.is_file()
        ),
        None,
    )


def _mark_qnn_htp_discovery(
    htp_path: Path | None,
    tokens: list[str],
    dll_discovery_log: list[str],
) -> None:
    if htp_path is None:
        if "dll:QnnHtp" not in tokens and "dll:QnnHtp:MISSING" not in tokens:
            tokens.append("dll:QnnHtp:MISSING")
        return

    dll_api = _available_dll_directory_api()
    try:
        if dll_api is not None:
            dll_api(str(htp_path.parent))
        dll_discovery_log.append(f"QnnHtp:added:{htp_path.parent}")
    except Exception as exc:
        dll_discovery_log.append(f"QnnHtp:failed:{htp_path.parent}:{exc}")
    if "dll:QnnHtp" not in tokens:
        tokens.append("dll:QnnHtp")


def _probe_qnn_capability(
    profile: HardwareProfile,
    installed_extras: list[str],
    tokens: list[str],
    probe_errors: dict[str, str],
    dll_discovery_log: list[str],
) -> None:
    if profile.npu_vendor != "qualcomm" or not _has_extra(installed_extras, "hw-npu-qualcomm-qnn"):
        return

    qnn_distribution_ready = _probe_distribution("onnxruntime-qnn", tokens, probe_errors)

    if qnn_distribution_ready:
        if "ep:QNNExecutionProvider" not in tokens:
            tokens.append("ep:QNNExecutionProvider:MISSING")

        htp_path = _discover_packaged_qnn_htp_path(probe_errors)
        if htp_path is None and "dll:QnnHtp" in tokens:
            tokens.append("qnn:htp_path:configured")
        elif htp_path is None:
            tokens.append("qnn:htp_path:MISSING")
        else:
            tokens.append("qnn:htp_path")
            tokens.append(f"qnn:backend_path:{htp_path}")
            _mark_qnn_htp_discovery(htp_path, tokens, dll_discovery_log)
    else:
        tokens.append("ep:QNNExecutionProvider:MISSING")
        tokens.append("qnn:htp_path:MISSING")

    if "dll:QnnHtp" not in tokens and "dll:QnnHtp:MISSING" not in tokens:
        tokens.append("dll:QnnHtp:MISSING")


def run_preflight(profile: HardwareProfile, installed_extras: list[str]) -> PreflightResult:
    cache_key = _profile_cache_key(profile, installed_extras)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return _restore(cached)

    tokens: list[str] = []
    dll_discovery_log: list[str] = []
    probe_errors: dict[str, str] = {}

    _bootstrap_windows_dlls(profile, tokens, dll_discovery_log)
    _probe_adreno_opencl_sidecar(profile, tokens, dll_discovery_log)
    _probe_imports(installed_extras, tokens, probe_errors, profile)

    if "import:onnxruntime" in tokens:
        _activate_qnn_execution_provider_if_applicable(
            profile,
            installed_extras,
            tokens,
            probe_errors,
            dll_discovery_log,
        )
        _probe_execution_providers(tokens, probe_errors)

    _probe_qnn_capability(profile, installed_extras, tokens, probe_errors, dll_discovery_log)

    result = PreflightResult(
        tokens=tokens,
        dll_discovery_log=dll_discovery_log,
        probe_errors=probe_errors,
    )
    _CACHE[cache_key] = _snapshot(result)
    return _restore(_CACHE[cache_key])
