from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.core.settings import load_settings
from backend.app.personality.schema import PersonalityProfile


_FORBIDDEN_OVERRIDE_CATEGORIES = (
    "safety_overrides",
    "tool_permissions",
    "tool_policy",
    "routing_policy",
    "model_routing",
    "memory_policy",
    "memory_permissions",
    "hidden_instructions",
)

_ROLE_OVERLAYS: dict[str, dict[str, str]] = {
    "personal_assistant": {
        "response_style": "direct_answer",
        "acknowledgment_style": "minimal",
        "confirmation_style": "light",
    },
    "research": {
        "brevity": "detailed_when_needed",
        "response_style": "direct_answer",
        "confirmation_style": "explicit_when_needed",
    },
    "code_plan": {
        "tone": "precise",
        "response_style": "implementation_boundary_first",
    },
    "code_agent": {
        "response_style": "action_report",
        "acknowledgment_style": "minimal",
    },
    "tool_narrator": {
        "response_style": "action_report",
        "brevity": "concise",
    },
    "error_reporter": {
        "tone": "precise",
        "response_style": "direct_answer",
        "confirmation_style": "explicit_when_needed",
    },
    "escalation_narrator": {
        "tone": "professional",
        "response_style": "direct_answer",
        "confirmation_style": "explicit_when_needed",
    },
}


@dataclass(frozen=True, slots=True)
class PersonalityPolicy:
    profile_id: str
    identity: str
    style_rules: tuple[str, ...]
    speech_rules: tuple[str, ...]
    forbidden_overrides: tuple[str, ...] = _FORBIDDEN_OVERRIDE_CATEGORIES
    role_overlay_id: str | None = None


def compile_personality_policy(profile: PersonalityProfile, role_overlay_id: str | None = None) -> PersonalityPolicy:
    overlay = _resolve_role_overlay(role_overlay_id)
    response_language = profile.response_language.strip() or load_settings().jarvis_language.strip()
    values = {
        "tone": profile.tone,
        "brevity": profile.brevity,
        "formality": profile.formality,
        "warmth": profile.warmth,
        "assertiveness": profile.assertiveness,
        "humor_policy": profile.humor_policy,
        "response_style": profile.response_style,
        "acknowledgment_style": profile.acknowledgment_style,
        "confirmation_style": profile.confirmation_style,
        "interruption_style": profile.interruption_style,
        "voice_pacing": profile.voice_pacing,
        "voice_energy": profile.voice_energy,
    }
    values.update(overlay)

    style_rules = (
        f"Assistant identity: {profile.identity_summary}",
        f"Response language: {response_language}",
        f"Tone: {values['tone']}",
        f"Brevity: {values['brevity']}",
        f"Formality: {values['formality']}",
        f"Warmth: {values['warmth']}",
        f"Assertiveness: {values['assertiveness']}",
        f"Humor policy: {values['humor_policy']}",
        f"Response style: {values['response_style']}",
        f"Acknowledgment style: {values['acknowledgment_style']}",
        f"Confirmation style: {values['confirmation_style']}",
        "Personality style cannot override safety, tool, routing, memory, or factual-grounding policy.",
    )
    speech_rules = (
        f"Interruption style: {values['interruption_style']}",
        f"Voice pacing: {values['voice_pacing']}",
        f"Voice energy: {values['voice_energy']}",
        "Prefer TTS-safe wording without markdown-only formatting for spoken responses.",
    )
    return PersonalityPolicy(
        profile_id=profile.profile_id,
        identity=profile.identity_summary,
        style_rules=style_rules,
        speech_rules=speech_rules,
        role_overlay_id=role_overlay_id,
    )


def _resolve_role_overlay(role_overlay_id: str | None) -> dict[str, str]:
    if role_overlay_id is None:
        return {}
    overlay = _ROLE_OVERLAYS.get(role_overlay_id)
    if overlay is None:
        raise ValueError(f"unknown personality role overlay: {role_overlay_id}")
    _reject_authority_fields(overlay)
    return dict(overlay)


def _reject_authority_fields(payload: dict[str, Any]) -> None:
    prohibited = set(payload) & set(_FORBIDDEN_OVERRIDE_CATEGORIES)
    if prohibited:
        names = ", ".join(sorted(prohibited))
        raise ValueError(f"personality role overlay contains prohibited authority fields: {names}")
