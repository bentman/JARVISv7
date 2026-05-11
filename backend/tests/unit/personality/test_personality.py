from __future__ import annotations

from backend.app.personality.adapter import apply_personality
from backend.app.personality.loader import list_personality_profiles, load_default_personality, load_personality, load_personality_profile
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


def test_adapter_appends_all_behavioral_guidance_without_profile_id():
    profile = PersonalityProfile("concise", "JARVIS", "direct", "terse", "semi-formal")

    prompt = apply_personality("prompt", profile)

    assert prompt == "prompt"


def test_adapter_uses_non_empty_addendum_once():
    addendum = "Prefer short answers."
    profile = PersonalityProfile("concise", "JARVIS", "direct", "terse", "semi-formal", addendum)

    prompt = apply_personality(f"prompt\n{addendum}", profile)

    assert prompt == f"prompt\n{addendum}"


def test_list_personality_profiles_loads_all_configured_profiles():
    profiles = {profile.profile_id: profile for profile in list_personality_profiles()}

    assert set(profiles) >= {"default", "concise", "warm"}
    for profile in profiles.values():
        assert profile.display_name
        assert profile.tone
        assert profile.brevity
        assert profile.formality
        assert isinstance(profile.system_prompt_addendum, str)


def test_load_personality_profile_rejects_unknown_and_unsafe_id():
    assert load_personality_profile("warm").profile_id == "warm"
    for profile_id in ["missing", "../default", " default"]:
        try:
            load_personality_profile(profile_id)
        except (FileNotFoundError, ValueError):
            pass
        else:
            raise AssertionError(f"invalid profile id accepted: {profile_id}")