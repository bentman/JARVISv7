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
from backend.tests.conftest import SKIP_UNLESS_LIVE


class UnusedSTT(STTBase):
    def __init__(self) -> None:
        super().__init__(device="cpu", model_path=Path("unused"))

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        raise AssertionError("text turn must not call STT")

    def is_available(self) -> bool:
        return False


def _live_llama_cpp_runtime(live_llama_cpp_sidecar) -> LlamaCppLLM:
    resolution = live_llama_cpp_sidecar.resolution
    runtime = LlamaCppLLM(
        base_url=resolution.base_url,
        model=resolution.model_id,
        sidecar_status=live_llama_cpp_sidecar.service.status,
        generation_defaults={"max_tokens": 24, "temperature": 0},
        managed=True,
        route=resolution.route,
        serve_profile_id=resolution.serve_profile_id,
        accelerator=resolution.accelerator,
        selected_reason=resolution.selected_reason,
    )
    assert runtime.is_available(), runtime.reason
    return runtime


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.llm
@pytest.mark.requires_llama_cpp
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_text_turn_returns_string_response_via_llama_cpp(live_llama_cpp_sidecar):
    engine = TurnEngine(
        stt=UnusedSTT(),
        tts=NullTTSRuntime(reason="not used by text turn"),
        llm=_live_llama_cpp_runtime(live_llama_cpp_sidecar),
        personality=load_default_personality(),
    )

    result = engine.run_text_turn("Reply with exactly: ready")

    assert result.final_state == ConversationState.IDLE
    assert result.response_text is not None
    assert result.response_text.strip()
    assert result.failure_reason is None
