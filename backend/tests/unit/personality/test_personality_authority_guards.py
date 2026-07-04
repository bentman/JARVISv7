from __future__ import annotations

from backend.app.personality.loader import load_default_personality, load_personality
from backend.app.personality.policy import compile_personality_policy


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


def test_compile_personality_policy_rejects_prohibited_overlay_fields(monkeypatch):
    from backend.app.personality import policy as policy_module

    monkeypatch.setitem(policy_module._ROLE_OVERLAYS, "invalid", {"routing_policy": "local_only"})  # noqa: SLF001

    try:
        compile_personality_policy(load_default_personality(), role_overlay_id="invalid")
    except ValueError as exc:
        assert "prohibited authority fields" in str(exc)
    else:
        raise AssertionError("prohibited role overlay authority field accepted")
