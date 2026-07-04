from __future__ import annotations

from backend.app.personality.loader import load_default_personality, load_personality
from backend.app.personality.policy import compile_personality_policy


def test_personality_profile_rejects_prohibited_authority_fields(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        "\n".join(
            [
                "profile_id: test",
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
                "routing_policy: local_only",
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


def test_compile_personality_policy_rejects_role_overlay():
    try:
        compile_personality_policy(load_default_personality(), role_overlay_id="invalid")
    except ValueError as exc:
        assert "role overlays are not supported" in str(exc)
    else:
        raise AssertionError("role overlay accepted")
