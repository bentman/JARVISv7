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


def _valid_yaml(profile_id: str = "test") -> str:
    return "\n".join(
        [
            f"profile_id: {profile_id}",
            "display_name: Test",
            "description: Test profile.",
            "locale: en",
            "system: Answer directly.",
            "style:",
            "  max_words_default: 80",
            "  structure: Answer then next step.",
            "  do:",
            "    - Lead with the answer.",
            "  avoid:",
            "    - Filler.",
            "traits:",
            "  warmth: medium",
            "  assertiveness: medium",
            "  detail: medium",
            "  humor: light",
            "examples:",
            "  - user: Status?",
            "    assistant: Ready.",
            "generation:",
            "  temperature: 0.5",
            "  top_p: 0.9",
            "  top_k: 40",
            "  repeat_penalty: 1.08",
            "  max_tokens: 120",
            "  stop:",
            "    - \"\\nUser:\"",
            "    - \"\\nAssistant:\"",
            "enabled: true",
        ]
    )


def test_personality_profile_roundtrips_dict(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(_valid_yaml(), encoding="utf-8")
    profile = load_personality(path)

    assert PersonalityProfile.from_dict(profile.to_dict()) == profile


def test_valid_target_profiles_load():
    profiles = {profile.profile_id: profile for profile in list_personality_profiles()}

    assert set(profiles) >= {"default", "concise", "warm", "jarvis", "sage"}
    assert profiles["jarvis"].display_name == "J.A.R.V.I.S"
    assert profiles["jarvis"].locale == "en_GB"
    assert profiles["sage"].display_name == "Sage"
    for profile in profiles.values():
        assert profile.description
        assert profile.system
        assert profile.style.max_words_default > 0
        assert profile.style.do
        assert profile.style.avoid
        assert profile.examples
        assert profile.generation["max_tokens"] > 0
        assert profile.enabled is True


def test_load_default_personality_returns_configured_profile():
    profile = load_default_personality()

    assert profile.profile_id == "default"
    assert profile.display_name == "Morgan"
    assert profile.description == "Balanced general assistant."


def test_adapter_remains_noop():
    profile = load_default_personality()

    assert apply_personality("prompt", profile) == "prompt"


def test_load_personality_profile_rejects_unknown_and_bad_id():
    assert load_personality_profile("warm").profile_id == "warm"
    for profile_id in ["missing", "../default", " default"]:
        try:
            load_personality_profile(profile_id)
        except (FileNotFoundError, ValueError):
            pass
        else:
            raise AssertionError(f"invalid profile id accepted: {profile_id}")


def test_personality_profile_rejects_old_active_fields(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(_valid_yaml() + "\ntone: calm\n", encoding="utf-8")

    try:
        load_personality(path)
    except ValueError as exc:
        assert "unknown fields" in str(exc)
        assert "tone" in str(exc)
    else:
        raise AssertionError("old personality field accepted")


def test_personality_profile_rejects_prohibited_authority_fields(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(_valid_yaml() + "\nrouting_policy: local_only\n", encoding="utf-8")

    try:
        load_personality(path)
    except ValueError as exc:
        assert "prohibited authority fields" in str(exc)
    else:
        raise AssertionError("prohibited personality authority field accepted")


def test_load_personality_rejects_scalar_style_do(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(_valid_yaml().replace("  do:\n    - Lead with the answer.", "  do: terse"), encoding="utf-8")

    try:
        load_personality(path)
    except ValueError as exc:
        assert "style.do must be a list of non-empty strings" in str(exc)
    else:
        raise AssertionError("scalar style.do value accepted")


def test_load_personality_rejects_scalar_style_avoid(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(_valid_yaml().replace("  avoid:\n    - Filler.", "  avoid: brisk"), encoding="utf-8")

    try:
        load_personality(path)
    except ValueError as exc:
        assert "style.avoid must be a list of non-empty strings" in str(exc)
    else:
        raise AssertionError("scalar style.avoid value accepted")


def test_valid_yaml_list_values_load_as_tuples(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(_valid_yaml(), encoding="utf-8")

    profile = load_personality(path)

    assert profile.style.do == ("Lead with the answer.",)
    assert profile.style.avoid == ("Filler.",)


def test_malformed_examples_report_through_profile_errors(tmp_path, monkeypatch):
    personality_dir = tmp_path / "personality"
    personality_dir.mkdir()
    (personality_dir / "valid.yaml").write_text(_valid_yaml("valid"), encoding="utf-8")
    (personality_dir / "invalid.yaml").write_text(
        _valid_yaml("invalid").replace("  - user: Status?\n    assistant: Ready.", "  - user: Status?"),
        encoding="utf-8",
    )
    monkeypatch.setattr("backend.app.personality.loader.CONFIG_DIR", tmp_path)

    result = list_personality_profiles_with_errors()

    assert [profile.profile_id for profile in result.profiles] == ["valid"]
    assert len(result.profile_errors) == 1
    assert result.profile_errors[0].profile_path == "invalid.yaml"
    assert "examples[0] must include user and assistant" in result.profile_errors[0].reason


def test_list_personality_profiles_reports_scalar_style_profile_errors(tmp_path, monkeypatch):
    personality_dir = tmp_path / "personality"
    personality_dir.mkdir()
    (personality_dir / "valid.yaml").write_text(_valid_yaml("valid"), encoding="utf-8")
    (personality_dir / "invalid.yaml").write_text(
        _valid_yaml("invalid").replace("  do:\n    - Lead with the answer.", "  do: terse"),
        encoding="utf-8",
    )
    monkeypatch.setattr("backend.app.personality.loader.CONFIG_DIR", tmp_path)

    result = list_personality_profiles_with_errors()

    assert [profile.profile_id for profile in result.profiles] == ["valid"]
    assert len(result.profile_errors) == 1
    assert result.profile_errors[0].profile_path == "invalid.yaml"
    assert "style.do must be a list of non-empty strings" in result.profile_errors[0].reason


def test_compile_personality_policy_is_deterministic_and_strong():
    profile = load_personality_profile("jarvis")

    first = compile_personality_policy(profile)
    second = compile_personality_policy(profile)

    assert first == second
    assert first.profile_id == "jarvis"
    assert first.system_text
    assert "Default maximum answer length: 170 words" in first.system_text
    assert "British spelling" in first.system_text
    assert "one dry aside" in first.system_text
    assert first.locale == "en_GB"
    assert first.examples
    assert first.generation["max_tokens"] == 280
    assert first.forbidden_overrides
    for legacy in ("Tone:", "Brevity:", "Warmth:", "Voice pacing:"):
        assert legacy not in first.system_text


def test_compile_personality_policy_rejects_role_overlay():
    try:
        compile_personality_policy(load_default_personality(), role_overlay_id="code_plan")
    except ValueError as exc:
        assert "role overlays are not supported" in str(exc)
    else:
        raise AssertionError("role overlay accepted")
