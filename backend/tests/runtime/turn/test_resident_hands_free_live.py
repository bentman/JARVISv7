from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pytest

from backend.app.cache.manager import CacheManager
from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.states import ConversationState
from backend.app.personality.schema import PersonalityProfile
from backend.app.runtimes.tts import playback as tts_playback
from backend.app.runtimes.vad import EnergyVADRuntime
from backend.app.services.audio_stream import ResidentAudioStream
from backend.app.services.resident_voice_invocation import ResidentVoiceInvocationService
from backend.app.services.utterance_segmenter import UtteranceSegmenter
from backend.tests.conftest import SKIP_UNLESS_LIVE
from backend.tests.unit.services.test_session_service import _service


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
    provider = _EngineProvider(stt=stt, playback=playback)
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


class _EngineProvider:
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
