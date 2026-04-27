from __future__ import annotations

from backend.app.personality.adapter import apply_personality
from backend.app.personality.loader import load_default_personality, load_personality
from backend.app.personality.schema import PersonalityProfile


def test_personality_profile_roundtrips_dict():
    profile = PersonalityProfile("default", "JARVIS", "professional", "concise", "semi-formal")

    assert PersonalityProfile.from_dict(profile.to_dict()) == profile


def test_load_personality_reads_yaml(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        "profile_id: test\ndisplay_name: JARVIS\ntone: calm\nbrevity: concise\nformality: formal\n",
        encoding="utf-8",
    )

    profile = load_personality(path)

    assert profile.profile_id == "test"
    assert profile.tone == "calm"


def test_load_default_personality_returns_configured_profile():
    profile = load_default_personality()

    assert profile.profile_id == "default"
    assert profile.display_name == "JARVIS"


def test_adapter_returns_prompt_unchanged_in_c1():
    profile = PersonalityProfile("default", "JARVIS", "professional", "concise", "semi-formal")

    assert apply_personality("prompt", profile) == "prompt"