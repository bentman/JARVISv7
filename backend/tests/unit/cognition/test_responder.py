from __future__ import annotations

from backend.app.cognition.responder import sanitize_for_tts


def test_sanitize_strips_markdown_bold():
    assert sanitize_for_tts("This is **important**") == "This is important"


def test_sanitize_strips_code_fences():
    assert sanitize_for_tts("say ```python\nprint('x')\n``` done") == "say done"


def test_sanitize_returns_plain_text_unchanged():
    assert sanitize_for_tts("plain text") == "plain text"