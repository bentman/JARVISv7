from __future__ import annotations

from pydantic import BaseModel


class PersonalitySummary(BaseModel):
    profile_id: str
    display_name: str
    tone: str
    brevity: str
    formality: str


class PersonalityListResponse(BaseModel):
    active_profile_id: str
    profiles: list[PersonalitySummary]


class PersonalitySelectRequest(BaseModel):
    profile_id: str


class PersonalitySelectResponse(BaseModel):
    active: PersonalitySummary