from __future__ import annotations

from backend.app.agents.critic import review_trace_dry_run
from backend.app.agents.ledger import AgentLedger, AgentLedgerRecord
from backend.app.agents.policy import AgentPolicy


def test_critic_dry_run_reviews_existing_records(tmp_path) -> None:
    ledger = AgentLedger(tmp_path / "ledger.sqlite3")
    ledger.append(AgentLedgerRecord(record_id="record-1", trace_id="trace-1", record_type="plan", role_id="planner"))
    policy = AgentPolicy(enabled=True, allowed_roles=["critic"])

    review = review_trace_dry_run("trace-1", policy=policy, ledger=ledger)

    assert review.approved is True
    assert review.reviewed_record_ids == ["record-1"]
    assert ledger.list_by_trace("trace-1")[-1].role_id == "critic"


def test_critic_dry_run_warns_when_role_disabled(tmp_path) -> None:
    ledger = AgentLedger(tmp_path / "ledger.sqlite3")
    policy = AgentPolicy(enabled=False, allowed_roles=["critic"])

    review = review_trace_dry_run("trace-1", policy=policy, ledger=ledger)

    assert review.approved is False
    assert "critic role is not allowed by policy" in review.warnings
    assert "no trace records found" in review.warnings
