from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
from backend.app.conversation.engine import TurnResult
from backend.app.conversation.realtime.events import RealtimeEventType
from backend.app.conversation.states import ConversationState
from backend.app.runtimes.vad import EnergyVADRuntime
from backend.app.services.audio_stream import ResidentAudioStream
from backend.app.services.resident_voice_invocation import (
    RESIDENT_STREAM_STOPPED_PTT_REASON,
    ResidentVoiceInvocationService,
    resident_interruption_chunks,
)
from backend.app.services.utterance_segmenter import UtteranceSegmenter
from backend.tests.unit.services.test_session_service import _service


class _FakeEngine:
    def __init__(self, calls: list[tuple[np.ndarray, int]], result: TurnResult | None = None) -> None:
        self.calls = calls
        self.result = result

    def run_voice_turn(self, audio: np.ndarray, sample_rate: int) -> TurnResult:
        self.calls.append((audio, sample_rate))
        if self.result is not None:
            return self.result
        return TurnResult(
            turn_id="turn-resident",
            session_id="session-resident",
            transcript="resident transcript",
            response_text="resident response",
            final_state=ConversationState.IDLE,
        )


def _wait_for(predicate, timeout_s: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached")


def _blocking_source(stop_event: threading.Event):
    while not stop_event.is_set():
        time.sleep(0.01)
        if False:
            yield np.array([], dtype=np.float32)


def _segmenter() -> UtteranceSegmenter:
    return UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.05),
        sample_rate=16000,
        pre_roll_s=0.00025,
        min_speech_s=0.0005,
        silence_end_s=0.0005,
        no_speech_timeout_s=0.0005,
    )


def test_ptt_invocation_runs_canonical_voice_turn_and_records_status(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    service = _service(tmp_path)
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine(calls),  # type: ignore[return-value]
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
    )

    queued = resident.ptt()
    assert queued.invocation_source in {None, "ptt"}

    _wait_for(lambda: service.status().last_transcript == "resident transcript")
    status = service.status()

    assert len(calls) == 1
    assert calls[0][1] == 16000
    assert status.state == "IDLE"
    assert status.last_transcript == "resident transcript"
    assert status.last_response == "resident response"
    assert status.failure_reason is None
    assert status.invocation_source == "ptt"
    assert status.turn_count == 0
    assert [event.event_type for event in resident.last_realtime_events()] == [
        RealtimeEventType.SESSION_ACTIVE,
        RealtimeEventType.INVOCATION_RECEIVED,
        RealtimeEventType.AUDIO_CAPTURE_STARTED,
        RealtimeEventType.AUDIO_CAPTURE_COMPLETED,
        RealtimeEventType.USER_TURN_COMMITTED,
        RealtimeEventType.TRANSCRIBING,
        RealtimeEventType.ASSISTANT_RESPONSE_STARTED,
        RealtimeEventType.RESPONDING,
        RealtimeEventType.ASSISTANT_SPEECH_STARTED,
        RealtimeEventType.SPEAKING,
        RealtimeEventType.TURN_COMPLETED,
        RealtimeEventType.SESSION_IDLE,
    ]


def test_ptt_uses_streamed_utterance_when_resident_stream_is_available(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    service = _service(tmp_path)
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=4, chunk_source_factory=_blocking_source)
    stream.start()
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine(calls),  # type: ignore[return-value]
        audio_capture=lambda: (_ for _ in ()).throw(AssertionError("fallback capture should not run")),
        resident_stream=stream,
        utterance_segmenter=_segmenter(),
    )

    resident.ptt()
    stream.publish_for_test(np.zeros(4, dtype=np.float32))
    stream.publish_for_test(np.full(4, 0.2, dtype=np.float32))
    stream.publish_for_test(np.full(4, 0.2, dtype=np.float32))
    stream.publish_for_test(np.zeros(4, dtype=np.float32))
    stream.publish_for_test(np.zeros(4, dtype=np.float32))

    _wait_for(lambda: service.status().last_transcript == "resident transcript")
    stream.stop()

    assert len(calls) == 1
    assert calls[0][1] == 16000
    assert calls[0][0].shape == (20,)
    assert np.array_equal(calls[0][0][:4], np.zeros(4, dtype=np.float32))
    assert service.status().invocation_source == "ptt"
    diagnostics = service.status().voice_capture_diagnostics
    assert diagnostics is not None
    assert diagnostics["source"] == "ptt"
    assert diagnostics["stage"] == "segment"
    assert diagnostics["reason"] == "silence"
    assert diagnostics["speech_chunks"] == 2


def test_streamed_ptt_no_speech_records_failure_without_committing_audio(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    service = _service(tmp_path)
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=4, chunk_source_factory=_blocking_source)
    stream.start()
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine(calls),  # type: ignore[return-value]
        audio_capture=lambda: (_ for _ in ()).throw(AssertionError("fallback capture should not run")),
        resident_stream=stream,
        utterance_segmenter=_segmenter(),
    )

    resident.ptt()
    stream.publish_for_test(np.zeros(4, dtype=np.float32))
    stream.publish_for_test(np.zeros(4, dtype=np.float32))

    _wait_for(lambda: service.status().state == "FAILED")
    stream.stop()
    status = service.status()

    assert calls == []
    assert status.failure_reason == "No speech detected during PTT"
    assert status.invocation_source == "ptt"
    assert status.voice_capture_diagnostics is not None
    assert status.voice_capture_diagnostics["reason"] == "no-speech"
    assert status.voice_capture_diagnostics["speech_chunks"] == 0


def test_ptt_only_mode_falls_back_to_blocking_capture_when_stream_is_stopped(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    service = _service(tmp_path)
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=4)
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine(calls),  # type: ignore[return-value]
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
        resident_stream=stream,
        utterance_segmenter=_segmenter(),
    )
    resident.set_mode("ptt-only")

    resident.ptt()

    _wait_for(lambda: service.status().last_transcript == "resident transcript")
    assert len(calls) == 1
    assert np.array_equal(calls[0][0], np.ones(8, dtype=np.float32))


def test_wake_capable_mode_fails_visibly_when_required_stream_is_stopped(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    service = _service(tmp_path)
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=4)
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine(calls),  # type: ignore[return-value]
        audio_capture=lambda: (_ for _ in ()).throw(AssertionError("fallback capture should not run")),
        resident_stream=stream,
        utterance_segmenter=_segmenter(),
    )

    resident.ptt()

    _wait_for(lambda: service.status().state == "FAILED")
    assert calls == []
    assert service.status().failure_reason == RESIDENT_STREAM_STOPPED_PTT_REASON
    assert service.status().invocation_source == "ptt"


def test_invocation_suspends_and_resumes_wake_monitor_hooks(tmp_path: Path) -> None:
    calls: list[str] = []
    service = _service(tmp_path)
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine([]),  # type: ignore[return-value]
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
        before_invocation=lambda: calls.append("pause") or True,
        after_invocation=lambda should_resume: calls.append(f"resume:{should_resume}"),
    )

    resident.ptt()

    _wait_for(lambda: service.status().last_transcript == "resident transcript")
    assert calls == ["pause", "resume:True"]


def test_resume_hook_failure_does_not_stop_later_invocations(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    service = _service(tmp_path)

    def resume_error(_should_resume: object) -> None:
        raise RuntimeError("wake resume failed")

    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine(calls),  # type: ignore[return-value]
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
        before_invocation=lambda: True,
        after_invocation=resume_error,
    )

    resident.ptt()
    _wait_for(lambda: len(calls) == 1)

    resident.ptt()

    _wait_for(lambda: len(calls) == 2)
    assert service.status().last_transcript == "resident transcript"


def test_wake_and_ptt_enqueue_same_invocation_service(tmp_path: Path) -> None:
    sources: list[str] = []
    service = _service(tmp_path)
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine([]),  # type: ignore[return-value]
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
    )
    original_enqueue = resident.enqueue

    def tracking_enqueue(source: str):
        sources.append(source)
        return original_enqueue(source)

    tracking_enqueue("ptt")
    tracking_enqueue("wake")

    _wait_for(lambda: service.status().invocation_source == "wake")
    assert sources == ["ptt", "wake"]
    assert service.status().last_transcript == "resident transcript"


def test_interrupted_ptt_queues_barge_in_follow_up_through_resident_service(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    service = _service(tmp_path)
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=4, chunk_source_factory=_blocking_source)
    stream.start()
    interrupted = TurnResult(
        turn_id="turn-interrupted",
        session_id="session-resident",
        transcript="first",
        response_text="interrupted response",
        final_state=ConversationState.IDLE,
        interrupted=True,
        interruption_events=[{"type": "barge_in", "recovery_state": "RECOVERING"}],
    )
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine(calls, interrupted if len(calls) == 0 else None),  # type: ignore[return-value]
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
        resident_stream=stream,
        utterance_segmenter=_segmenter(),
    )

    resident.enqueue("ptt", np.ones(8, dtype=np.float32), 16000)
    _wait_for(lambda: len(calls) == 1)
    stream.publish_for_test(np.zeros(4, dtype=np.float32))
    stream.publish_for_test(np.full(4, 0.2, dtype=np.float32))
    stream.publish_for_test(np.full(4, 0.2, dtype=np.float32))
    stream.publish_for_test(np.zeros(4, dtype=np.float32))
    stream.publish_for_test(np.zeros(4, dtype=np.float32))

    _wait_for(lambda: service.status().invocation_source == "barge_in")
    stream.stop()

    assert len(calls) == 2
    assert calls[1][0].shape == (20,)
    assert calls[1][1] == 16000
    assert service.status().last_transcript == "resident transcript"


def test_interrupted_ptt_only_does_not_queue_barge_in_follow_up(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    service = _service(tmp_path)
    interrupted = TurnResult(
        turn_id="turn-interrupted",
        session_id="session-resident",
        transcript="first",
        response_text="interrupted response",
        final_state=ConversationState.IDLE,
        interrupted=True,
        interruption_events=[{"type": "barge_in", "recovery_state": "RECOVERING"}],
    )
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine(calls, interrupted),  # type: ignore[return-value]
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
    )
    resident.set_mode("ptt-only")

    resident.enqueue("ptt", np.ones(8, dtype=np.float32), 16000)

    _wait_for(lambda: service.status().invocation_source == "ptt")
    time.sleep(0.05)

    assert len(calls) == 1
    assert service.status().invocation_source == "ptt"


def test_ptt_only_temporarily_disables_engine_interruption_monitor(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    service = _service(tmp_path)
    marker_detector = object()
    marker_chunks = object()

    class InspectingEngine(_FakeEngine):
        barge_in_detector = marker_detector
        interruption_audio_chunks = marker_chunks

        def run_voice_turn(self, audio: np.ndarray, sample_rate: int) -> TurnResult:
            assert self.barge_in_detector is None
            assert self.interruption_audio_chunks is None
            return super().run_voice_turn(audio, sample_rate)

    engine = InspectingEngine(calls)
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: engine,  # type: ignore[return-value]
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
    )
    resident.set_mode("ptt-only")

    resident.enqueue("ptt", np.ones(8, dtype=np.float32), 16000)

    _wait_for(lambda: service.status().last_transcript == "resident transcript")

    assert engine.barge_in_detector is marker_detector
    assert engine.interruption_audio_chunks is marker_chunks


def test_resident_interruption_chunks_tolerates_short_empty_reads() -> None:
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=4, chunk_source_factory=_blocking_source)
    stream.start()
    _wait_for(lambda: stream.status().running)
    chunks = resident_interruption_chunks(stream)
    assert chunks is not None
    iterator = iter(chunks)
    received: list[np.ndarray] = []
    errors: list[BaseException] = []

    def read_chunk() -> None:
        try:
            received.append(next(iterator))
        except BaseException as exc:
            errors.append(exc)

    reader = threading.Thread(target=read_chunk)
    reader.start()
    try:
        time.sleep(0.2)
        assert reader.is_alive()
        stream.publish_for_test(np.full(4, 0.2, dtype=np.float32))
        reader.join(timeout=1.0)
    finally:
        stream.stop()

    assert not reader.is_alive()
    assert errors == []
    assert len(received) == 1
    assert np.array_equal(received[0], np.full(4, 0.2, dtype=np.float32))


def test_interrupted_barge_in_does_not_recursively_queue_follow_up(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    service = _service(tmp_path)
    interrupted = TurnResult(
        turn_id="turn-interrupted",
        session_id="session-resident",
        transcript="barge",
        response_text="interrupted response",
        final_state=ConversationState.IDLE,
        interrupted=True,
        interruption_events=[{"type": "barge_in", "recovery_state": "RECOVERING"}],
    )
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine(calls, interrupted),  # type: ignore[return-value]
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
    )

    resident.enqueue("barge_in")

    _wait_for(lambda: service.status().invocation_source == "barge_in")
    time.sleep(0.05)

    assert len(calls) == 1


def test_wake_invocation_uses_provided_audio_without_new_capture(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    service = _service(tmp_path)
    wake_audio = np.arange(6, dtype=np.float32)

    def capture_error():
        raise AssertionError("wake payload should avoid a second microphone capture")

    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine(calls),  # type: ignore[return-value]
        audio_capture=capture_error,
    )

    resident.enqueue("wake", wake_audio, 16000)

    _wait_for(lambda: service.status().last_transcript == "resident transcript")
    assert len(calls) == 1
    assert np.array_equal(calls[0][0], wake_audio)
    assert calls[0][1] == 16000
    assert service.status().invocation_source == "wake"
    event_types = [event.event_type for event in resident.last_realtime_events()]
    assert RealtimeEventType.AUDIO_CAPTURE_STARTED not in event_types
    assert RealtimeEventType.AUDIO_CAPTURE_COMPLETED in event_types


def test_capture_failure_records_failed_voice_status(tmp_path: Path) -> None:
    service = _service(tmp_path)

    def capture_error():
        raise RuntimeError("microphone unavailable")

    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine([]),  # type: ignore[return-value]
        audio_capture=capture_error,
    )

    resident.ptt()

    _wait_for(lambda: service.status().state == "FAILED")
    status = service.status()
    assert status.failure_reason == "microphone unavailable"
    assert status.last_transcript is None
    assert status.last_response is None
    assert status.invocation_source == "ptt"
    assert [event.event_type for event in resident.last_realtime_events()][-1] == RealtimeEventType.SESSION_FAILED


def test_wake_empty_transcript_reports_no_speech_detected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    empty_result = TurnResult(
        turn_id="turn-empty",
        session_id="session-resident",
        transcript="",
        response_text=None,
        final_state=ConversationState.FAILED,
        failure_reason="STT returned empty transcript",
    )
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine([], empty_result),  # type: ignore[return-value]
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
    )

    resident.enqueue("wake")

    _wait_for(lambda: service.status().state == "FAILED")
    status = service.status()
    assert status.failure_reason == "No speech detected after wake"
    assert status.invocation_source == "wake"


def test_wake_empty_audio_reports_no_speech_without_fallback_capture(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    service = _service(tmp_path)
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine(calls),  # type: ignore[return-value]
        audio_capture=lambda: (_ for _ in ()).throw(AssertionError("empty wake audio should not recapture")),
    )

    resident.enqueue("wake", np.array([], dtype=np.float32), 16000)

    _wait_for(lambda: service.status().state == "FAILED")
    status = service.status()
    assert calls == []
    assert status.failure_reason == "No speech detected after wake"
    assert status.invocation_source == "wake"


def test_ptt_empty_transcript_keeps_stt_failure_reason(tmp_path: Path) -> None:
    service = _service(tmp_path)
    empty_result = TurnResult(
        turn_id="turn-empty",
        session_id="session-resident",
        transcript="",
        response_text=None,
        final_state=ConversationState.FAILED,
        failure_reason="STT returned empty transcript",
    )
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine([], empty_result),  # type: ignore[return-value]
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
    )

    resident.ptt()

    _wait_for(lambda: service.status().state == "FAILED")
    status = service.status()
    assert status.failure_reason == "STT returned empty transcript"
    assert status.invocation_source == "ptt"
