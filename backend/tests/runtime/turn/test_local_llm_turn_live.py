from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.personality.loader import load_default_personality
from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.tts.tts_runtime import NullTTSRuntime
from backend.tests.conftest import LLAMA_CPP_READY_PROMPT, SKIP_UNLESS_LIVE, assert_llama_cpp_ready_contract


class UnusedSTT(STTBase):
    def __init__(self) -> None:
        super().__init__(device="cpu", model_path=Path("unused"))

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        raise AssertionError("text turn must not call STT")

    def is_available(self) -> bool:
        return False


def _live_llama_cpp_runtime(live_llama_cpp_sidecar) -> LlamaCppLLM:
    resolution = live_llama_cpp_sidecar.resolution
    generation_defaults = {
        **resolution.generation_defaults,
        "max_tokens": 24,
        "temperature": 0,
    }
    runtime = LlamaCppLLM(
        base_url=resolution.base_url,
        model=resolution.model_id,
        sidecar_status=live_llama_cpp_sidecar.service.status,
        generation_defaults=generation_defaults,
        managed=True,
        route=resolution.route,
        serve_profile_id=resolution.serve_profile_id,
        accelerator=resolution.accelerator,
        selected_reason=resolution.selected_reason,
        model_mode=resolution.model_mode,
        model_policy=resolution.model_policy,
        model_role=resolution.model_role,
        model_selection_reason=resolution.model_selection_reason,
    )
    assert runtime.is_available(), runtime.reason
    return runtime


def _text_engine(llm: LlamaCppLLM, *, session_manager: SessionManager | None = None) -> TurnEngine:
    return TurnEngine(
        stt=UnusedSTT(),
        tts=NullTTSRuntime(reason="not used by text turn"),
        llm=llm,
        personality=load_default_personality(),
        session_manager=session_manager,
    )


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.llm
@pytest.mark.requires_llama_cpp
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_text_turn_returns_deterministic_response_via_llama_cpp(live_llama_cpp_sidecar):
    runtime = _live_llama_cpp_runtime(live_llama_cpp_sidecar)
    engine = _text_engine(runtime)

    result = engine.run_text_turn(LLAMA_CPP_READY_PROMPT)

    assert result.final_state == ConversationState.IDLE
    assert result.response_text is not None
    assert result.failure_reason is None
    assert runtime.model == live_llama_cpp_sidecar.resolution.model_id
    assert runtime.serve_profile_id == live_llama_cpp_sidecar.resolution.serve_profile_id
    assert runtime.accelerator == live_llama_cpp_sidecar.resolution.accelerator
    if runtime.model_mode == "prod":
        assert runtime.model != "assistant-small-q4"
    assert_llama_cpp_ready_contract(result.response_text, runtime=runtime)


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.llm
@pytest.mark.requires_llama_cpp
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_text_turn_latest_request_beats_prior_turn_with_continuity(live_llama_cpp_sidecar, tmp_path: Path):
    runtime = _live_llama_cpp_runtime(live_llama_cpp_sidecar)
    manager = SessionManager(
        session_id="live-llama-cpp-stale-guard",
        turns_base_dir=tmp_path / "turns",
        sessions_base_dir=tmp_path / "sessions",
    )
    engine = _text_engine(runtime, session_manager=manager)

    first = engine.run_text_turn("Answer with exactly one word: blue")
    second = engine.run_text_turn(LLAMA_CPP_READY_PROMPT)

    assert first.final_state == ConversationState.IDLE
    assert first.failure_reason is None
    assert second.final_state == ConversationState.IDLE
    assert second.response_text is not None
    assert second.failure_reason is None
    assert_llama_cpp_ready_contract(second.response_text, runtime=runtime)
