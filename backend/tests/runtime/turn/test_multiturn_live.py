from __future__ import annotations

from pathlib import Path
import wave

import numpy as np
import pytest

from backend.app.artifacts.storage import read_turn_artifact
from backend.app.conversation.engine import TurnEngine, TurnResult
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.memory.write_policy import WritePolicy
from backend.app.personality.schema import PersonalityProfile
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.runtimes.stt.onnx_whisper_runtime import OnnxWhisperRuntime
from backend.app.runtimes.tts.tts_runtime import NullTTSRuntime
from backend.tests.conftest import SKIP_UNLESS_LIVE, SKIP_UNLESS_OLLAMA, ollama_base_url


FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "hello_world.wav"


def _load_mono_pcm16_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        raw_audio = wav_file.readframes(wav_file.getnframes())
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
    if channels != 1 or sample_width != 2:
        raise ValueError("expected mono 16-bit PCM WAV fixture")
    return np.frombuffer(raw_audio, dtype="<i2").astype(np.float32) / 32768.0, sample_rate


def _engine(tmp_path: Path) -> tuple[TurnEngine, SessionManager]:
    session_manager = SessionManager(
        session_id="runtime-multiturn-session",
        turns_base_dir=tmp_path / "turns",
        sessions_base_dir=tmp_path / "sessions",
    )
    engine = TurnEngine(
        stt=OnnxWhisperRuntime(device="cpu"),
        tts=NullTTSRuntime(reason="C.4 continuity test uses explicit TTS degradation"),
        llm=OllamaLLM(base_url=ollama_base_url()),
        personality=PersonalityProfile(
            profile_id="runtime-c4",
            display_name="JARVIS",
            tone="professional",
            brevity="concise",
            formality="semi-formal",
            system_prompt_addendum="For every user message in this validation test, reply with exactly: ready",
        ),
        session_manager=session_manager,
        write_policy=WritePolicy(max_working_memory_entries=10),
    )
    return engine, session_manager


def _run_two_spoken_turns(tmp_path: Path) -> tuple[TurnResult, TurnResult, SessionManager]:
    engine, session_manager = _engine(tmp_path)
    audio, sample_rate = _load_mono_pcm16_wav(FIXTURE_PATH)

    first = engine.run_voice_turn(audio, sample_rate)
    second = engine.run_voice_turn(audio, sample_rate)

    return first, second, session_manager


def _assert_completed_degraded_voice_turn(result: TurnResult) -> None:
    assert result.final_state == ConversationState.IDLE
    assert result.failure_reason is None
    assert result.transcript is not None
    assert "hello" in result.transcript.lower()
    assert result.response_text is not None
    assert result.response_text.strip()
    assert result.tts_degraded is True
    assert result.tts_degraded_reason == "TTS runtime is unavailable"


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.stt
@pytest.mark.tts
@pytest.mark.requires_ollama
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_OLLAMA, reason="OLLAMA_BASE_URL not set")
def test_two_spoken_turns_in_one_session_write_artifacts_and_inject_memory(tmp_path: Path):
    first, second, session_manager = _run_two_spoken_turns(tmp_path)

    _assert_completed_degraded_voice_turn(first)
    _assert_completed_degraded_voice_turn(second)
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