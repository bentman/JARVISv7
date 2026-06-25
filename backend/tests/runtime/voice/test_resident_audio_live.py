from __future__ import annotations

import os

import pytest

from backend.app.runtimes.vad import EnergyVADRuntime
from backend.app.runtimes.wake.openwakeword_runtime import OpenWakeWordRuntime
from backend.app.services.audio_stream import ResidentAudioStream
from backend.app.services.session_service import SessionService
from backend.app.services.utterance_segmenter import UtteranceSegmenter
from backend.app.services.wake_monitor import WakeMonitorService
from backend.tests.conftest import SKIP_UNLESS_LIVE
from backend.tests.unit.services.test_session_service import _service


SKIP_UNLESS_RESIDENT_AUDIO_OPERATOR = not os.getenv("JARVISV7_RESIDENT_AUDIO_LIVE")


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(
    SKIP_UNLESS_RESIDENT_AUDIO_OPERATOR,
    reason="resident live microphone/operator gate JARVISV7_RESIDENT_AUDIO_LIVE not set",
)
def test_resident_audio_stream_captures_operator_utterance() -> None:
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=1280)
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.02),
        sample_rate=16000,
        pre_roll_s=0.25,
        min_speech_s=0.2,
        silence_end_s=0.5,
        no_speech_timeout_s=5.0,
        max_duration_s=8.0,
    )
    stream.start()
    subscriber = stream.subscribe()
    try:
        result = segmenter.capture(_subscriber_chunks(subscriber))
    finally:
        stream.unsubscribe(subscriber)
        stream.stop()

    assert result.speech_started, result.reason
    assert result.audio.size > 0


@pytest.mark.live
@pytest.mark.wake
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(
    SKIP_UNLESS_RESIDENT_AUDIO_OPERATOR,
    reason="resident live microphone/operator gate JARVISV7_RESIDENT_AUDIO_LIVE not set",
)
def test_wake_monitor_uses_resident_stream_for_operator_command(tmp_path) -> None:
    service: SessionService = _service(tmp_path)
    invocations: list[tuple[str, object, int | None]] = []
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=1280)
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.02),
        sample_rate=16000,
        pre_roll_s=0.25,
        min_speech_s=0.2,
        silence_end_s=0.5,
        no_speech_timeout_s=5.0,
        max_duration_s=8.0,
    )
    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: OpenWakeWordRuntime(),
        invocation_callback=lambda source, audio, sample_rate: invocations.append((source, audio, sample_rate)),
        resident_stream=stream,
        utterance_segmenter=segmenter,
    )

    stream.start()
    try:
        status = monitor.start()
        assert status.available, status.reason
        _wait_for(lambda: len(invocations) == 1, timeout_s=15.0)
    finally:
        monitor.stop()
        stream.stop()

    source, audio, sample_rate = invocations[0]
    assert source == "wake"
    assert sample_rate == 16000
    assert getattr(audio, "size", 0) > 0


def _subscriber_chunks(subscriber):
    while True:
        yield subscriber.get(timeout=0.5)


def _wait_for(predicate, timeout_s: float) -> None:
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition was not reached")
