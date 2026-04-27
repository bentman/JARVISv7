from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.memory.write_policy import WritePolicy
from backend.app.personality.schema import PersonalityProfile
from backend.app.runtimes.llm.base import LLMBase
from backend.app.runtimes.stt.barge_in import BargeInDetector
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.tts.base import TTSBase
from backend.tests.conftest import SKIP_UNLESS_LIVE


class FakeSTT(STTBase):
    def __init__(self) -> None:
        super().__init__(device="cpu", model_path=Path("unused"))

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        return "interrupt test"

    def is_available(self) -> bool:
        return True


class FakeTTS(TTSBase):
    def __init__(self) -> None:
        super().__init__(device="cpu", model_path=Path("unused"))

    def synthesize(self, text: str) -> np.ndarray:
        return np.full(8, 0.1, dtype=np.float32)

    def sample_rate(self) -> int:
        return 24000

    def is_available(self) -> bool:
        return True


class FakeLLM(LLMBase):
    def generate(self, prompt: str, **kwargs: object) -> str:
        return "ready"

    def is_available(self) -> bool:
        return True

    def runtime_name(self) -> str:
        return "fake"


class FakePlayback:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self, audio: np.ndarray, sample_rate: int) -> None:
        self.started = True

    def play(self, audio: np.ndarray, sample_rate: int) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


def _personality() -> PersonalityProfile:
    return PersonalityProfile(
        profile_id="runtime-interruption",
        display_name="JARVIS",
        tone="professional",
        brevity="concise",
        formality="semi-formal",
    )


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.tts
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_interruption_during_speaking_produces_clean_state_transition_and_artifact(tmp_path: Path):
    manager = SessionManager(session_id="interruption-live", turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")
    detector = BargeInDetector(energy_threshold=0.02, guard_time_s=0.0, time_source=lambda: 1.0)
    playback = FakePlayback()
    engine = TurnEngine(
        stt=FakeSTT(),
        tts=FakeTTS(),
        llm=FakeLLM(),
        personality=_personality(),
        session_manager=manager,
        write_policy=WritePolicy(),
        barge_in_detector=detector,
        interruption_audio_chunks=[np.full(8, 0.1, dtype=np.float32)],
        playback_api=playback,
    )

    result = engine.run_voice_turn(np.zeros(8, dtype=np.float32), 16000)

    assert playback.started is True
    assert playback.stopped is True
    assert result.final_state == ConversationState.IDLE
    assert result.interrupted is True
    assert result.interruption_events[0]["type"] == "barge_in"
    assert manager.turn_artifacts[0].interruption_events == result.interruption_events