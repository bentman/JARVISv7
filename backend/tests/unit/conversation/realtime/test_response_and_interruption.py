from __future__ import annotations

from backend.app.conversation.realtime.events import RealtimeEventType
from backend.app.conversation.realtime.interruption import record_interruption_boundary
from backend.app.conversation.realtime.ledger import RealtimeEventLedger
from backend.app.conversation.realtime.response_queue import RealtimeResponseQueue


def test_response_queue_ignores_empty_responses_and_preserves_order() -> None:
    queue = RealtimeResponseQueue()

    queue.enqueue(None)
    queue.enqueue("")
    queue.enqueue("first")
    queue.enqueue("second")

    assert len(queue) == 2
    assert queue.dequeue() == "first"
    assert queue.dequeue() == "second"
    assert queue.dequeue() is None


def test_interruption_boundary_records_expected_event_order() -> None:
    ledger = RealtimeEventLedger(session_id="session-1")

    record_interruption_boundary(
        ledger,
        source="ptt",
        turn_id="turn-1",
        interruption_event={"type": "barge_in"},
    )

    assert ledger.event_types() == [
        RealtimeEventType.USER_INTERRUPTION_DETECTED,
        RealtimeEventType.ASSISTANT_SPEECH_STOP_REQUESTED,
        RealtimeEventType.TURN_RECOVERING,
    ]
    assert ledger.events[0].metadata == {"type": "barge_in"}
    assert ledger.events[-1].state == "RECOVERING"
