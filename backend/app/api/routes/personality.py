from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.app import ApiState
from backend.app.api.dependencies import get_api_state
from backend.app.api.schemas.personality import (
    PersonalityListResponse,
    PersonalityProfileError,
    PersonalitySelectRequest,
    PersonalitySelectResponse,
    PersonalitySummary,
)
from backend.app.personality.loader import list_personality_profiles_with_errors, load_personality_profile
from backend.app.personality.schema import PersonalityProfile

router = APIRouter()


def _summary(profile: PersonalityProfile) -> PersonalitySummary:
    return PersonalitySummary(
        profile_id=profile.profile_id,
        display_name=profile.display_name,
        description=profile.description,
        locale=profile.locale,
        max_words_default=profile.style.max_words_default,
    )


@router.get("/personality/list", response_model=PersonalityListResponse)
def personality_list(state: ApiState = Depends(get_api_state)) -> PersonalityListResponse:
    profile_list = list_personality_profiles_with_errors()
    return PersonalityListResponse(
        active_profile_id=state.session_service.active_personality().profile_id,
        profiles=[_summary(profile) for profile in profile_list.profiles],
        profile_errors=[
            PersonalityProfileError(profile_path=error.profile_path, reason=error.reason)
            for error in profile_list.profile_errors
        ],
    )


@router.post("/personality/select", response_model=PersonalitySelectResponse)
def personality_select(
    request: PersonalitySelectRequest,
    state: ApiState = Depends(get_api_state),
) -> PersonalitySelectResponse:
    try:
        profile = load_personality_profile(request.profile_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    state.personality = profile
    state.engine.personality = profile
    state.session_service.select_personality(profile)
    return PersonalitySelectResponse(active=_summary(profile))
