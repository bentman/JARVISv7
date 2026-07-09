from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.artifacts.storage import read_session_artifact, read_turn_artifact
from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.memory.write_policy import WritePolicy
from backend.app.personality.schema import (
    PersonalityExample,
    PersonalityProfile,
    PersonalityStyle,
    PersonalityTraits,
)
from backend.app.runtimes.llm.base import LLMBase
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.tts.base import TTSBase


class FakeSTT(STTBase):
    def __init__(self) -> None:
        super().__init__(device="cpu", model_path=Path("unused"))

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        return "unused"

    def is_available(self) -> bool:
        return True


class FakeTTS(TTSBase):
    def __init__(self) -> None:
        super().__init__(device="cpu", model_path=Path("unused"))

    def synthesize(self, text: str) -> np.ndarray:
        return np.array([], dtype=np.float32)

    def sample_rate(self) -> int:
        return 24000

    def is_available(self) -> bool:
        return False


class SequencedLLM(LLMBase):
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def generate(self, prompt: str, **kwargs: object) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)

    def is_available(self) -> bool:
        return True

    def runtime_name(self) -> str:
        return "fake"


def _personality() -> PersonalityProfile:
    return PersonalityProfile(
        profile_id="test",
        display_name="JARVIS",
        description="Balanced assistant.",
        locale="en",
        system="Answer directly.",
        style=PersonalityStyle(
            max_words_default=120,
            structure="Answer first.",
            do=("Lead with the answer.",),
            avoid=("Filler.",),
        ),
        traits=PersonalityTraits(
            warmth="medium", assertiveness="medium", detail="medium", humor="light"
        ),
        examples=(PersonalityExample(user="Status?", assistant="Ready."),),
        generation={
            "temperature": 0.5,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.08,
            "max_tokens": 120,
            "stop": ["\nUser:", "\nAssistant:"],
        },
    )


def _engine(tmp_path, llm: SequencedLLM) -> tuple[TurnEngine, SessionManager]:
    manager = SessionManager(session_id="session-1", turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")
    engine = TurnEngine(
        stt=FakeSTT(),
        tts=FakeTTS(),
        llm=llm,
        personality=_personality(),
        session_manager=manager,
        write_policy=WritePolicy(max_working_memory_entries=10),
    )
    return engine, manager


def test_two_text_turns_produce_two_artifacts_in_session(tmp_path):
    engine, manager = _engine(tmp_path, SequencedLLM(["first response", "second response"]))

    first = engine.run_text_turn("first")
    second = engine.run_text_turn("second")

    assert first.final_state == ConversationState.IDLE
    assert second.final_state == ConversationState.IDLE
    assert len(manager.turn_artifacts) == 2
    assert read_turn_artifact("session-1", first.turn_id, tmp_path / "turns") is not None
    assert read_turn_artifact("session-1", second.turn_id, tmp_path / "turns") is not None


def test_second_turn_context_includes_first_turn_response_in_working_memory(tmp_path):
    llm = SequencedLLM(["first response", "second response"])
    engine, manager = _engine(tmp_path, llm)

    engine.run_text_turn("first")
    engine.run_text_turn("second")

    assert manager.working_memory.as_list() == ["first response", "second response"]
    assert "Working memory:" in llm.prompts[1]
    assert "- first response" in llm.prompts[1]


def test_session_close_writes_session_artifact(tmp_path):
    engine, manager = _engine(tmp_path, SequencedLLM(["first response", "second response"]))
    first = engine.run_text_turn("first")
    second = engine.run_text_turn("second")

    session_path = manager.close_session()
    session_artifact = read_session_artifact("session-1", tmp_path / "sessions")

    assert session_path == tmp_path / "sessions" / "session-1" / "session.json"
    assert session_artifact is not None
    assert session_artifact.turn_ids == [first.turn_id, second.turn_id]
    assert session_artifact.final_state == "IDLE"


def test_two_turn_session_retrieves_semantic_memory(tmp_path):
    from backend.app.memory.semantic import SemanticMemory

    db_path = tmp_path / "semantic.sqlite"
    semantic = SemanticMemory(db_path)

    # Pre-populate a semantic fact
    semantic.write_fact(
        text="JARVIS is running on a high-end local system.",
        source_session_id="prior-session",
        source_turn_id="prior-turn",
        source_field="response_text",
    )

    llm = SequencedLLM(["understood"])
    manager = SessionManager(session_id="session-2", turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")
    engine = TurnEngine(
        stt=FakeSTT(),
        tts=FakeTTS(),
        llm=llm,
        personality=_personality(),
        session_manager=manager,
        write_policy=WritePolicy(max_working_memory_entries=10),
        semantic=semantic,
    )

    # Run a text turn that matches the semantic fact keyword
    result = engine.run_text_turn("Tell me about local system")
    assert result.final_state == ConversationState.IDLE

    # Verify that the semantic fact was retrieved and injected into the prompt
    assert len(llm.prompts) == 1
    assert "Relevant prior context:" in llm.prompts[0]
    assert "JARVIS is running on a high-end local system." in llm.prompts[0]

    # Verify turn artifact records retrieved memory refs
    assert len(manager.turn_artifacts) == 1
    artifact = manager.turn_artifacts[0]
    assert "prior-turn" in artifact.retrieved_memory_refs