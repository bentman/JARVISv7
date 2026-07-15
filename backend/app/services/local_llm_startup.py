from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.core.settings import Settings, load_settings
from backend.app.hardware.preflight import PreflightResult
from backend.app.models.catalog import ModelCatalogError
from backend.app.models.llm_profiles import LLMServeProfileResolution, resolve_llm_serve_profile
from backend.app.models.llm_selection import select_llm_model
from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.services.local_llm_sidecar import LocalLLMSidecarService, LocalLLMSidecarStatus

_ORIGINAL_GET = httpx.get


ReadinessProbe = Callable[[str, float], tuple[bool, str]]


@dataclass(slots=True)
class ManagedLocalLLMStartup:
    runtime: LlamaCppLLM | None
    sidecar: LocalLLMSidecarService | None = None
    resolution: LLMServeProfileResolution | None = None
    degraded_reason: str | None = None


def prepare_managed_local_llm(
    profile: HardwareProfile,
    preflight: PreflightResult,
    *,
    flags: CapabilityFlags | None = None,
    settings: Settings | None = None,
    route: str = "voice_chat",
    readiness_probe: ReadinessProbe | None = None,
) -> ManagedLocalLLMStartup:
    resolved_settings = settings or load_settings()
    if not resolved_settings.use_local_model:
        return ManagedLocalLLMStartup(
            runtime=None,
            degraded_reason="local model disabled",
        )

    try:
        model_selection = select_llm_model(route, profile, settings=resolved_settings)
        resolution = resolve_llm_serve_profile(
            route,
            profile,
            preflight,
            settings=resolved_settings,
            flags=flags,
            model_name=model_selection.model_id,
        )
    except ModelCatalogError as exc:
        return ManagedLocalLLMStartup(
            runtime=None,
            degraded_reason=str(exc),
        )
    resolution = LLMServeProfileResolution(
        model_id=resolution.model_id,
        route=resolution.route,
        serve_profile_id=resolution.serve_profile_id,
        local_model_path=resolution.local_model_path,
        binary_path=resolution.binary_path,
        base_url=resolution.base_url,
        accelerator=resolution.accelerator,
        launch=resolution.launch,
        generation_defaults=resolution.generation_defaults,
        selected_reason=resolution.selected_reason,
        model_mode=model_selection.mode,
        model_policy=model_selection.policy,
        model_role=model_selection.role,
        model_selection_reason=model_selection.reason,
        degraded_reasons=resolution.degraded_reasons,
        degraded_candidates=resolution.degraded_candidates,
    )
    if resolution.degraded_reason:
        return ManagedLocalLLMStartup(
            runtime=None,
            resolution=resolution,
            degraded_reason=resolution.degraded_reason,
        )

    sidecar: LocalLLMSidecarService | None = None
    if resolved_settings.effective_llama_cpp_managed:
        sidecar = LocalLLMSidecarService()
        status = sidecar.start(resolution)
        if not status.running:
            return ManagedLocalLLMStartup(
                runtime=None,
                sidecar=sidecar,
                resolution=resolution,
                degraded_reason=status.degraded_reason or status.last_error or "managed llama.cpp sidecar did not start",
            )

        ready, reason = _probe_startup_readiness(
            resolution.base_url,
            90.0,
            sidecar=sidecar,
            readiness_probe=readiness_probe,
        )
        if not ready:
            sidecar.stop()
            return ManagedLocalLLMStartup(
                runtime=None,
                resolution=resolution,
                degraded_reason=f"Degraded-sidecar-unreachable: {reason}",
            )

    def recover_sidecar() -> LocalLLMSidecarStatus:
        if sidecar is None:
            raise RuntimeError("managed llama.cpp sidecar recovery requested without a sidecar service")
        status = sidecar.restart(resolution)
        if not status.running:
            return status
        ready, _reason = _probe_startup_readiness(
            resolution.base_url,
            90.0,
            sidecar=sidecar,
            readiness_probe=readiness_probe,
        )
        if not ready:
            sidecar.stop()
        return sidecar.status()

    runtime = LlamaCppLLM(
        base_url=resolution.base_url,
        model=resolution.model_id,
        generation_defaults=resolution.generation_defaults,
        sidecar_status=sidecar.status if sidecar is not None else None,
        sidecar_recover=recover_sidecar if sidecar is not None else None,
        managed=resolved_settings.effective_llama_cpp_managed,
        route=resolution.route,
        serve_profile_id=resolution.serve_profile_id,
        accelerator=resolution.accelerator,
        selected_reason=resolution.selected_reason,
        model_mode=resolution.model_mode,
        model_policy=resolution.model_policy,
        model_role=resolution.model_role,
        model_selection_reason=resolution.model_selection_reason,
    )
    return ManagedLocalLLMStartup(
        runtime=runtime,
        sidecar=sidecar,
        resolution=resolution,
    )


def _probe_startup_readiness(
    base_url: str,
    timeout_seconds: float,
    *,
    sidecar: LocalLLMSidecarService,
    readiness_probe: ReadinessProbe | None,
) -> tuple[bool, str]:
    if readiness_probe is not None:
        return readiness_probe(base_url, timeout_seconds)
    phase_durations_ms: dict[str, float] = {}
    result = wait_for_llama_cpp_ready(
        base_url,
        timeout_seconds,
        phase_durations_ms=phase_durations_ms,
    )
    sidecar.update_startup_phase_durations(phase_durations_ms)
    return result


def wait_for_llama_cpp_ready(
    base_url: str,
    timeout_seconds: float = 90.0,
    *,
    phase_durations_ms: dict[str, float] | None = None,
) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout_seconds
    last_reason = "not probed"
    url = base_url.rstrip("/")
    durations = phase_durations_ms if phase_durations_ms is not None else {}
    durations.setdefault("health_readiness", 0.0)
    durations.setdefault("models_readiness", 0.0)
    health_phase_started_at = time.monotonic()
    models_phase_started_at: float | None = None
    health_ready = False
    with httpx.Client() as client:
        while time.monotonic() < deadline:
            get_func = httpx.get if httpx.get is not _ORIGINAL_GET else client.get
            if not health_ready:
                try:
                    health = get_func(f"{url}/health", timeout=2.0)
                    health.raise_for_status()
                except Exception as exc:
                    last_reason = str(exc)
                    time.sleep(0.25)
                    continue
                health_ready = True
                durations["health_readiness"] = _elapsed_ms(health_phase_started_at)
                models_phase_started_at = time.monotonic()
            try:
                models = get_func(f"{url}/v1/models", timeout=2.0)
                models.raise_for_status()
                payload = models.json()
                if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                    if models_phase_started_at is not None:
                        durations["models_readiness"] = _elapsed_ms(models_phase_started_at)
                    return True, "health and /v1/models reachable"
                last_reason = "/v1/models returned invalid payload"
            except Exception as exc:
                last_reason = str(exc)
            time.sleep(0.25)
    if health_ready and models_phase_started_at is not None:
        durations["models_readiness"] = _elapsed_ms(models_phase_started_at)
    else:
        durations["health_readiness"] = _elapsed_ms(health_phase_started_at)
    return False, last_reason


def _elapsed_ms(started_at: float) -> float:
    return max(0.0, (time.monotonic() - started_at) * 1000.0)
