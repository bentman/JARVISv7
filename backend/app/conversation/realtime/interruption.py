from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.app.conversation.realtime.events import RealtimeEventType
from backend.app.conversation.realtime.ledger import RealtimeEventLedger


def record_interruption_boundary(
    ledger: RealtimeEventLedger,
    *,
    source: str | None = None,
    turn_id: str | None = None,
    interruption_event: Mapping[str, Any] | None = None,
) -> None:
    metadata = dict(interruption_event or {})
    ledger.append(RealtimeEventType.USER_INTERRUPTION_DETECTED, source=source, turn_id=turn_id, metadata=metadata)
    ledger.append(RealtimeEventType.ASSISTANT_SPEECH_STOP_REQUESTED, source=source, turn_id=turn_id)
    ledger.append(RealtimeEventType.TURN_RECOVERING, source=source, turn_id=turn_id, state="RECOVERING")
