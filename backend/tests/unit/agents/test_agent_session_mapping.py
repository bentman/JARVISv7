"""Tests for backend.app.agents.session_mapping."""

from __future__ import annotations

import pytest
from backend.app.agents.schema import AgentProfile
from backend.app.agents.session_mapping import (
    AgentSessionEvent,
    AgentSessionRecord,
    build_session_record,
)


def _event(event_type: str = "output", **kwargs) -> AgentSessionEvent:
    return AgentSessionEvent(
        event_type=event_type,
        data=kwargs.pop("data", {"detail": "test"}),
        timestamp=kwargs.pop("timestamp", "2026-09-07T00:00:00+00:00"),
    )


def _profile(**overrides) -> AgentProfile:
    values = {
        "profile_id": "test-agent",
        "display_name": "Test Agent",
        "purpose": "Testing",
        "instructions": "Follow test conventions.",
        "invocation_modes": ("direct",),
        "capability_ids": (),
        "memory_scope": "working",
        "approval_class": "standard",
        "timeout_ms": 30000,
        "cancellable": True,
        "output_contract": {"type": "object"},
        "provider_model_policy": {},
    }
    values.update(overrides)
    return AgentProfile(**values)


# --- AgentSessionEvent ---


def test_event_creation() -> None:
    event = _event("initialized")
    assert event.event_type == "initialized"
    assert event.data == {"detail": "test"}
    assert event.timestamp == "2026-09-07T00:00:00+00:00"


def test_event_rejects_invalid_type() -> None:
    with pytest.raises(ValueError, match="event_type must be one of"):
        AgentSessionEvent(event_type="bogus", data={}, timestamp="2026-09-07T00:00:00+00:00")


def test_event_rejects_empty_type() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        AgentSessionEvent(event_type="", data={}, timestamp="2026-09-07T00:00:00+00:00")


def test_event_rejects_non_dict_data() -> None:
    with pytest.raises(ValueError, match="data must be a dict"):
        AgentSessionEvent(event_type="output", data="not-a-dict", timestamp="2026-09-07T00:00:00+00:00")  # type: ignore[arg-type]


def test_event_rejects_empty_timestamp() -> None:
    with pytest.raises(ValueError, match="timestamp must be a non-empty"):
        AgentSessionEvent(event_type="output", data={}, timestamp="")


def test_event_all_valid_types() -> None:
    for etype in (
        "initialized", "session_created", "permission_request", "progress",
        "output", "error", "completed", "cancelled",
    ):
        event = _event(etype)
        assert event.event_type == etype


# --- AgentSessionRecord ---


def test_record_creation() -> None:
    record = AgentSessionRecord(
        agent_id="agent-1", profile_id="profile-1", run_id="run-1"
    )
    assert record.status == "running"
    assert record.events == []
    assert record.error is None


def test_record_rejects_empty_agent_id() -> None:
    with pytest.raises(ValueError, match="agent_id must be a non-empty"):
        AgentSessionRecord(agent_id="", profile_id="p", run_id="r")


def test_record_rejects_invalid_status() -> None:
    with pytest.raises(ValueError, match="status must be one of"):
        AgentSessionRecord(agent_id="a", profile_id="p", run_id="r", status="bogus")


def test_record_append_event() -> None:
    record = AgentSessionRecord(agent_id="a", profile_id="p", run_id="r")
    event = _event("output")

    updated = record.append_event(event)

    assert len(updated.events) == 1
    assert updated.events[0] is event
    assert len(record.events) == 0  # original unchanged (frozen)


def test_record_append_event_preserves_fields() -> None:
    record = AgentSessionRecord(
        agent_id="a", profile_id="p", run_id="r",
        memory_scope="episodic", capability_ids=("cap-1",),
    )
    updated = record.append_event(_event("output"))

    assert updated.agent_id == "a"
    assert updated.memory_scope == "episodic"
    assert updated.capability_ids == ("cap-1",)


def test_record_to_delegated_run() -> None:
    record = AgentSessionRecord(
        agent_id="agent-1",
        profile_id="profile-1",
        run_id="run-1",
        events=[_event("output"), _event("completed")],
        status="completed",
        output={"text": "done"},
        memory_scope="working",
        capability_ids=("cap-1", "cap-2"),
    )

    result = record.to_delegated_run()

    assert result == {
        "run_id": "run-1",
        "agent_id": "agent-1",
        "profile_id": "profile-1",
        "status": "completed",
        "output": {"text": "done"},
        "event_count": 2,
        "memory_scope": "working",
        "capability_ids": ["cap-1", "cap-2"],
        "error": None,
    }


def test_record_to_delegated_run_with_error() -> None:
    record = AgentSessionRecord(
        agent_id="agent-1",
        profile_id="profile-1",
        run_id="run-1",
        status="failed",
        error="connection refused",
    )

    result = record.to_delegated_run()

    assert result["status"] == "failed"
    assert result["error"] == "connection refused"
    assert result["event_count"] == 0


# --- build_session_record ---


def test_build_session_record_from_profile() -> None:
    profile = _profile(
        capability_ids=("read-file", "mcp-search"),
        memory_scope="episodic",
    )
    events = [_event("initialized"), _event("output")]

    record = build_session_record(profile, "run-42", events)

    assert record.agent_id == "test-agent"
    assert record.profile_id == "test-agent"
    assert record.run_id == "run-42"
    assert record.status == "running"
    assert record.memory_scope == "episodic"
    assert record.capability_ids == ("read-file", "mcp-search")
    assert len(record.events) == 2


def test_build_session_record_defaults_when_no_events() -> None:
    profile = _profile()
    record = build_session_record(profile, "run-1")

    assert record.events == []
    assert record.status == "running"
    assert record.error is None


# --- Status transitions ---


def test_status_running_to_completed() -> None:
    running = AgentSessionRecord(agent_id="a", profile_id="p", run_id="r", status="running")
    completed = AgentSessionRecord(agent_id="a", profile_id="p", run_id="r", status="completed")

    assert running.status == "running"
    assert completed.status == "completed"


def test_status_running_to_failed() -> None:
    failed = AgentSessionRecord(
        agent_id="a", profile_id="p", run_id="r", status="failed", error="timeout"
    )

    assert failed.status == "failed"
    assert failed.error == "timeout"
