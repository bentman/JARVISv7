from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.agents.messages import AgentMessage, AgentRequest, AgentResponse


def test_agent_message_contract_serializes_payload() -> None:
    message = AgentMessage(
        trace_id="trace-1",
        role="planner",
        message_type="plan",
        payload={"steps": ["inspect"]},
    )

    payload = message.model_dump()

    assert payload["trace_id"] == "trace-1"
    assert payload["role"] == "planner"
    assert payload["message_type"] == "plan"
    assert payload["payload"] == {"steps": ["inspect"]}
    assert payload["message_id"]


def test_agent_request_and_response_contracts_are_typed() -> None:
    request = AgentRequest(trace_id="trace-1", requested_role="critic", objective="review")
    response = AgentResponse(trace_id="trace-1", responding_role="critic", status="recorded")

    assert request.run_mode == "boundary"
    assert response.run_mode == "boundary"


def test_agent_message_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        AgentMessage(trace_id="trace-1", role="unknown", message_type="event")
