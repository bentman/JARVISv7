from __future__ import annotations

from backend.app.agents.ledger import AgentLedger, AgentLedgerRecord


def trace_payload(records: list[AgentLedgerRecord]) -> dict[str, object]:
    return {
        "records": [record.model_dump() for record in records],
        "record_count": len(records),
        "read_only": True,
    }


def read_trace(ledger: AgentLedger, trace_id: str) -> dict[str, object]:
    return trace_payload(ledger.list_by_trace(trace_id))
