from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.states import ConversationState
from backend.app.personality.loader import load_default_personality
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.tts.tts_runtime import NullTTSRuntime
from backend.tests.conftest import SKIP_UNLESS_LIVE, SKIP_UNLESS_OLLAMA, ollama_base_url


class UnusedSTT(STTBase):
    def __init__(self) -> None:
        super().__init__(device="cpu", model_path=Path("unused"))

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        raise AssertionError("text turn must not call STT")

    def is_available(self) -> bool:
        return False


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.requires_ollama
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_OLLAMA, reason="OLLAMA_BASE_URL not set")
def test_text_turn_returns_string_response_to_known_prompt():
    engine = TurnEngine(
        stt=UnusedSTT(),
        tts=NullTTSRuntime(reason="not used in C.1"),
        llm=OllamaLLM(base_url=ollama_base_url()),
        personality=load_default_personality(),
    )

    result = engine.run_text_turn("Reply with exactly: ready")

    assert result.final_state == ConversationState.IDLE
    assert result.response_text is not None
    assert result.response_text.strip()
    assert result.failure_reason is None