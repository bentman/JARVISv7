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
    def __init__(self, *, available: bool = False, error: Exception | None = None) -> None:
        super().__init__(device="cpu", model_path=Path("unused"))
        self.available = available
        self.error = error
        self.calls = 0
        self.synthesized_texts: list[str] = []

    def synthesize(self, text: str) -> np.ndarray:
        self.calls += 1
        self.synthesized_texts.append(text)
        if self.error is not None:
            raise self.error
        return np.array([0.0, 0.1, -0.1], dtype=np.float32)

    def sample_rate(self) -> int:
        if self.error is not None:
            raise self.error
        return 24000

    def is_available(self) -> bool:
        return self.available


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


def _engine(stt: FakeSTT | None = None, tts: FakeTTS | None = None, llm: FakeLLM | None = None) -> TurnEngine:
    return TurnEngine(stt=stt or FakeSTT(), tts=tts or FakeTTS(), llm=llm or FakeLLM(), personality=_personality())


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
    assert result.tts_degraded is True
    assert result.tts_degraded_reason == "TTS runtime is unavailable"


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


def test_speaking_state_no_longer_raises_not_implemented_in_c2():
    _engine().enter_stub_state(ConversationState.SPEAKING)


def test_acting_and_interrupted_states_raise_not_implemented_in_c1():
    engine = _engine()

    with pytest.raises(NotImplementedError):
        engine.enter_stub_state(ConversationState.ACTING)
    with pytest.raises(NotImplementedError):
        engine.enter_stub_state(ConversationState.INTERRUPTED)


def test_speaking_state_entered_when_tts_available(monkeypatch: pytest.MonkeyPatch):
    tts = FakeTTS(available=True)
    playback_calls: list[tuple[np.ndarray, int]] = []

    def fake_play(audio: np.ndarray, sample_rate: int) -> None:
        playback_calls.append((audio, sample_rate))

    monkeypatch.setattr("backend.app.conversation.engine.playback.play", fake_play)

    result = _engine(tts=tts).run_voice_turn(np.zeros(1600, dtype=np.float32), 16000)

    assert result.final_state == ConversationState.IDLE
    assert result.failure_reason is None
    assert result.tts_degraded is False
    assert result.tts_degraded_reason is None
    assert tts.calls == 1
    assert len(playback_calls) == 1
    assert playback_calls[0][1] == 24000


def test_speaking_state_skipped_when_tts_unavailable(monkeypatch: pytest.MonkeyPatch):
    tts = FakeTTS(available=False)
    playback_called = False

    def fake_play(audio: np.ndarray, sample_rate: int) -> None:
        nonlocal playback_called
        playback_called = True

    monkeypatch.setattr("backend.app.conversation.engine.playback.play", fake_play)

    result = _engine(tts=tts).run_voice_turn(np.zeros(1600, dtype=np.float32), 16000)

    assert result.final_state == ConversationState.IDLE
    assert result.failure_reason is None
    assert tts.calls == 0
    assert playback_called is False


def test_tts_degraded_flag_set_when_tts_skipped():
    result = _engine(tts=FakeTTS(available=False)).run_voice_turn(np.zeros(1600, dtype=np.float32), 16000)

    assert result.final_state == ConversationState.IDLE
    assert result.response_text == "ready"
    assert result.tts_degraded is True
    assert result.tts_degraded_reason == "TTS runtime is unavailable"


def test_sanitize_called_before_tts_synthesize(monkeypatch: pytest.MonkeyPatch):
    tts = FakeTTS(available=True)
    llm = FakeLLM(response="**ready** `now`\x01")
    monkeypatch.setattr("backend.app.conversation.engine.playback.play", lambda audio, sample_rate: None)

    result = _engine(tts=tts, llm=llm).run_voice_turn(np.zeros(1600, dtype=np.float32), 16000)

    assert result.final_state == ConversationState.IDLE
    assert result.response_text == "ready now"
    assert tts.synthesized_texts == ["ready now"]


@pytest.mark.parametrize("failure_kind", ["synthesize", "sample_rate", "playback"])
def test_tts_or_playback_error_closes_to_failed(monkeypatch: pytest.MonkeyPatch, failure_kind: str):
    class SampleRateErrorTTS(FakeTTS):
        def sample_rate(self) -> int:
            raise RuntimeError("sample rate failed")

    tts: FakeTTS
    if failure_kind == "synthesize":
        tts = FakeTTS(available=True, error=RuntimeError("tts failed"))
        monkeypatch.setattr("backend.app.conversation.engine.playback.play", lambda audio, sample_rate: None)
        expected = "tts failed"
    elif failure_kind == "sample_rate":
        tts = SampleRateErrorTTS(available=True)
        monkeypatch.setattr("backend.app.conversation.engine.playback.play", lambda audio, sample_rate: None)
        expected = "sample rate failed"
    else:
        tts = FakeTTS(available=True)

        def fail_play(audio: np.ndarray, sample_rate: int) -> None:
            raise RuntimeError("playback failed")

        monkeypatch.setattr("backend.app.conversation.engine.playback.play", fail_play)
        expected = "playback failed"

    result = _engine(tts=tts).run_voice_turn(np.zeros(1600, dtype=np.float32), 16000)

    assert result.final_state == ConversationState.FAILED
    assert result.failure_reason == expected