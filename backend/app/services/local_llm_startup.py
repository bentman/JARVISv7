from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import httpx

from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.core.settings import Settings, load_settings
from backend.app.hardware.preflight import PreflightResult
from backend.app.models.llm_profiles import LLMServeProfileResolution, resolve_llm_serve_profile
from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.services.local_llm_sidecar import LocalLLMSidecarService


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

    resolution = resolve_llm_serve_profile(
        route,
        profile,
        preflight,
        settings=resolved_settings,
        flags=flags,
    )
    if resolution.degraded_reason:
        return ManagedLocalLLMStartup(
            runtime=None,
            resolution=resolution,
            degraded_reason=resolution.degraded_reason,
        )

    sidecar: LocalLLMSidecarService | None = None
    if resolved_settings.llama_cpp_managed:
        sidecar = LocalLLMSidecarService()
        status = sidecar.start(resolution)
        if not status.running:
            return ManagedLocalLLMStartup(
                runtime=None,
                sidecar=sidecar,
                resolution=resolution,
                degraded_reason=status.degraded_reason or status.last_error or "managed llama.cpp sidecar did not start",
            )

        probe = readiness_probe or wait_for_llama_cpp_ready
        ready, reason = probe(resolution.base_url, 45.0)
        if not ready:
            sidecar.stop()
            return ManagedLocalLLMStartup(
                runtime=None,
                resolution=resolution,
                degraded_reason=f"Degraded-sidecar-unreachable: {reason}",
            )

    runtime = LlamaCppLLM(
        base_url=resolution.base_url,
        model=resolution.model_id,
        generation_defaults=resolution.generation_defaults,
        sidecar_status=sidecar.status if sidecar is not None else None,
        managed=resolved_settings.llama_cpp_managed,
        route=resolution.route,
        serve_profile_id=resolution.serve_profile_id,
        accelerator=resolution.accelerator,
        selected_reason=resolution.selected_reason,
    )
    return ManagedLocalLLMStartup(
        runtime=runtime,
        sidecar=sidecar,
        resolution=resolution,
    )


def wait_for_llama_cpp_ready(base_url: str, timeout_seconds: float = 45.0) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout_seconds
    last_reason = "not probed"
    url = base_url.rstrip("/")
    while time.monotonic() < deadline:
        try:
            health = httpx.get(f"{url}/health", timeout=2.0)
            health.raise_for_status()
            models = httpx.get(f"{url}/v1/models", timeout=2.0)
            models.raise_for_status()
            payload = models.json()
            if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                return True, "health and /v1/models reachable"
            last_reason = "/v1/models returned invalid payload"
        except Exception as exc:
            last_reason = str(exc)
        time.sleep(0.25)
    return False, last_reason
