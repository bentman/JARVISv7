from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.states import ConversationState
from backend.app.personality.loader import load_default_personality
from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.tts.tts_runtime import NullTTSRuntime
from backend.tests.conftest import SKIP_UNLESS_LIVE, llama_cpp_base_url, llama_cpp_model_name


class UnusedSTT(STTBase):
    def __init__(self) -> None:
        super().__init__(device="cpu", model_path=Path("unused"))

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        raise AssertionError("text turn must not call STT")

    def is_available(self) -> bool:
        return False


def _live_llama_cpp_runtime() -> LlamaCppLLM:
    runtime = LlamaCppLLM(
        base_url=llama_cpp_base_url(),
        model=llama_cpp_model_name(),
        generation_defaults={"max_tokens": 24, "temperature": 0},
        managed=True,
    )
    if not runtime.is_available():
        pytest.skip(f"requires live llama.cpp sidecar: {runtime.reason}")
    return runtime


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.llm
@pytest.mark.requires_llama_cpp
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_text_turn_returns_string_response_via_llama_cpp():
    engine = TurnEngine(
        stt=UnusedSTT(),
        tts=NullTTSRuntime(reason="not used by text turn"),
        llm=_live_llama_cpp_runtime(),
        personality=load_default_personality(),
    )

    result = engine.run_text_turn("Reply with exactly: ready")

    assert result.final_state == ConversationState.IDLE
    assert result.response_text is not None
    assert result.response_text.strip()
    assert result.failure_reason is None
