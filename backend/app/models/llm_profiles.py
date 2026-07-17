from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.core.paths import REPO_ROOT
from backend.app.core.settings import Settings, load_settings
from backend.app.hardware.preflight import PreflightResult
from backend.app.models.catalog import ModelCatalogError, ModelEntry, get_model_entry


@dataclass(frozen=True, slots=True)
class ServeProfileCandidate:
    profile_id: str
    accelerator: str
    reason: str


@dataclass(frozen=True, slots=True)
class LLMServeProfileResolution:
    model_id: str
    route: str
    serve_profile_id: str
    local_model_path: Path
    binary_path: Path
    base_url: str
    accelerator: str
    launch: dict[str, Any]
    generation_defaults: dict[str, Any]
    selected_reason: str
    model_mode: str | None = None
    model_policy: str | None = None
    model_role: str | None = None
    model_selection_reason: str | None = None
    degraded_reasons: list[str] = field(default_factory=list)
    degraded_candidates: list[ServeProfileCandidate] = field(default_factory=list)

    @property
    def degraded_reason(self) -> str | None:
        if not self.degraded_reasons:
            return None
        return "; ".join(self.degraded_reasons)


def resolve_llm_serve_profile(
    route: str,
    profile: HardwareProfile,
    preflight: PreflightResult,
    *,
    settings: Settings | None = None,
    flags: CapabilityFlags | None = None,
    model_name: str | None = None,
    entry: ModelEntry | None = None,
) -> LLMServeProfileResolution:
    selected_entry = entry or get_model_entry("llm", model_name)
    config = selected_entry.config
    routes = config.get("routes", [])
    if route not in routes:
        raise ModelCatalogError(f"route '{route}' is not declared for LLM model '{selected_entry.name}'")

    serve_profiles = _serve_profiles(config, selected_entry.name)

    cpu_profile_id = _cpu_profile_id(profile)
    cpu_serve_profile = serve_profiles.get(cpu_profile_id)
    if not isinstance(cpu_serve_profile, dict):
        raise ModelCatalogError(
            f"LLM model '{selected_entry.name}' has no CPU serve profile for {profile.os_name}/{profile.arch}"
        )

    resolved_settings = settings or load_settings()
    local_model_path = _settings_path_override(resolved_settings.llama_cpp_model_path, selected_entry.local_path)
    selected_profile_id, selected_profile, degraded_candidates = _select_current_host_profile(
        serve_profiles,
        cpu_profile_id,
        cpu_serve_profile,
        profile,
        preflight,
        flags,
        local_model_path,
    )
    binary_path = _settings_path_override(
        resolved_settings.llama_cpp_binary_path,
        _profile_path(selected_profile, "binary_path", selected_entry.name, selected_profile_id),
    )
    base_url = _base_url(selected_profile, resolved_settings)
    accelerator = str(selected_profile.get("accelerator", "cpu"))
    degraded_reasons = _selected_degraded_reasons(local_model_path, binary_path)

    return LLMServeProfileResolution(
        model_id=selected_entry.name,
        route=route,
        serve_profile_id=selected_profile_id,
        local_model_path=local_model_path,
        binary_path=binary_path,
        base_url=base_url,
        accelerator=accelerator,
        launch=dict(selected_profile.get("launch", {})),
        generation_defaults=dict(config.get("generation_defaults", {})),
        selected_reason=_selected_reason(selected_profile_id, accelerator),
        degraded_reasons=degraded_reasons,
        degraded_candidates=degraded_candidates,
    )


def _cpu_profile_id(profile: HardwareProfile) -> str:
    return f"{profile.os_name}_{profile.arch}_cpu"


def _serve_profiles(config: dict[str, Any], model_name: str) -> dict[str, Any]:
    raw_profiles = config.get("serve_profiles", {})
    if not isinstance(raw_profiles, dict):
        raise ModelCatalogError(f"LLM model '{model_name}' has invalid serve_profiles metadata")

    hardware_profiles = raw_profiles.get("hardware_profiles")
    if hardware_profiles is None:
        return raw_profiles
    if not isinstance(hardware_profiles, dict):
        raise ModelCatalogError(
            f"LLM model '{model_name}' has invalid serve_profiles.hardware_profiles metadata"
        )
    return hardware_profiles


def _select_current_host_profile(
    serve_profiles: dict[str, Any],
    cpu_profile_id: str,
    cpu_serve_profile: dict[str, Any],
    profile: HardwareProfile,
    preflight: PreflightResult,
    flags: CapabilityFlags | None,
    local_model_path: Path,
) -> tuple[str, dict[str, Any], list[ServeProfileCandidate]]:
    selected_profile_id = cpu_profile_id
    selected_profile = cpu_serve_profile
    degraded_candidates: list[ServeProfileCandidate] = []

    for profile_id, candidate in serve_profiles.items():
        if not isinstance(candidate, dict):
            continue
        if profile_id == cpu_profile_id:
            continue
        if candidate.get("os") != profile.os_name or candidate.get("arch") != profile.arch:
            continue

        accelerator = str(candidate.get("accelerator", "cpu"))
        if accelerator == "cpu":
            continue

        reason = _accelerator_degraded_reason(
            profile_id,
            candidate,
            profile,
            preflight,
            flags,
            local_model_path,
        )
        if reason is None and selected_profile_id == cpu_profile_id:
            selected_profile_id = profile_id
            selected_profile = candidate
            continue
        if reason is not None:
            degraded_candidates.append(
                ServeProfileCandidate(
                    profile_id=profile_id,
                    accelerator=accelerator,
                    reason=reason,
                )
            )

    return selected_profile_id, selected_profile, degraded_candidates


def _selected_reason(profile_id: str, accelerator: str) -> str:
    if accelerator == "cpu":
        return f"selected current-host CPU serve profile {profile_id}"
    return f"selected current-host {accelerator} serve profile {profile_id}"


def _settings_path_override(raw_path: str | None, default_path: Path) -> Path:
    if raw_path is None or not raw_path.strip():
        return default_path
    return _repo_path(Path(raw_path))


def _profile_path(serve_profile: dict[str, Any], field_name: str, model_name: str, profile_id: str) -> Path:
    raw_path = serve_profile.get(field_name)
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ModelCatalogError(f"LLM model '{model_name}' profile '{profile_id}' has no {field_name}")
    return _repo_path(Path(raw_path))


def _repo_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _base_url(serve_profile: dict[str, Any], settings: Settings) -> str:
    if settings.llama_cpp_base_url:
        return settings.llama_cpp_base_url.rstrip("/")
    raw_base_url = serve_profile.get("base_url")
    if isinstance(raw_base_url, str) and raw_base_url.strip():
        return raw_base_url.rstrip("/")
    host = str(serve_profile.get("host", "127.0.0.1"))
    port = int(serve_profile.get("port", 8080))
    return f"http://{host}:{port}"


def _selected_degraded_reasons(local_model_path: Path, binary_path: Path) -> list[str]:
    reasons: list[str] = []
    if not local_model_path.is_file() or local_model_path.stat().st_size <= 0:
        reasons.append("Degraded-no-local-model-artifact")
    if not binary_path.is_file() or binary_path.stat().st_size <= 0:
        reasons.append("Degraded-no-sidecar-binary")
    return reasons


def _degraded_accelerator_candidates(
    serve_profiles: dict[str, Any],
    profile: HardwareProfile,
    preflight: PreflightResult,
    flags: CapabilityFlags | None,
    local_model_path: Path,
) -> list[ServeProfileCandidate]:
    candidates: list[ServeProfileCandidate] = []
    for profile_id, candidate in serve_profiles.items():
        if not isinstance(candidate, dict):
            continue
        if candidate.get("os") != profile.os_name or candidate.get("arch") != profile.arch:
            continue
        accelerator = str(candidate.get("accelerator", "cpu"))
        if accelerator == "cpu":
            continue
        reason = _accelerator_degraded_reason(
            profile_id,
            candidate,
            profile,
            preflight,
            flags,
            local_model_path,
        )
        if reason is not None:
            candidates.append(
                ServeProfileCandidate(
                    profile_id=profile_id,
                    accelerator=accelerator,
                    reason=reason,
                )
            )
    return candidates


def _accelerator_degraded_reason(
    profile_id: str,
    candidate: dict[str, Any],
    profile: HardwareProfile,
    preflight: PreflightResult,
    flags: CapabilityFlags | None,
    local_model_path: Path,
) -> str | None:
    close_reason = candidate.get("close_if_unavailable")
    accelerator = str(candidate.get("accelerator", ""))

    if accelerator == "gpu.cuda":
        cuda_ready = (
            profile.gpu_vendor == "nvidia"
            and profile.cuda_available
            and (flags is None or flags.supports_cuda_llm)
        )
        if not cuda_ready:
            return str(close_reason or "Degraded-accelerator-unavailable")
    elif accelerator == "npu.qnn":
        qnn_ready = (
            profile.npu_vendor == "qualcomm"
            and profile.npu_available
            and (flags is None or flags.qnn_available)
            and "ep:QNNExecutionProvider" in preflight.tokens
            and "dll:QnnHtp" in preflight.tokens
        )
        if not qnn_ready:
            return str(close_reason or "Degraded-accelerator-unavailable")
    elif accelerator == "gpu.opencl.adreno":
        opencl_ready = (
            profile.gpu_vendor == "qualcomm"
            and profile.gpu_available
            and "opencl:adreno" in preflight.tokens
        )
        if not opencl_ready:
            return str(close_reason or "Degraded-accelerator-unavailable")
    else:
        return str(close_reason or "Degraded-accelerator-unavailable")

    binary_path = _profile_path(candidate, "binary_path", "llm", profile_id)
    if not binary_path.is_file() or binary_path.stat().st_size <= 0:
        return "Degraded-no-sidecar-binary"
    if not local_model_path.is_file() or local_model_path.stat().st_size <= 0:
        return "Degraded-no-local-model-artifact"
    return None
