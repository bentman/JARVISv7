from __future__ import annotations

from backend.app.personality.adapter import apply_personality
from backend.app.personality.loader import list_personality_profiles, load_default_personality, load_personality, load_personality_profile
from backend.app.personality.policy import compile_personality_policy
from backend.app.personality.schema import PersonalityProfile


def test_personality_profile_roundtrips_dict():
    profile = PersonalityProfile(
        "default",
        "JARVIS",
        "professional",
        "concise",
        "semi-formal",
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
    assert profile.enabled is True


def test_load_default_personality_returns_configured_profile():
    profile = load_default_personality()

    assert profile.profile_id == "default"
    assert profile.display_name == "JARVIS"
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


def test_load_personality_profile_rejects_unknown_and_unsafe_id():
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
                "extra_instruction: unsafe",
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


def test_personality_profile_rejects_prohibited_authority_fields(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        "\n".join(
            [
                "profile_id: test",
                "display_name: JARVIS",
                "tone: calm",
                "brevity: concise",
                "formality: formal",
                "tool_permissions:",
                "  filesystem.write: true",
            ]
        ),
        encoding="utf-8",
    )

    try:
        load_personality(path)
    except ValueError as exc:
        assert "prohibited authority fields" in str(exc)
    else:
        raise AssertionError("prohibited personality authority field accepted")


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
    assert any("Tone: professional" == rule for rule in first.style_rules)
    assert any("Voice pacing: normal" == rule for rule in first.speech_rules)
    assert "tool_permissions" in first.forbidden_overrides


def test_compile_personality_policy_applies_style_only_overlay():
    policy = compile_personality_policy(load_default_personality(), role_overlay_id="code_plan")

    assert policy.role_overlay_id == "code_plan"
    assert "Tone: precise" in policy.style_rules
    assert "Response style: implementation_boundary_first" in policy.style_rules
    assert all("tool_permissions" not in rule for rule in policy.style_rules)


def test_compile_personality_policy_rejects_unknown_overlay():
    try:
        compile_personality_policy(load_default_personality(), role_overlay_id="unknown")
    except ValueError as exc:
        assert "unknown personality role overlay" in str(exc)
    else:
        raise AssertionError("unknown personality role overlay accepted")


def test_compile_personality_policy_rejects_prohibited_overlay_fields(monkeypatch):
    from backend.app.personality import policy as policy_module

    monkeypatch.setitem(policy_module._ROLE_OVERLAYS, "unsafe", {"tool_permissions": "all"})  # noqa: SLF001

    try:
        compile_personality_policy(load_default_personality(), role_overlay_id="unsafe")
    except ValueError as exc:
        assert "prohibited authority fields" in str(exc)
    else:
        raise AssertionError("prohibited role overlay authority field accepted")
