from __future__ import annotations

from backend.app.cognition.style_guard import apply_personality_style_guard
from backend.app.personality.loader import load_default_personality, load_personality_profile
from backend.app.personality.policy import compile_personality_policy


def test_style_guard_is_deterministic():
    policy = compile_personality_policy(load_default_personality())

    first = apply_personality_style_guard("Sure, ready now.", policy, modality="voice")
    second = apply_personality_style_guard("Sure, ready now.", policy, modality="voice")

    assert first == second


def test_style_guard_trims_generic_voice_acknowledgment_for_concise_no_intro_profile():
    policy = compile_personality_policy(load_personality_profile("concise"))

    assert apply_personality_style_guard("Sure, ready now.", policy, modality="voice") == "ready now."


def test_style_guard_preserves_text_acknowledgment_for_default_profile():
    policy = compile_personality_policy(load_default_personality())

    assert apply_personality_style_guard("Sure, ready now.", policy, modality="text") == "Sure, ready now."


def test_style_guard_keeps_ack_only_response_instead_of_emptying_it():
    policy = compile_personality_policy(load_personality_profile("concise"))

    assert apply_personality_style_guard("Okay.", policy, modality="voice") == "Okay."
    assert apply_personality_style_guard("Sure!", policy, modality="voice") == "Sure!"
