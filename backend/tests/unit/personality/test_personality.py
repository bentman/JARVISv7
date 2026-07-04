from __future__ import annotations

from backend.app.personality.adapter import apply_personality
from backend.app.personality.loader import (
    list_personality_profiles,
    list_personality_profiles_with_errors,
    load_default_personality,
    load_personality,
    load_personality_profile,
)
from backend.app.personality.policy import compile_personality_policy
from backend.app.personality.schema import PersonalityProfile


def test_personality_profile_roundtrips_dict():
    profile = PersonalityProfile(
        "default",
        "JARVIS",
        "professional",
        "concise",
        "semi-formal",
        response_language="english",
        locale="en",
        system_prompt="Use this persona.",
        style_rules=("Prefer direct answers.",),
        speech_rules=("Use TTS-safe wording.",),
        example_messages=({"role": "user", "content": "Status?"}, {"role": "assistant", "content": "Ready."}),
        generation={"temperature": 0.5, "max_tokens": 120, "stop": ["\nUser:"]},
        identity_summary="A local-first assistant.",
        warmth="moderate",
        assertiveness="moderate",
        humor_policy="none",
        response_style="direct_answer",
        acknowledgment_style="minimal",
        confirmation_style="explicit_when_needed",
        interruption_style="stop_cleanly",
        voice_pacing="normal",
        voice_energy="neutral",
        enabled=True,
    )

    assert PersonalityProfile.from_dict(profile.to_dict()) == profile


def test_load_personality_reads_minimal_legacy_yaml_with_defaults(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        "profile_id: test\ndisplay_name: JARVIS\ntone: calm\nbrevity: concise\nformality: formal\n",
        encoding="utf-8",
    )

    profile = load_personality(path)

    assert profile.profile_id == "test"
    assert profile.tone == "calm"
    assert profile.identity_summary
    assert profile.warmth == "moderate"
    assert profile.response_language == ""
    assert profile.locale == ""
    assert profile.system_prompt == ""
    assert profile.style_rules == ()
    assert profile.speech_rules == ()
    assert profile.example_messages == ()
    assert profile.generation == {}
    assert profile.enabled is True


def test_load_personality_rejects_scalar_style_rules(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        "\n".join(
            [
                "profile_id: test",
                "display_name: JARVIS",
                "tone: calm",
                "brevity: concise",
                "formality: formal",
                "style_rules: terse",
            ]
        ),
        encoding="utf-8",
    )

    try:
        load_personality(path)
    except ValueError as exc:
        assert "style_rules must be a list of non-empty strings" in str(exc)
    else:
        raise AssertionError("scalar style_rules value accepted")


def test_load_personality_rejects_scalar_speech_rules(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        "\n".join(
            [
                "profile_id: test",
                "display_name: JARVIS",
                "tone: calm",
                "brevity: concise",
                "formality: formal",
                "speech_rules: brisk",
            ]
        ),
        encoding="utf-8",
    )

    try:
        load_personality(path)
    except ValueError as exc:
        assert "speech_rules must be a list of non-empty strings" in str(exc)
    else:
        raise AssertionError("scalar speech_rules value accepted")


def test_load_personality_accepts_rule_lists_as_tuples(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        "\n".join(
            [
                "profile_id: test",
                "display_name: JARVIS",
                "tone: calm",
                "brevity: concise",
                "formality: formal",
                "style_rules:",
                "  - Prefer short answers.",
                "speech_rules:",
                "  - Speak briskly.",
            ]
        ),
        encoding="utf-8",
    )

    profile = load_personality(path)

    assert profile.style_rules == ("Prefer short answers.",)
    assert profile.speech_rules == ("Speak briskly.",)


def test_load_default_personality_returns_configured_profile():
    profile = load_default_personality()

    assert profile.profile_id == "default"
    assert profile.display_name == "Morgan"
    assert profile.identity_summary
    assert profile.response_style == "direct_answer"


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
        assert isinstance(profile.response_language, str)
        assert isinstance(profile.locale, str)
        assert profile.system_prompt
        assert profile.style_rules
        assert profile.speech_rules
        assert profile.example_messages
        assert profile.generation
        assert profile.identity_summary
        assert profile.warmth
        assert profile.assertiveness
        assert profile.humor_policy
        assert profile.response_style
        assert profile.acknowledgment_style
        assert profile.confirmation_style
        assert profile.interruption_style
        assert profile.voice_pacing
        assert profile.voice_energy
        assert profile.enabled is True


def test_load_personality_profile_rejects_unknown_and_bad_id():
    assert load_personality_profile("warm").profile_id == "warm"
    for profile_id in ["missing", "../default", " default"]:
        try:
            load_personality_profile(profile_id)
        except (FileNotFoundError, ValueError):
            pass
        else:
            raise AssertionError(f"invalid profile id accepted: {profile_id}")


def test_personality_profile_rejects_unknown_fields(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        "\n".join(
            [
                "profile_id: test",
                "display_name: JARVIS",
                "tone: calm",
                "brevity: concise",
                "formality: formal",
                "extra_instruction: invalid",
            ]
        ),
        encoding="utf-8",
    )

    try:
        load_personality(path)
    except ValueError as exc:
        assert "unknown fields" in str(exc)
    else:
        raise AssertionError("unknown personality field accepted")


def test_list_personality_profiles_isolates_invalid_profile_files(tmp_path, monkeypatch):
    personality_dir = tmp_path / "personality"
    personality_dir.mkdir()
    (personality_dir / "valid.yaml").write_text(
        "\n".join(
            [
                "profile_id: valid",
                "display_name: JARVIS",
                "tone: calm",
                "brevity: concise",
                "formality: formal",
            ]
        ),
        encoding="utf-8",
    )
    (personality_dir / "invalid.yaml").write_text("profile_id: invalid\nsystem_prompt: []\n", encoding="utf-8")
    monkeypatch.setattr("backend.app.personality.loader.CONFIG_DIR", tmp_path)

    result = list_personality_profiles_with_errors()

    assert [profile.profile_id for profile in result.profiles] == ["valid"]
    assert len(result.profile_errors) == 1
    assert result.profile_errors[0].profile_path == "invalid.yaml"


def test_list_personality_profiles_reports_scalar_rule_profile_errors(tmp_path, monkeypatch):
    personality_dir = tmp_path / "personality"
    personality_dir.mkdir()
    (personality_dir / "valid.yaml").write_text(
        "\n".join(
            [
                "profile_id: valid",
                "display_name: JARVIS",
                "tone: calm",
                "brevity: concise",
                "formality: formal",
                "style_rules:",
                "  - Keep it short.",
            ]
        ),
        encoding="utf-8",
    )
    (personality_dir / "invalid.yaml").write_text(
        "\n".join(
            [
                "profile_id: invalid",
                "display_name: JARVIS",
                "tone: calm",
                "brevity: concise",
                "formality: formal",
                "style_rules: terse",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("backend.app.personality.loader.CONFIG_DIR", tmp_path)

    result = list_personality_profiles_with_errors()

    assert [profile.profile_id for profile in result.profiles] == ["valid"]
    assert len(result.profile_errors) == 1
    assert result.profile_errors[0].profile_path == "invalid.yaml"
    assert "style_rules must be a list of non-empty strings" in result.profile_errors[0].reason


def test_personality_profile_rejects_invalid_style_values():
    try:
        PersonalityProfile("test", "JARVIS", "chaotic", "concise", "formal")
    except ValueError as exc:
        assert "invalid personality tone" in str(exc)
    else:
        raise AssertionError("invalid personality tone accepted")


def test_compile_personality_policy_is_deterministic():
    profile = load_default_personality()

    first = compile_personality_policy(profile)
    second = compile_personality_policy(profile)

    assert first == second
    assert first.profile_id == "default"
    assert first.identity == profile.identity_summary
    assert first.system_prompt
    assert first.locale == "en"
    assert first.example_messages
    assert first.generation["max_tokens"] == 220
    assert any("Response language: en" == rule for rule in first.style_rules)
    assert any("Tone: professional" == rule for rule in first.style_rules)
    assert any("Voice pacing: normal" == rule for rule in first.speech_rules)
    assert first.forbidden_overrides


def test_compile_personality_policy_applies_style_only_overlay():
    policy = compile_personality_policy(load_default_personality(), role_overlay_id="code_plan")

    assert policy.role_overlay_id == "code_plan"
    assert "Tone: precise" in policy.style_rules
    assert "Response style: implementation_boundary_first" in policy.style_rules


def test_compile_personality_policy_rejects_unknown_overlay():
    try:
        compile_personality_policy(load_default_personality(), role_overlay_id="unknown")
    except ValueError as exc:
        assert "unknown personality role overlay" in str(exc)
    else:
        raise AssertionError("unknown personality role overlay accepted")
