from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.states import ConversationState
from backend.app.personality.schema import PersonalityProfile
from backend.app.runtimes.llm.base import LLMBase
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.tts.base import TTSBase


class FakeSTT(STTBase):
    def __init__(self, transcript: str = "hello world", error: Exception | None = None) -> None:
        super().__init__(device="cpu", model_path=Path("unused"))
        self.transcript = transcript
        self.error = error
        self.calls = 0

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.transcript

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


class FakeLLM(LLMBase):
    def __init__(self, response: str = "ready", error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.prompts: list[str] = []

    def generate(self, prompt: str, **kwargs: object) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.response

    def is_available(self) -> bool:
        return True

    def runtime_name(self) -> str:
        return "fake"


def _personality() -> PersonalityProfile:
    return PersonalityProfile(
        profile_id="test",
        display_name="JARVIS",
        tone="professional",
        brevity="concise",
        formality="semi-formal",
        system_prompt_addendum="Prefer direct answers.",
    )


def _engine(stt: FakeSTT | None = None, llm: FakeLLM | None = None) -> TurnEngine:
    return TurnEngine(stt=stt or FakeSTT(), tts=FakeTTS(), llm=llm or FakeLLM(), personality=_personality())


def test_text_turn_returns_response_for_known_prompt():
    llm = FakeLLM(response="hello")
    result = _engine(llm=llm).run_text_turn("hello world")

    assert result.final_state == ConversationState.IDLE
    assert result.transcript == "hello world"
    assert result.response_text == "hello"
    assert result.failure_reason is None
    assert "Prefer direct answers." in llm.prompts[0]


def test_voice_turn_calls_stt_then_llm():
    stt = FakeSTT(transcript="hello world")
    llm = FakeLLM(response="ready")
    result = _engine(stt=stt, llm=llm).run_voice_turn(np.zeros(1600, dtype=np.float32), 16000)

    assert stt.calls == 1
    assert "hello world" in llm.prompts[0]
    assert result.response_text == "ready"
    assert result.final_state == ConversationState.IDLE


def test_turn_engine_transitions_through_expected_states():
    result = _engine().run_voice_turn(np.zeros(1600, dtype=np.float32), 16000)

    assert result.final_state == ConversationState.IDLE
    assert result.failure_reason is None


def test_turn_engine_closes_to_failed_on_stt_error():
    result = _engine(stt=FakeSTT(error=RuntimeError("stt failed"))).run_voice_turn(
        np.zeros(1600, dtype=np.float32),
        16000,
    )

    assert result.final_state == ConversationState.FAILED
    assert result.failure_reason == "stt failed"


def test_turn_engine_closes_to_failed_on_llm_error():
    result = _engine(llm=FakeLLM(error=RuntimeError("llm failed"))).run_text_turn("hello")

    assert result.final_state == ConversationState.FAILED
    assert result.failure_reason == "llm failed"


def test_speaking_state_raises_not_implemented_in_c1():
    with pytest.raises(NotImplementedError, match="pending C.2"):
        _engine().enter_stub_state(ConversationState.SPEAKING)


def test_acting_and_interrupted_states_raise_not_implemented_in_c1():
    engine = _engine()

    with pytest.raises(NotImplementedError):
        engine.enter_stub_state(ConversationState.ACTING)
    with pytest.raises(NotImplementedError):
        engine.enter_stub_state(ConversationState.INTERRUPTED)