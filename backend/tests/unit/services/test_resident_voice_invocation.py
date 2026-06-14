from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from backend.app.conversation.engine import TurnResult
from backend.app.conversation.realtime.events import RealtimeEventType
from backend.app.conversation.states import ConversationState
from backend.app.services.resident_voice_invocation import ResidentVoiceInvocationService
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
        RealtimeEventType.REASONING,
        RealtimeEventType.RESPONDING,
        RealtimeEventType.ASSISTANT_SPEECH_STARTED,
        RealtimeEventType.SPEAKING,
        RealtimeEventType.TURN_COMPLETED,
        RealtimeEventType.SESSION_IDLE,
    ]


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
