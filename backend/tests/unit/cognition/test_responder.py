from __future__ import annotations

from backend.app.cognition.responder import bound_single_turn_response, sanitize_for_tts


def test_sanitize_strips_markdown_bold():
    assert sanitize_for_tts("This is **important**") == "This is important"


def test_sanitize_strips_code_fences():
    assert sanitize_for_tts("say ```python\nprint('x')\n``` done") == "say done"


def test_sanitize_returns_plain_text_unchanged():
    assert sanitize_for_tts("plain text") == "plain text"


def test_bound_single_turn_response_strips_leading_assistant_label():
    assert bound_single_turn_response("Assistant: Ready.") == "Ready."


def test_bound_single_turn_response_trims_fabricated_continuation_turns():
    text = "Here is the answer.\nUser: another question\nAssistant: another answer"

    assert bound_single_turn_response(text) == "Here is the answer."
