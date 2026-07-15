from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import wave

import numpy as np
import pytest

from backend.app.artifacts.storage import read_turn_artifact
from backend.app.conversation.engine import TurnEngine, TurnResult
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.memory.episodic import EpisodicMemory
from backend.app.memory.retrieval import RetrievedFact
from backend.app.memory.write_policy import WritePolicy
from backend.app.personality.loader import load_default_personality
from backend.app.personality.schema import PersonalityProfile
from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.stt.onnx_whisper_runtime import OnnxWhisperRuntime
from backend.app.runtimes.tts.tts_runtime import NullTTSRuntime
from backend.tests.conftest import (
    LLAMA_CPP_READY_PROMPT,
    SKIP_UNLESS_LIVE,
    SKIP_UNLESS_OLLAMA,
    assert_llama_cpp_ready_contract,
    ollama_base_url,
)


FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "hello_world.wav"


class UnusedSTT(STTBase):
    def __init__(self) -> None:
        super().__init__(device="cpu", model_path=Path("unused"))

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        raise AssertionError("text turn must not call STT")

    def is_available(self) -> bool:
        return False


@dataclass(frozen=True)
class RetrievalCase:
    name: str


def _load_mono_pcm16_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        raw_audio = wav_file.readframes(wav_file.getnframes())
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
    if channels != 1 or sample_width != 2:
        raise ValueError("expected mono 16-bit PCM WAV fixture")
    return np.frombuffer(raw_audio, dtype="<i2").astype(np.float32) / 32768.0, sample_rate


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


def _engine(tmp_path: Path, preflight, profile) -> tuple[TurnEngine, SessionManager]:
    session_manager = SessionManager(
        session_id="runtime-multiturn-session",
        turns_base_dir=tmp_path / "turns",
        sessions_base_dir=tmp_path / "sessions",
    )
    from backend.app.runtimes.stt.stt_runtime import select_stt_runtime
    from backend.app.personality.schema import (
        PersonalityExample,
        PersonalityProfile,
        PersonalityStyle,
        PersonalityTraits,
    )
    stt = select_stt_runtime(preflight, profile)
    engine = TurnEngine(
        stt=stt,
        tts=NullTTSRuntime(reason="C.4 continuity test uses explicit TTS degradation"),
        llm=OllamaLLM(base_url=ollama_base_url()),
        personality=PersonalityProfile(
            profile_id="runtime-c4",
            display_name="JARVIS",
            description="Balanced assistant.",
            locale="en",
            system="For every user message in this validation test, reply with exactly: ready",
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
        ),
        session_manager=session_manager,
        write_policy=WritePolicy(max_working_memory_entries=10),
    )
    return engine, session_manager


def _run_two_spoken_turns(
    tmp_path: Path, preflight, profile
) -> tuple[TurnResult, TurnResult, SessionManager]:
    engine, session_manager = _engine(tmp_path, preflight, profile)
    audio, sample_rate = _load_mono_pcm16_wav(FIXTURE_PATH)
    first = engine.run_voice_turn(audio, sample_rate)

    second_audio_path = FIXTURE_PATH.parent / "hey_jarvis.wav"
    second_audio, second_sample_rate = _load_mono_pcm16_wav(second_audio_path)
    second = engine.run_voice_turn(second_audio, second_sample_rate)

    return first, second, session_manager


def _assert_completed_degraded_voice_turn(result: TurnResult, expected_substring: str = "hello") -> None:
    assert result.final_state == ConversationState.IDLE
    assert result.failure_reason is None
    assert result.transcript is not None
    assert expected_substring in result.transcript.lower()
    assert result.response_text is not None
    assert result.response_text.strip()
    assert result.tts_degraded is True
    assert result.tts_degraded_reason == "TTS runtime is unavailable"


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


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.stt
@pytest.mark.tts
@pytest.mark.requires_ollama
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_OLLAMA, reason="OLLAMA_BASE_URL not set")
def test_two_spoken_turns_in_one_session_write_artifacts_and_inject_memory(
    preflight_fixture, profiler_fixture, tmp_path: Path
):
    first, second, session_manager = _run_two_spoken_turns(tmp_path, preflight_fixture, profiler_fixture.profile)

    _assert_completed_degraded_voice_turn(first, "hello")
    _assert_completed_degraded_voice_turn(second, "jarvis")
    assert len(session_manager.turn_artifacts) == 2
    assert (tmp_path / "turns" / session_manager.session_id / f"{first.turn_id}.json").exists()
    assert (tmp_path / "turns" / session_manager.session_id / f"{second.turn_id}.json").exists()
    assert not (Path("data") / "turns" / session_manager.session_id).exists()
    second_artifact = read_turn_artifact(session_manager.session_id, second.turn_id, tmp_path / "turns")
    assert second_artifact is not None
    assert second_artifact.final_prompt_text is not None
    assert "Working memory:" in second_artifact.final_prompt_text
    assert first.response_text is not None
    assert f"- {first.response_text}" in second_artifact.final_prompt_text


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(RetrievalCase("episodic-write"), marks=pytest.mark.requires_ollama, id="episodic-write"),
        pytest.param(RetrievalCase("retrieve-recent"), id="retrieve-recent"),
        pytest.param(
            RetrievalCase("retrieved-memory-refs"),
            marks=[pytest.mark.g2_required, pytest.mark.requires_ollama],
            id="retrieved-memory-refs",
        ),
    ],
)
@pytest.mark.live
@pytest.mark.turn
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_retrieval_memory_paths(case: RetrievalCase, tmp_path: Path) -> None:
    if case.name == "episodic-write":
        if SKIP_UNLESS_OLLAMA:
            pytest.skip("OLLAMA_BASE_URL not set")
        manager = SessionManager(session_id="retrieval-live-1", turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")
        episodic = EpisodicMemory(base_dir=tmp_path / "episodic", sessions_base_dir=tmp_path / "sessions")
        engine = TurnEngine(
            stt=UnusedSTT(),
            tts=NullTTSRuntime(reason="not used"),
            llm=OllamaLLM(base_url=ollama_base_url()),
            personality=load_default_personality(),
            session_manager=manager,
            episodic=episodic,
        )
        result = engine.run_text_turn("Reply with exactly: episodic proof")
        assert result.failure_reason is None
        assert (tmp_path / "episodic" / "retrieval-live-1" / f"{result.turn_id}.json").exists()
        return

    if case.name == "retrieve-recent":
        episodic = EpisodicMemory(base_dir=tmp_path / "episodic", sessions_base_dir=tmp_path / "sessions")
        session_dir = tmp_path / "episodic" / "prior-session"
        session_dir.mkdir(parents=True)
        (session_dir / "prior-turn.json").write_text(
            """{
  \"turn_id\": \"prior-turn\",
  \"session_id\": \"prior-session\",
  \"session_started_at\": \"2026-01-01T00:00:00+00:00\",
  \"transcript\": \"prior transcript\",
  \"response_text\": \"prior response\",
  \"tools_invoked\": [],
  \"written_at\": \"2026-01-01T00:00:00+00:00\"
}
""",
            encoding="utf-8",
        )
        out = episodic.retrieve_recent(n=1)
        assert len(out) == 1
        assert out[0].turn_id == "prior-turn"
        return

    if SKIP_UNLESS_OLLAMA:
        pytest.skip("OLLAMA_BASE_URL not set")
    manager = SessionManager(session_id="retrieval-live-2", turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")
    episodic = EpisodicMemory(base_dir=tmp_path / "episodic", sessions_base_dir=tmp_path / "sessions")
    prior_session_dir = tmp_path / "episodic" / "prior-session"
    prior_session_dir.mkdir(parents=True)
    (prior_session_dir / "prior-turn.json").write_text(
        """{
  \"turn_id\": \"prior-turn\",
  \"session_id\": \"prior-session\",
  \"session_started_at\": \"2026-01-01T00:00:00+00:00\",
  \"transcript\": \"remember this reference\",
  \"response_text\": \"remember this reference response\",
  \"tools_invoked\": [],
  \"written_at\": \"2026-01-01T00:00:00+00:00\"
}
""",
        encoding="utf-8",
    )

    engine = TurnEngine(
        stt=UnusedSTT(),
        tts=NullTTSRuntime(reason="not used"),
        llm=OllamaLLM(base_url=ollama_base_url()),
        personality=load_default_personality(),
        session_manager=manager,
        episodic=episodic,
    )

    engine.retrieval.retrieve = lambda query, n=3, **kwargs: [
        RetrievedFact(
            turn_id="prior-turn",
            session_id="prior-session",
            content="remember this reference response",
            source_field="response_text",
            relevance_method="keyword",
        )
    ]

    result = engine.run_text_turn("Please use remembered reference")
    assert result.failure_reason is None
    artifact = manager.turn_artifacts[-1]
    assert artifact.retrieved_memory_refs == ["prior-turn"]
    assert artifact.final_prompt_text is not None
    assert "Relevant prior context:" in artifact.final_prompt_text
    assert "[prior-se/prior-tu] remember this reference response" in artifact.final_prompt_text
