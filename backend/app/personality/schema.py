from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


_ALLOWED_FIELDS = {
    "profile_id",
    "display_name",
    "tone",
    "brevity",
    "formality",
    "system_prompt_addendum",
    "identity_summary",
    "warmth",
    "assertiveness",
    "humor_policy",
    "response_style",
    "acknowledgment_style",
    "confirmation_style",
    "interruption_style",
    "voice_pacing",
    "voice_energy",
    "enabled",
}

_PROHIBITED_FIELDS = {
    "tool_permissions",
    "tool_policy",
    "routing_policy",
    "model_routing",
    "memory_policy",
    "memory_permissions",
    "safety_overrides",
    "hidden_instructions",
    "system_prompt",
}

_ALLOWED_TONE = {"professional", "direct", "warm", "calm", "precise"}
_ALLOWED_BREVITY = {"terse", "concise", "balanced", "detailed_when_needed"}
_ALLOWED_FORMALITY = {"formal", "semi-formal", "conversational"}
_ALLOWED_WARMTH = {"low", "moderate", "high"}
_ALLOWED_ASSERTIVENESS = {"low", "moderate", "high"}
_ALLOWED_HUMOR_POLICY = {"none", "dry", "light"}
_ALLOWED_RESPONSE_STYLE = {"direct_answer", "implementation_boundary_first", "action_report", "supportive"}
_ALLOWED_ACKNOWLEDGMENT_STYLE = {"none", "minimal", "brief"}
_ALLOWED_CONFIRMATION_STYLE = {"none", "light", "explicit_when_needed"}
_ALLOWED_INTERRUPTION_STYLE = {"stop_cleanly", "acknowledge_then_continue"}
_ALLOWED_VOICE_PACING = {"slow", "normal", "brisk"}
_ALLOWED_VOICE_ENERGY = {"calm", "neutral", "energetic"}


@dataclass(frozen=True, slots=True)
class PersonalityProfile:
    profile_id: str
    display_name: str
    tone: str
    brevity: str
    formality: str
    system_prompt_addendum: str = ""
    identity_summary: str = "A local-first personal assistant with a consistent JARVIS identity."
    warmth: str = "moderate"
    assertiveness: str = "moderate"
    humor_policy: str = "none"
    response_style: str = "direct_answer"
    acknowledgment_style: str = "minimal"
    confirmation_style: str = "explicit_when_needed"
    interruption_style: str = "stop_cleanly"
    voice_pacing: str = "normal"
    voice_energy: str = "neutral"
    enabled: bool = True

    def __post_init__(self) -> None:
        _validate_member("tone", self.tone, _ALLOWED_TONE)
        _validate_member("brevity", self.brevity, _ALLOWED_BREVITY)
        _validate_member("formality", self.formality, _ALLOWED_FORMALITY)
        _validate_member("warmth", self.warmth, _ALLOWED_WARMTH)
        _validate_member("assertiveness", self.assertiveness, _ALLOWED_ASSERTIVENESS)
        _validate_member("humor_policy", self.humor_policy, _ALLOWED_HUMOR_POLICY)
        _validate_member("response_style", self.response_style, _ALLOWED_RESPONSE_STYLE)
        _validate_member("acknowledgment_style", self.acknowledgment_style, _ALLOWED_ACKNOWLEDGMENT_STYLE)
        _validate_member("confirmation_style", self.confirmation_style, _ALLOWED_CONFIRMATION_STYLE)
        _validate_member("interruption_style", self.interruption_style, _ALLOWED_INTERRUPTION_STYLE)
        _validate_member("voice_pacing", self.voice_pacing, _ALLOWED_VOICE_PACING)
        _validate_member("voice_energy", self.voice_energy, _ALLOWED_VOICE_ENERGY)
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersonalityProfile":
        unexpected = set(data) - _ALLOWED_FIELDS
        prohibited = set(data) & _PROHIBITED_FIELDS
        if prohibited:
            names = ", ".join(sorted(prohibited))
            raise ValueError(f"personality profile contains prohibited authority fields: {names}")
        if unexpected:
            names = ", ".join(sorted(unexpected))
            raise ValueError(f"personality profile contains unknown fields: {names}")
        return cls(
            profile_id=str(data["profile_id"]),
            display_name=str(data["display_name"]),
            tone=str(data["tone"]),
            brevity=str(data["brevity"]),
            formality=str(data["formality"]),
            system_prompt_addendum=str(data.get("system_prompt_addendum", "")),
            identity_summary=str(
                data.get("identity_summary", "A local-first personal assistant with a consistent JARVIS identity.")
            ),
            warmth=str(data.get("warmth", "moderate")),
            assertiveness=str(data.get("assertiveness", "moderate")),
            humor_policy=str(data.get("humor_policy", "none")),
            response_style=str(data.get("response_style", "direct_answer")),
            acknowledgment_style=str(data.get("acknowledgment_style", "minimal")),
            confirmation_style=str(data.get("confirmation_style", "explicit_when_needed")),
            interruption_style=str(data.get("interruption_style", "stop_cleanly")),
            voice_pacing=str(data.get("voice_pacing", "normal")),
            voice_energy=str(data.get("voice_energy", "neutral")),
            enabled=_coerce_enabled(data.get("enabled", True)),
        )


def _validate_member(field_name: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"invalid personality {field_name}: {value!r}; expected one of: {allowed_values}")


def _coerce_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError("enabled must be a boolean")
