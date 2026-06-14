from __future__ import annotations

from backend.app.conversation.realtime.events import RealtimeEventType
from backend.app.conversation.realtime.ledger import RealtimeEventLedger
from backend.app.conversation.states import ConversationState


def test_realtime_ledger_assigns_monotonic_sequences() -> None:
    ledger = RealtimeEventLedger(session_id="session-1")

    first = ledger.append(RealtimeEventType.SESSION_ACTIVE, source="ptt", state=ConversationState.IDLE)
    second = ledger.append(RealtimeEventType.INVOCATION_RECEIVED, source="ptt")

    assert first.sequence == 1
    assert second.sequence == 2
    assert ledger.event_types() == [
        RealtimeEventType.SESSION_ACTIVE,
        RealtimeEventType.INVOCATION_RECEIVED,
    ]
    assert ledger.to_dicts()[0]["state"] == "IDLE"


def test_realtime_event_metadata_is_copied() -> None:
    ledger = RealtimeEventLedger(session_id="session-1")
    metadata = {"sample_rate": 16000}

    event = ledger.append(RealtimeEventType.AUDIO_CAPTURE_COMPLETED, metadata=metadata)
    metadata["sample_rate"] = 8000

    assert event.metadata == {"sample_rate": 16000}
