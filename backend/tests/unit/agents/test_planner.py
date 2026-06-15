from __future__ import annotations

from backend.app.agents.ledger import AgentLedger
from backend.app.agents.messages import AgentRequest
from backend.app.agents.planner import AgentPlanStep, create_planner_dry_run
from backend.app.agents.policy import AgentPolicy


def test_planner_dry_run_records_plan(tmp_path) -> None:
    ledger = AgentLedger(tmp_path / "ledger.sqlite3")
    policy = AgentPolicy(enabled=True, allowed_roles=["planner"])
    request = AgentRequest(trace_id="trace-1", requested_role="planner", objective="inspect status", run_mode="dry_run")

    response = create_planner_dry_run(
        request,
        policy=policy,
        ledger=ledger,
        steps=[AgentPlanStep(step_id="step-1", description="inspect only")],
    )

    records = ledger.list_by_trace("trace-1")
    assert response.status == "recorded"
    assert response.run_mode == "dry_run"
    assert len(records) == 1
    assert records[0].record_type == "plan"
    assert records[0].payload["dry_run"] is True


def test_planner_dry_run_rejects_when_role_is_disabled(tmp_path) -> None:
    ledger = AgentLedger(tmp_path / "ledger.sqlite3")
    policy = AgentPolicy(enabled=False, allowed_roles=["planner"])
    request = AgentRequest(trace_id="trace-1", requested_role="planner", objective="inspect status", run_mode="dry_run")

    response = create_planner_dry_run(request, policy=policy, ledger=ledger)

    records = ledger.list_by_trace("trace-1")
    assert response.status == "rejected"
    assert records[0].record_type == "policy_decision"
    assert records[0].payload["allowed"] is False
