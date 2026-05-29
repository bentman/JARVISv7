from __future__ import annotations

from backend.app.cognition.prompt_assembler import assemble_prompt
from backend.app.memory.retrieval import RetrievedFact
from backend.app.personality.schema import PersonalityProfile


def _profile(addendum: str = "") -> PersonalityProfile:
    return PersonalityProfile("default", "JARVIS", "professional", "concise", "semi-formal", addendum)


def test_assemble_includes_transcript():
    prompt = assemble_prompt("hello world", _profile())

    assert "User: hello world" in prompt
    assert prompt.endswith("Assistant:")
    assert "Do not continue the dialogue" in prompt


def test_assemble_ignores_personality_addendum_for_prompt_content():
    prompt = assemble_prompt("hello", _profile("Use a calm voice."))

    assert "Use a calm voice." not in prompt


def test_assemble_includes_working_memory_lines_when_provided():
    prompt = assemble_prompt("hello", _profile(), working_memory=["previous answer"])

    assert "Working memory:" in prompt
    assert "- previous answer" in prompt


def test_assemble_includes_retrieved_context_when_provided():
    prompt = assemble_prompt(
        "hello",
        _profile(),
        retrieved_context=[
            RetrievedFact(
                turn_id="turn-123456789",
                session_id="session-abcdefghi",
                content="prior answer",
                source_field="response_text",
                relevance_method="keyword",
            )
        ],
    )

    assert "Relevant prior context:" in prompt
    assert "- [session-/turn-123] prior answer" in prompt


def test_assemble_omits_retrieved_section_when_retrieved_context_is_none():
    prompt = assemble_prompt("hello", _profile(), retrieved_context=None)

    assert "Relevant prior context:" not in prompt


def test_assemble_omits_retrieved_section_when_retrieved_context_is_empty():
    prompt = assemble_prompt("hello", _profile(), retrieved_context=[])

    assert "Relevant prior context:" not in prompt
