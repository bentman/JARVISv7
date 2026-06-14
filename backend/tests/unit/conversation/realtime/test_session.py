from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.conversation.engine import TurnResult
from backend.app.conversation.realtime.events import RealtimeEventType
from backend.app.conversation.realtime.session import RealtimeConversationSession
from backend.app.conversation.states import ConversationState
from backend.tests.unit.services.test_session_service import _service


class _FakeEngine:
    def __init__(self, result: TurnResult | None = None) -> None:
        self.calls: list[tuple[np.ndarray, int]] = []
        self.result = result

    def run_voice_turn(self, audio: np.ndarray, sample_rate: int) -> TurnResult:
        self.calls.append((audio, sample_rate))
        if self.result is not None:
            return self.result
        return TurnResult(
            turn_id="turn-realtime",
            session_id="session-realtime",
            transcript="hello",
            response_text="response",
            final_state=ConversationState.IDLE,
        )


def test_realtime_voice_invocation_delegates_committed_turn_and_records_order(tmp_path: Path) -> None:
    service = _service(tmp_path)
    engine = _FakeEngine()
    session = RealtimeConversationSession(
        session_service=service,
        engine_provider=lambda: engine,  # type: ignore[return-value]
    )

    session.run_voice_invocation(
        source="ptt",
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
    )

    assert len(engine.calls) == 1
    assert engine.calls[0][1] == 16000
    assert session.ledger.event_types() == [
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
    assert service.status().state == "IDLE"
    assert service.status().last_transcript == "hello"
    assert RealtimeEventType.REASONING not in session.ledger.event_types()


def test_realtime_degraded_tts_response_does_not_record_speech_events(tmp_path: Path) -> None:
    service = _service(tmp_path)
    engine = _FakeEngine(
        TurnResult(
            turn_id="turn-degraded",
            session_id="session-realtime",
            transcript="hello",
            response_text="text response",
            final_state=ConversationState.IDLE,
            tts_degraded=True,
            tts_degraded_reason="TTS runtime is unavailable",
        )
    )
    session = RealtimeConversationSession(
        session_service=service,
        engine_provider=lambda: engine,  # type: ignore[return-value]
    )

    session.run_voice_invocation(
        source="ptt",
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
    )

    event_types = session.ledger.event_types()
    assert RealtimeEventType.ASSISTANT_RESPONSE_STARTED in event_types
    assert RealtimeEventType.RESPONDING in event_types
    assert RealtimeEventType.ASSISTANT_SPEECH_STARTED not in event_types
    assert RealtimeEventType.SPEAKING not in event_types
    assert event_types[-2:] == [
        RealtimeEventType.TURN_COMPLETED,
        RealtimeEventType.SESSION_IDLE,
    ]


def test_realtime_wake_audio_uses_payload_without_capture(tmp_path: Path) -> None:
    service = _service(tmp_path)
    engine = _FakeEngine()
    session = RealtimeConversationSession(
        session_service=service,
        engine_provider=lambda: engine,  # type: ignore[return-value]
    )
    wake_audio = np.arange(4, dtype=np.float32)

    def capture_error() -> tuple[np.ndarray, int]:
        raise AssertionError("capture should not run")

    session.run_voice_invocation(source="wake", audio=wake_audio, sample_rate=16000, audio_capture=capture_error)

    assert len(engine.calls) == 1
    assert np.array_equal(engine.calls[0][0], wake_audio)
    assert RealtimeEventType.AUDIO_CAPTURE_STARTED not in session.ledger.event_types()
    assert RealtimeEventType.AUDIO_CAPTURE_COMPLETED in session.ledger.event_types()


def test_realtime_wake_empty_transcript_maps_no_speech_failure(tmp_path: Path) -> None:
    service = _service(tmp_path)
    engine = _FakeEngine(
        TurnResult(
            turn_id="turn-empty",
            session_id="session-realtime",
            transcript="",
            response_text=None,
            final_state=ConversationState.FAILED,
            failure_reason="STT returned empty transcript",
        )
    )
    session = RealtimeConversationSession(
        session_service=service,
        engine_provider=lambda: engine,  # type: ignore[return-value]
    )

    result = session.run_voice_invocation(
        source="wake",
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
    )

    assert result.failure_reason == "No speech detected after wake"
    assert service.status().state == "FAILED"
    assert service.status().failure_reason == "No speech detected after wake"
    assert session.ledger.event_types()[-1] == RealtimeEventType.SESSION_FAILED


def test_realtime_capture_failure_records_failed_status_and_event(tmp_path: Path) -> None:
    service = _service(tmp_path)
    session = RealtimeConversationSession(
        session_service=service,
        engine_provider=lambda: _FakeEngine(),  # type: ignore[return-value]
    )

    try:
        session.run_voice_invocation(
            source="ptt",
            audio_capture=lambda: (_ for _ in ()).throw(RuntimeError("microphone unavailable")),
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("capture failure was not raised")

    assert service.status().state == "FAILED"
    assert service.status().failure_reason == "microphone unavailable"
    assert session.ledger.event_types()[-1] == RealtimeEventType.SESSION_FAILED
