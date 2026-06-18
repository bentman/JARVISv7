from __future__ import annotations

from backend.app.agents.ledger import AgentLedger, AgentLedgerRecord


def test_agent_ledger_persists_and_reopens_records(tmp_path) -> None:
    path = tmp_path / "agent_ledger.sqlite3"
    ledger = AgentLedger(path)
    record = AgentLedgerRecord(
        record_id="record-1",
        trace_id="trace-1",
        session_id="session-1",
        turn_id="turn-1",
        role_id="planner",
        record_type="plan",
        payload={"summary": "inspect only"},
        created_at="2026-06-15T00:00:00+00:00",
    )

    ledger.append(record)
    reopened = AgentLedger(path)

    assert reopened.list_by_trace("trace-1") == [record]
    assert reopened.list_by_turn("session-1", "turn-1") == [record]


def test_agent_ledger_preserves_trace_order(tmp_path) -> None:
    ledger = AgentLedger(tmp_path / "agent_ledger.sqlite3")
    first = AgentLedgerRecord(
        record_id="record-1",
        trace_id="trace-1",
        record_type="policy_decision",
        payload={"enabled": False},
        created_at="2026-06-15T00:00:00+00:00",
    )
    second = AgentLedgerRecord(
        record_id="record-2",
        trace_id="trace-1",
        record_type="event",
        parent_record_id="record-1",
        payload={"event": "boundary_recorded"},
        created_at="2026-06-15T00:00:01+00:00",
    )

    ledger.append(second)
    ledger.append(first)

    assert ledger.list_by_trace("trace-1") == [first, second]


def test_agent_ledger_preserves_append_order_for_same_timestamp(tmp_path) -> None:
    ledger = AgentLedger(tmp_path / "agent_ledger.sqlite3")
    created_at = "2026-06-15T00:00:00+00:00"
    first = AgentLedgerRecord(
        record_id="record-z",
        trace_id="trace-1",
        session_id="session-1",
        turn_id="turn-1",
        record_type="event",
        payload={"event": "first"},
        created_at=created_at,
    )
    second = AgentLedgerRecord(
        record_id="record-a",
        trace_id="trace-1",
        session_id="session-1",
        turn_id="turn-1",
        record_type="event",
        payload={"event": "second"},
        created_at=created_at,
    )

    ledger.append(first)
    ledger.append(second)

    assert ledger.list_by_trace("trace-1") == [first, second]
    assert ledger.list_by_turn("session-1", "turn-1") == [first, second]
