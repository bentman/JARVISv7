from __future__ import annotations

import time

import pytest
from backend.app.runtimes.vad import EnergyVADRuntime
from backend.app.runtimes.wake.openwakeword_runtime import OpenWakeWordRuntime
from backend.app.services.audio_stream import ResidentAudioStream
from backend.app.services.session_service import SessionService
from backend.app.services.utterance_segmenter import UtteranceSegmenter
from backend.app.services.wake_monitor import WakeMonitorService
from backend.tests.conftest import SKIP_UNLESS_LIVE
from backend.tests.unit.services.test_session_service import _service


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_resident_audio_stream_captures_operator_utterance(capsys) -> None:
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
        _operator_prompt(
            capsys,
            "Resident audio stream validation",
            [
                "Capture starts after the countdown.",
                "Say a short phrase clearly, for example: 'resident stream validation'.",
            ],
        )
        result = segmenter.capture(_subscriber_chunks(subscriber))
    finally:
        stream.unsubscribe(subscriber)
        stream.stop()

    assert result.speech_started, result.reason
    assert result.audio.size > 0


@pytest.mark.live
@pytest.mark.wake
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_wake_monitor_uses_resident_stream_for_operator_command(tmp_path, capsys) -> None:
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
        _operator_notice(
            capsys,
            "Wake shared-stream validation",
            [
                "Wake monitor is active for up to 15 seconds.",
                "Say the configured wake word, then a short command.",
            ],
        )
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


def _operator_prompt(capsys, title: str, lines: list[str]) -> None:
    _operator_notice(capsys, title, lines)
    with capsys.disabled():
        for remaining in (3, 2, 1):
            print(f"[operator] capture begins in {remaining}...", flush=True)
            time.sleep(1.0)
        print("[operator] SPEAK NOW.", flush=True)


def _operator_notice(capsys, title: str, lines: list[str]) -> None:
    with capsys.disabled():
        print(f"\n[operator] {title}", flush=True)
        for line in lines:
            print(f"[operator] {line}", flush=True)


def _wait_for(predicate, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition was not reached")
