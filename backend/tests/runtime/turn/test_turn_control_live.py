from __future__ import annotations

import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
from backend.app.cache.manager import CacheManager
from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.states import ConversationState
from backend.app.personality.loader import load_default_personality
from backend.app.personality.schema import PersonalityProfile
from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.stt.onnx_whisper_runtime import OnnxWhisperRuntime
from backend.app.runtimes.tts import playback as tts_playback
from backend.app.runtimes.tts.tts_runtime import NullTTSRuntime
from backend.app.runtimes.vad import EnergyVADRuntime
from backend.app.services.audio_stream import ResidentAudioStream
from backend.app.services.resident_voice_invocation import ResidentVoiceInvocationService
from backend.app.services.utterance_segmenter import UtteranceSegmenter
from backend.tests.conftest import (
    LLAMA_CPP_READY_PROMPT,
    SKIP_UNLESS_LIVE,
    SKIP_UNLESS_OLLAMA,
    assert_llama_cpp_ready_contract,
    ollama_base_url,
)
from backend.tests.unit.services.test_session_service import _service

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "hello_world.wav"


class UnusedSTT(STTBase):
    def __init__(self) -> None:
        super().__init__(device="cpu", model_path=Path("unused"))

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        raise AssertionError("text turn must not call STT")

    def is_available(self) -> bool:
        return False


@dataclass(frozen=True)
class OllamaTurnCase:
    mode: str


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


def _text_engine(llm: LlamaCppLLM) -> TurnEngine:
    return TurnEngine(
        stt=UnusedSTT(),
        tts=NullTTSRuntime(reason="not used by text turn"),
        llm=llm,
        personality=load_default_personality(),
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(OllamaTurnCase(mode="text"), id="text"),
        pytest.param(OllamaTurnCase(mode="voice"), marks=pytest.mark.stt, id="voice"),
    ],
)
@pytest.mark.live
@pytest.mark.turn
@pytest.mark.requires_ollama
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_OLLAMA, reason="OLLAMA_BASE_URL not set")
def test_ollama_turn_returns_response(case: OllamaTurnCase):
    llm = OllamaLLM(base_url=ollama_base_url())
    if case.mode == "text":
        engine = TurnEngine(
            stt=UnusedSTT(),
            tts=NullTTSRuntime(reason="not used in C.1"),
            llm=llm,
            personality=load_default_personality(),
        )
        result = engine.run_text_turn("Reply with exactly: ready")

        assert result.final_state == ConversationState.IDLE
        assert result.response_text is not None
        assert result.response_text.strip()
        assert result.failure_reason is None
        return

    engine = TurnEngine(
        stt=OnnxWhisperRuntime(device="cpu"),
        tts=NullTTSRuntime(reason="not used in C.1"),
        llm=llm,
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
    assert result.tts_degraded is True
    assert result.tts_degraded_reason == "TTS runtime is unavailable"


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
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_live_resident_hands_free_captures_one_follow_up(tmp_path, capsys) -> None:
    service = _service(tmp_path)
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=1280)
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.02),
        sample_rate=16000,
        pre_roll_s=0.25,
        min_speech_s=0.2,
        silence_end_s=0.5,
        no_speech_timeout_s=8.0,
        max_duration_s=8.0,
    )
    playback = _AudiblePlayback()
    stt = _SequencedSTT(["initial hands-free request", "hands-free follow-up"])
    provider = _HandsFreeEngineProvider(stt=stt, playback=playback)
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=provider,
        audio_capture=lambda: (_ for _ in ()).throw(AssertionError("fallback capture should not run")),
        resident_stream=stream,
        utterance_segmenter=segmenter,
    )
    resident.set_mode("hands-free")

    stream.start()
    try:
        resident.enqueue("ptt", np.ones(1600, dtype=np.float32), 16000)
        _wait_for(playback.started.is_set, timeout_s=5.0, reason="assistant playback did not start")
        _wait_for(
            lambda: resident.follow_up_status().listening,
            timeout_s=8.0,
            reason="hands-free follow-up listening did not start",
        )
        _operator_prompt(
            capsys,
            "Hands-free follow-up validation",
            [
                "Hands-free follow-up listening is active.",
                "After the countdown, speak a short follow-up request clearly.",
            ],
        )
        _wait_for(
            lambda: (
                service.status().invocation_source == "hands_free"
                and service.status().state == "IDLE"
                and service.status().last_transcript == "hands-free follow-up"
            ),
            timeout_s=12.0,
            reason="hands-free follow-up turn did not complete",
        )
    finally:
        stream.stop()

    status = service.status()
    assert provider.calls == 2
    assert stt.transcripts_used == ["initial hands-free request", "hands-free follow-up"]
    assert status.state == "IDLE"
    assert status.invocation_source == "hands_free"
    assert status.last_transcript == "hands-free follow-up"
    assert status.failure_reason is None
    assert resident.follow_up_status().listening is False


class _SequencedSTT:
    device = "cpu"
    model_path = Path("models/stt/live-hands-free-test")

    def __init__(self, transcripts: list[str]) -> None:
        self._transcripts = list(transcripts)
        self.transcripts_used: list[str] = []

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        assert sample_rate == 16000
        assert audio.size > 0
        transcript = self._transcripts.pop(0) if self._transcripts else "hands-free follow-up"
        self.transcripts_used.append(transcript)
        return transcript

    def is_available(self) -> bool:
        return True


class _FakeLLM:
    def runtime_name(self) -> str:
        return "live-hands-free-test"

    def is_available(self) -> bool:
        return True

    def generate_envelope(self, envelope, **kwargs: object) -> str:
        _ = envelope, kwargs
        return "This is a resident hands-free validation response."


class _ToneTTS:
    device = "cpu"
    model_path = Path("models/tts/live-hands-free-test")

    def synthesize(self, text: str) -> np.ndarray:
        _ = text
        duration_s = 1.0
        sample_rate = self.sample_rate()
        samples = np.arange(int(sample_rate * duration_s), dtype=np.float32)
        tone = np.sin(2.0 * np.pi * 440.0 * samples / float(sample_rate))
        return (0.08 * tone).astype(np.float32)

    def sample_rate(self) -> int:
        return 16000

    def is_available(self) -> bool:
        return True


class _AudiblePlayback:
    def __init__(self) -> None:
        self.started = threading.Event()

    def play(self, audio: np.ndarray, sample_rate: int) -> None:
        assert audio.size > 0
        assert sample_rate == 16000
        self.started.set()
        tts_playback.play(audio, sample_rate)

    def last_output_device(self) -> str:
        return tts_playback.last_output_device() or "live-hands-free-test playback"


class _HandsFreeEngineProvider:
    def __init__(self, *, stt: _SequencedSTT, playback: _AudiblePlayback) -> None:
        self._stt = stt
        self._playback = playback
        self.calls = 0

    def __call__(self) -> TurnEngine:
        self.calls += 1
        return TurnEngine(
            stt=self._stt,  # type: ignore[arg-type]
            tts=_ToneTTS(),  # type: ignore[arg-type]
            llm=_FakeLLM(),  # type: ignore[arg-type]
            personality=_personality(),
            cache_manager=CacheManager(),
            playback_api=self._playback,
        )


def _personality() -> PersonalityProfile:
    return PersonalityProfile(
        profile_id="test",
        display_name="JARVIS",
        tone="professional",
        brevity="concise",
        formality="semi-formal",
    )


def _operator_prompt(capsys, title: str, lines: list[str]) -> None:
    with capsys.disabled():
        print(f"\n[operator] {title}", flush=True)
        for line in lines:
            print(f"[operator] {line}", flush=True)
        for remaining in (3, 2, 1):
            print(f"[operator] capture begins in {remaining}...", flush=True)
            time.sleep(1.0)
        print("[operator] SPEAK NOW.", flush=True)


def _wait_for(predicate, *, timeout_s: float, reason: str) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(reason)
