from __future__ import annotations

from backend.app.agents.executor import AgentToolRequest, evaluate_tool_request_dry_run
from backend.app.agents.ledger import AgentLedger
from backend.app.agents.policy import AgentPolicy


class Registry:
    def __init__(self) -> None:
        self.invoked = False

    def list_tools(self) -> list[str]:
        return ["time"]

    def invoke(self, tool_name: str, tool_input: dict[str, object]) -> str:
        self.invoked = True
        return "not expected"


def test_executor_dry_run_allows_registered_policy_allowed_tool_without_invoking(tmp_path) -> None:
    ledger = AgentLedger(tmp_path / "ledger.sqlite3")
    policy = AgentPolicy(enabled=True, allowed_roles=["executor"], allowed_tools=["time"])
    registry = Registry()

    decision = evaluate_tool_request_dry_run(
        AgentToolRequest(trace_id="trace-1", requested_tool="time"),
        policy=policy,
        ledger=ledger,
        registry=registry,
    )

    assert decision.allowed is True
    assert decision.dry_run is True
    assert registry.invoked is False
    assert ledger.list_by_trace("trace-1")[0].payload["allowed"] is True


def test_executor_dry_run_blocks_unregistered_tool(tmp_path) -> None:
    ledger = AgentLedger(tmp_path / "ledger.sqlite3")
    policy = AgentPolicy(enabled=True, allowed_roles=["executor"], allowed_tools=["missing"])

    decision = evaluate_tool_request_dry_run(
        AgentToolRequest(trace_id="trace-1", requested_tool="missing"),
        policy=policy,
        ledger=ledger,
        registry=Registry(),
    )

    assert decision.allowed is False
    assert decision.reason == "tool is not registered"
