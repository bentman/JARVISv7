from __future__ import annotations

from backend.app.actions import catalog
from backend.app.api.dependencies import get_optional_capability_service
from backend.app.api.schemas.llm_config import (
    LLMDiscoveredModel,
    LLMProviderConfigResponse,
    LLMProviderProfileResponse,
    LLMProviderProfileWrite,
    LLMProviderSelectionResponse,
    LLMProviderSelectionWrite,
    LLMProviderTestResponse,
    SecretRotationResponse,
)
from backend.app.services.capability_service import CapabilityService, execute_operator_action
from backend.app.services.llm_provider_profiles import (
    LLMProviderProfileStore,
    ProviderConfigError,
    ProviderProfile,
    ProviderSelection,
    SecretStoreLockedError,
)
from backend.app.services.llm_provider_service import provider_model_discovery
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()
PROFILE_STORE_FACTORY = LLMProviderProfileStore


def _store() -> LLMProviderProfileStore:
    return PROFILE_STORE_FACTORY()


def _profile_response(profile: ProviderProfile) -> LLMProviderProfileResponse:
    return LLMProviderProfileResponse(
        profile_id=profile.profile_id,
        name=profile.name,
        kind=profile.kind,
        endpoint=profile.endpoint,
        model=profile.model,
        context_window=profile.context_window,
        timeout_seconds=profile.timeout_seconds,
        has_secret=profile.has_secret,
        builtin=profile.builtin,
        cloud_eligible=profile.cloud_eligible,
        readiness_state=profile.readiness_state,
        updated_at=profile.updated_at,
        secret_updated_at=profile.secret_updated_at,
    )


def _selection_response(selection: ProviderSelection) -> LLMProviderSelectionResponse:
    return LLMProviderSelectionResponse(
        primary_profile_id=selection.primary_profile_id,
        local_fallback_profile_id=selection.local_fallback_profile_id,
        cloud_escalation_enabled=selection.cloud_escalation_enabled,
        cloud_profile_id=selection.cloud_profile_id,
        persisted=selection.persisted,
    )


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail={"error": "invalid_provider_configuration", "message": str(exc)})


@router.get("/config/llm", response_model=LLMProviderConfigResponse)
def get_llm_config() -> LLMProviderConfigResponse:
    store = _store()
    return LLMProviderConfigResponse(
        profiles=[_profile_response(profile) for profile in store.list_profiles()],
        selection=_selection_response(store.get_selection()),
    )


@router.post("/config/llm/profiles", response_model=LLMProviderProfileResponse)
def create_llm_profile(
    request: LLMProviderProfileWrite,
    actions: CapabilityService | None = Depends(get_optional_capability_service),
) -> LLMProviderProfileResponse:
    try:
        profile = execute_operator_action(
            actions,
            catalog.PROVIDER_PROFILE_WRITE,
            {"name": request.name, "kind": request.kind},
            lambda: _store().create_profile(
                name=request.name,
                kind=request.kind,
                endpoint=request.endpoint,
                model=request.model,
                context_window=request.context_window,
                timeout_seconds=request.timeout_seconds,
                api_key=request.api_key,
            ),
        )
        return _profile_response(profile)
    except (ProviderConfigError, SecretStoreLockedError) as exc:
        raise _bad_request(exc) from exc


@router.put("/config/llm/profiles/{profile_id}", response_model=LLMProviderProfileResponse)
def update_llm_profile(
    profile_id: str,
    request: LLMProviderProfileWrite,
    actions: CapabilityService | None = Depends(get_optional_capability_service),
) -> LLMProviderProfileResponse:
    try:
        profile = execute_operator_action(
            actions,
            catalog.PROVIDER_PROFILE_WRITE,
            {"profile_id": profile_id, "name": request.name},
            lambda: _store().update_profile(
                profile_id,
                name=request.name,
                kind=request.kind,
                endpoint=request.endpoint,
                model=request.model,
                context_window=request.context_window,
                timeout_seconds=request.timeout_seconds,
                api_key=request.api_key,
                clear_api_key=request.clear_api_key,
            ),
        )
        return _profile_response(profile)
    except (ProviderConfigError, SecretStoreLockedError) as exc:
        raise _bad_request(exc) from exc


@router.delete("/config/llm/profiles/{profile_id}")
def delete_llm_profile(
    profile_id: str,
    actions: CapabilityService | None = Depends(get_optional_capability_service),
) -> dict[str, bool]:
    try:
        execute_operator_action(
            actions,
            catalog.PROVIDER_PROFILE_DELETE,
            {"profile_id": profile_id},
            lambda: _store().delete_profile(profile_id),
        )
        return {"deleted": True}
    except ProviderConfigError as exc:
        raise _bad_request(exc) from exc


@router.post("/config/llm/profiles/{profile_id}/test", response_model=LLMProviderTestResponse)
def test_llm_profile(profile_id: str) -> LLMProviderTestResponse:
    store = _store()
    try:
        profile = store.get_profile(profile_id)
        if profile.kind == "managed_llama_cpp":
            return LLMProviderTestResponse(status="configured", reason="managed profile readiness is reported by /readiness")
        models = provider_model_discovery(store, profile)
        return LLMProviderTestResponse(
            status="ready",
            reason="provider models endpoint reachable",
            models=[LLMDiscoveredModel.model_validate(item) for item in models],
        )
    except Exception as exc:
        message = str(exc)
        reason = (
            "provider credential is not configured"
            if "credential" in message.casefold()
            else "provider model discovery is unavailable; manual model entry remains available"
        )
        return LLMProviderTestResponse(status="unverified", reason=reason)


@router.put("/config/llm/selection", response_model=LLMProviderSelectionResponse)
def update_llm_selection(
    request: LLMProviderSelectionWrite,
    actions: CapabilityService | None = Depends(get_optional_capability_service),
) -> LLMProviderSelectionResponse:
    try:
        selection = execute_operator_action(
            actions,
            catalog.PROVIDER_SELECTION_UPDATE,
            {"primary_profile_id": request.primary_profile_id},
            lambda: _store().set_selection(
                primary_profile_id=request.primary_profile_id,
                local_fallback_profile_id=request.local_fallback_profile_id,
                cloud_escalation_enabled=request.cloud_escalation_enabled,
                cloud_profile_id=request.cloud_profile_id,
            ),
        )
        return _selection_response(selection)
    except ProviderConfigError as exc:
        raise _bad_request(exc) from exc


@router.post("/config/secrets/rotate", response_model=SecretRotationResponse)
def rotate_secret_store_key(
    actions: CapabilityService | None = Depends(get_optional_capability_service),
) -> SecretRotationResponse:
    try:
        execute_operator_action(
            actions,
            catalog.PROVIDER_SECRET_ROTATE,
            {},
            lambda: _store().rotate_key(),
        )
        return SecretRotationResponse(rotated=True)
    except (ProviderConfigError, SecretStoreLockedError) as exc:
        raise _bad_request(exc) from exc
