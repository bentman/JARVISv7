from __future__ import annotations

from typing import Any, Protocol

from backend.app.agents.ledger import AgentLedger, AgentLedgerRecord
from backend.app.agents.policy import AgentPolicy
from pydantic import BaseModel, Field


class ToolRegistryView(Protocol):
    def list_tools(self) -> list[str]:
        ...


class AgentToolRequest(BaseModel):
    trace_id: str
    requested_tool: str
    tool_input: dict[str, Any] = Field(default_factory=dict)
    role_id: str = "executor"


class AgentToolDecision(BaseModel):
    trace_id: str
    requested_tool: str
    allowed: bool
    reason: str
    dry_run: bool = True


def evaluate_tool_request_dry_run(
    request: AgentToolRequest,
    *,
    policy: AgentPolicy,
    ledger: AgentLedger,
    registry: ToolRegistryView,
) -> AgentToolDecision:
    registered_tools = set(registry.list_tools())
    if request.requested_tool not in registered_tools:
        decision = AgentToolDecision(
            trace_id=request.trace_id,
            requested_tool=request.requested_tool,
            allowed=False,
            reason="tool is not registered",
        )
    elif not policy.allows_role("executor"):
        decision = AgentToolDecision(
            trace_id=request.trace_id,
            requested_tool=request.requested_tool,
            allowed=False,
            reason="executor role is not allowed by policy",
        )
    elif not policy.allows_tool(request.requested_tool):
        decision = AgentToolDecision(
            trace_id=request.trace_id,
            requested_tool=request.requested_tool,
            allowed=False,
            reason="tool is not allowed by policy",
        )
    else:
        decision = AgentToolDecision(
            trace_id=request.trace_id,
            requested_tool=request.requested_tool,
            allowed=True,
            reason="tool request is allowed for dry-run evaluation",
        )

    ledger.append(
        AgentLedgerRecord(
            trace_id=request.trace_id,
            role_id=request.role_id,
            record_type="policy_decision",
            payload={
                **decision.model_dump(),
                "tool_input": request.tool_input,
                "registered_tools": sorted(registered_tools),
            },
        )
    )
    return decision
