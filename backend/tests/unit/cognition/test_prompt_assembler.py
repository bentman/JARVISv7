from __future__ import annotations

from backend.app.cognition.prompt_assembler import assemble_prompt
from backend.app.personality.schema import PersonalityProfile


def _profile(addendum: str = "") -> PersonalityProfile:
    return PersonalityProfile("default", "JARVIS", "professional", "concise", "semi-formal", addendum)


def test_assemble_includes_transcript():
    prompt = assemble_prompt("hello world", _profile())

    assert "User: hello world" in prompt


def test_assemble_includes_personality_addendum_when_set():
    prompt = assemble_prompt("hello", _profile("Use a calm voice."))

    assert "Use a calm voice." in prompt


def test_assemble_includes_working_memory_lines_when_provided():
    prompt = assemble_prompt("hello", _profile(), working_memory=["previous answer"])

    assert "Working memory:" in prompt
    assert "- previous answer" in prompt