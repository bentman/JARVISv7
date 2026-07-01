from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.core.capabilities import HardwareProfile
from backend.app.core.settings import Settings, load_settings
from backend.app.models.catalog import ModelCatalogError, ModelEntry, get_model_entry, load_catalog


class LLMSelectionError(ModelCatalogError):
    """Raised when LLM model policy cannot select a valid model."""


@dataclass(frozen=True, slots=True)
class LLMModelSelection:
    model_id: str
    route: str
    mode: str
    policy: str
    role: str
    role_status: str | None
    hardware_selector: str
    reason: str
    override: bool = False


def select_llm_model(
    route: str,
    profile: HardwareProfile,
    *,
    settings: Settings | None = None,
    policy: str | None = None,
    model_override: str | None = None,
    catalog: dict[str, Any] | None = None,
) -> LLMModelSelection:
    data = catalog or load_catalog("llm")
    selection = _selection_config(data)
    resolved_settings = settings or load_settings()
    override = _clean(model_override if model_override is not None else resolved_settings.llm_model_id)
    selected_mode = _clean(resolved_settings.llm_model_mode) or "dev"
    selected_policy = _clean(policy if policy is not None else resolved_settings.llm_model_policy)
    if selected_policy is None:
        selected_policy = _required_string(selection, "default_policy", "llm_selection.default_policy")

    if override:
        entry = _get_llm_entry(override)
        _require_route(entry, route)
        return LLMModelSelection(
            model_id=entry.name,
            route=route,
            mode=selected_mode,
            policy=selected_policy,
            role="override",
            role_status=None,
            hardware_selector="override",
            reason=f"selected explicit LLM_MODEL_ID override {entry.name}",
            override=True,
        )

    if selected_mode == "dev":
        modes = _required_mapping(selection, "modes", "llm_selection.modes")
        dev_config = modes.get("dev")
        if not isinstance(dev_config, dict):
            raise LLMSelectionError("LLM model mode 'dev' is not configured")
        model_id = _required_string(dev_config, "model", "llm_selection.modes.dev.model")
        role = _required_string(dev_config, "role", "llm_selection.modes.dev.role")
        role_status = dev_config.get("status") if isinstance(dev_config.get("status"), str) else None
        entry = _get_llm_entry(model_id)
        _require_route(entry, route)
        return LLMModelSelection(
            model_id=entry.name,
            route=route,
            mode=selected_mode,
            policy=selected_policy,
            role=role,
            role_status=role_status,
            hardware_selector="mode:dev",
            reason=f"mode dev selected {entry.name}",
        )
    if selected_mode != "prod":
        raise LLMSelectionError(f"LLM model mode '{selected_mode}' is not configured")

    policies = _required_mapping(selection, "policies", "llm_selection.policies")
    policy_map = policies.get(selected_policy)
    if not isinstance(policy_map, dict):
        raise LLMSelectionError(f"LLM model policy '{selected_policy}' is not configured")

    hardware_selector, role = _select_role(policy_map, profile)
    roles = _required_mapping(selection, "roles", "llm_selection.roles")
    role_config = roles.get(role)
    if not isinstance(role_config, dict):
        raise LLMSelectionError(f"LLM model role '{role}' is not configured")
    model_id = _required_string(role_config, "model", f"llm_selection.roles.{role}.model")
    role_status = role_config.get("status") if isinstance(role_config.get("status"), str) else None
    entry = _get_llm_entry(model_id)
    _require_route(entry, route)
    return LLMModelSelection(
        model_id=entry.name,
        route=route,
        mode=selected_mode,
        policy=selected_policy,
        role=role,
        role_status=role_status,
        hardware_selector=hardware_selector,
        reason=(
            f"policy {selected_policy} mapped {hardware_selector} to role {role}; "
            f"role selects model {entry.name}"
        ),
    )


def _selection_config(catalog: dict[str, Any]) -> dict[str, Any]:
    selection = catalog.get("llm_selection")
    if not isinstance(selection, dict):
        raise LLMSelectionError("llm_selection metadata is not configured")
    return selection


def _select_role(policy_map: dict[str, Any], profile: HardwareProfile) -> tuple[str, str]:
    for selector in _hardware_selectors(profile):
        role = policy_map.get(selector)
        if isinstance(role, str) and role.strip():
            return selector, role
    role = policy_map.get("*")
    if isinstance(role, str) and role.strip():
        return "*", role
    raise LLMSelectionError(f"LLM model policy has no mapping for current host {_hardware_selectors(profile)[-1]}")


def _hardware_selectors(profile: HardwareProfile) -> list[str]:
    base = f"{profile.os_name}_{profile.arch}"
    selectors: list[str] = []
    if profile.os_name == "windows" and profile.arch == "amd64":
        if profile.gpu_vendor == "nvidia" and profile.cuda_available:
            selectors.append("windows_amd64_gpu_nvidia_cuda")
        elif profile.gpu_vendor == "amd" and profile.gpu_available:
            selectors.append("windows_amd64_gpu_amd")
        elif profile.gpu_vendor == "intel" and profile.gpu_available:
            selectors.append("windows_amd64_gpu_intel")
    if profile.os_name == "windows" and profile.arch == "arm64":
        if profile.gpu_vendor == "qualcomm" and profile.gpu_available:
            selectors.append("windows_arm64_gpu_qualcomm_adreno_opencl")
        if profile.npu_vendor == "qualcomm" and profile.npu_available:
            selectors.extend(["windows_arm64_npu_qualcomm_qnn", "windows_arm64_npu_qualcomm_base"])
    selectors.append(f"{base}_cpu")
    return selectors


def _require_route(entry: ModelEntry, route: str) -> None:
    routes = entry.config.get("routes", [])
    if route not in routes:
        raise LLMSelectionError(f"route '{route}' is not declared for LLM model '{entry.name}'")


def _get_llm_entry(model_id: str) -> ModelEntry:
    try:
        return get_model_entry("llm", model_id)
    except ModelCatalogError as exc:
        raise LLMSelectionError(str(exc)) from exc


def _required_mapping(config: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    value = config.get(key)
    if not isinstance(value, dict):
        raise LLMSelectionError(f"{label} must be a mapping")
    return value


def _required_string(config: dict[str, Any], key: str, label: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LLMSelectionError(f"{label} must be a non-empty string")
    return value.strip()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
