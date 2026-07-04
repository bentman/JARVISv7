from __future__ import annotations

from pydantic import BaseModel


class PersonalitySummary(BaseModel):
    profile_id: str
    display_name: str
    description: str
    locale: str
    max_words_default: int


class PersonalityProfileError(BaseModel):
    profile_path: str
    reason: str


class PersonalityListResponse(BaseModel):
    active_profile_id: str
    profiles: list[PersonalitySummary]
    profile_errors: list[PersonalityProfileError] = []


class PersonalitySelectRequest(BaseModel):
    profile_id: str


class PersonalitySelectResponse(BaseModel):
    active: PersonalitySummary
