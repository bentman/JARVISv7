from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PersonalityProfile:
    profile_id: str
    display_name: str
    tone: str
    brevity: str
    formality: str
    system_prompt_addendum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersonalityProfile":
        return cls(
            profile_id=str(data["profile_id"]),
            display_name=str(data["display_name"]),
            tone=str(data["tone"]),
            brevity=str(data["brevity"]),
            formality=str(data["formality"]),
            system_prompt_addendum=str(data.get("system_prompt_addendum", "")),
        )