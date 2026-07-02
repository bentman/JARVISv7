from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pytest

from backend.app.cache.manager import CacheManager
from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.memory.write_policy import WritePolicy
from backend.app.personality.schema import PersonalityProfile
from backend.app.runtimes.llm.base import LLMBase
from backend.app.runtimes.stt.barge_in import BargeInDetector
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.tts import playback as tts_playback
from backend.app.runtimes.tts.base import TTSBase
from backend.app.runtimes.vad import EnergyVADRuntime
from backend.app.services.audio_stream import ResidentAudioStream
from backend.app.services.resident_voice_invocation import ResidentVoiceInvocationService, resident_interruption_chunks
from backend.app.services.utterance_segmenter import UtteranceSegmenter
from backend.tests.conftest import SKIP_UNLESS_LIVE
from backend.tests.unit.services.test_session_service import _service


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


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_live_resident_barge_in_stops_playback_and_queues_follow_up(tmp_path, capsys) -> None:
    service = _service(tmp_path)
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=1280)
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.02),
        sample_rate=16000,
        pre_roll_s=0.25,
        min_speech_s=0.2,
        silence_end_s=0.5,
        no_speech_timeout_s=6.0,
        max_duration_s=8.0,
    )
    playback = _AudiblePlayback()
    detector = _DiagnosticBargeInDetector(
        vad=EnergyVADRuntime(speech_rms_threshold=0.015),
        guard_time_s=0.75,
        min_speech_s=0.08,
    )
    stt = _SequencedSTT(["initial operator request", "barge-in follow-up"])
    provider = _EngineProvider(stt=stt, playback=playback, stream=stream, detector=detector)
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=provider,
        audio_capture=lambda: (_ for _ in ()).throw(AssertionError("fallback capture should not run")),
        resident_stream=stream,
        utterance_segmenter=segmenter,
    )

    stream.start()
    try:
        resident.enqueue("ptt", np.ones(1600, dtype=np.float32), 16000)
        _wait_for(playback.started.is_set, timeout_s=5.0, reason="assistant playback did not start")
        _operator_prompt(
            capsys,
            "Barge-in interruption validation",
            [
                "Audible assistant playback is active through the default output device.",
                "After the countdown, speak over the playback with a short interruption.",
                "Keep speaking until the next prompt appears.",
            ],
            before_speak=lambda: not playback.stopped.is_set(),
        )
        _wait_for(
            playback.stopped.is_set,
            timeout_s=10.0,
            reason=lambda: (
                "barge-in did not stop playback; "
                f"chunks={detector.chunk_count} speech_chunks={detector.speech_chunk_count} "
                f"max_rms={detector.max_rms:.5f}"
            ),
        )
        _operator_prompt(
            capsys,
            "Barge-in follow-up validation",
            [
                "The interrupted turn stopped.",
                "After the countdown, speak the follow-up request clearly.",
            ],
        )
        _wait_for(
            lambda: service.status().invocation_source == "barge_in",
            timeout_s=12.0,
            reason="barge-in follow-up was not queued",
        )
    finally:
        stream.stop()

    status = service.status()
    assert playback.stopped.is_set()
    assert provider.calls == 2
    assert stt.transcripts_used == ["initial operator request", "barge-in follow-up"]
    assert status.state == "IDLE"
    assert status.invocation_source == "barge_in"
    assert status.last_transcript == "barge-in follow-up"
    assert status.failure_reason is None


class _SequencedSTT:
    device = "cpu"
    model_path = Path("models/stt/live-barge-in-test")

    def __init__(self, transcripts: list[str]) -> None:
        self._transcripts = list(transcripts)
        self.transcripts_used: list[str] = []

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        assert sample_rate == 16000
        assert audio.size > 0
        transcript = self._transcripts.pop(0) if self._transcripts else "barge-in follow-up"
        self.transcripts_used.append(transcript)
        return transcript

    def is_available(self) -> bool:
        return True


class _FakeLLM:
    def runtime_name(self) -> str:
        return "live-barge-in-test"

    def is_available(self) -> bool:
        return True

    def generate_envelope(self, envelope, **kwargs: object) -> str:
        _ = envelope, kwargs
        return "This is a long assistant response for live barge-in validation."


class _ToneTTS:
    device = "cpu"
    model_path = Path("models/tts/live-barge-in-test")

    def __init__(self, *, available: bool) -> None:
        self._available = available

    def synthesize(self, text: str) -> np.ndarray:
        _ = text
        duration_s = 12.0
        sample_rate = self.sample_rate()
        samples = np.arange(int(sample_rate * duration_s), dtype=np.float32)
        tone = np.sin(2.0 * np.pi * 440.0 * samples / float(sample_rate))
        return (0.08 * tone).astype(np.float32)

    def sample_rate(self) -> int:
        return 16000

    def is_available(self) -> bool:
        return self._available


class _AudiblePlayback:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.stopped = threading.Event()
        self._ends_at = 0.0

    def start(self, audio: np.ndarray, sample_rate: int) -> None:
        assert audio.size > 0
        assert sample_rate == 16000
        self._ends_at = time.monotonic() + (float(audio.size) / float(sample_rate))
        tts_playback.start(audio, sample_rate)
        self.started.set()

    def stop(self) -> None:
        tts_playback.stop()
        self.stopped.set()

    def is_playing(self) -> bool:
        return self.started.is_set() and not self.stopped.is_set() and time.monotonic() < self._ends_at

    def play(self, audio: np.ndarray, sample_rate: int) -> None:
        tts_playback.play(audio, sample_rate)

    def last_output_device(self) -> str:
        return tts_playback.last_output_device() or "live-barge-in-test playback"


class _DiagnosticBargeInDetector(BargeInDetector):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.chunk_count = 0
        self.speech_chunk_count = 0
        self.max_rms = 0.0

    def detect(self, audio_chunk: np.ndarray) -> bool:
        samples = np.asarray(audio_chunk, dtype=np.float32).reshape(-1)
        self.chunk_count += 1
        if samples.size:
            rms = float(np.sqrt(np.mean(np.square(samples))))
            self.max_rms = max(self.max_rms, rms)
        detected = super().detect(samples)
        if self._speech_samples > 0:
            self.speech_chunk_count += 1
        return detected


class _EngineProvider:
    def __init__(
        self,
        *,
        stt: _SequencedSTT,
        playback: _AudiblePlayback,
        stream: ResidentAudioStream,
        detector: _DiagnosticBargeInDetector,
    ) -> None:
        self._stt = stt
        self._playback = playback
        self._stream = stream
        self._detector = detector
        self.calls = 0

    def __call__(self) -> TurnEngine:
        self.calls += 1
        return TurnEngine(
            stt=self._stt,  # type: ignore[arg-type]
            tts=_ToneTTS(available=self.calls == 1),  # type: ignore[arg-type]
            llm=_FakeLLM(),  # type: ignore[arg-type]
            personality=_personality(),
            cache_manager=CacheManager(),
            barge_in_detector=self._detector if self.calls == 1 else None,
            interruption_audio_chunks=resident_interruption_chunks(self._stream) if self.calls == 1 else None,
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


def _operator_prompt(capsys, title: str, lines: list[str], before_speak=None) -> None:
    with capsys.disabled():
        print(f"\n[operator] {title}", flush=True)
        for line in lines:
            print(f"[operator] {line}", flush=True)
        for remaining in (3, 2, 1):
            print(f"[operator] capture begins in {remaining}...", flush=True)
            time.sleep(1.0)
        if before_speak is not None and not before_speak():
            raise AssertionError("playback stopped before operator speech prompt")
        print("[operator] SPEAK NOW.", flush=True)


def _wait_for(predicate, *, timeout_s: float, reason) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    message = reason() if callable(reason) else reason
    raise AssertionError(message)
