from __future__ import annotations

from pathlib import Path
import wave

import numpy as np
import pytest

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.states import ConversationState
from backend.app.personality.loader import load_default_personality
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


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.stt
@pytest.mark.requires_ollama
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_OLLAMA, reason="OLLAMA_BASE_URL not set")
def test_voice_turn_transcribes_fixture_and_returns_response():
    engine = TurnEngine(
        stt=OnnxWhisperRuntime(device="cpu"),
        tts=NullTTSRuntime(reason="not used in C.1"),
        llm=OllamaLLM(base_url=ollama_base_url()),
        personality=load_default_personality(),
    )
    audio, sample_rate = _load_mono_pcm16_wav(FIXTURE_PATH)

    result = engine.run_voice_turn(audio, sample_rate)

    assert result.final_state == ConversationState.IDLE
    assert result.transcript is not None
    assert "hello" in result.transcript.lower()
    assert result.response_text is not None
    assert result.response_text.strip()
    assert result.failure_reason is None