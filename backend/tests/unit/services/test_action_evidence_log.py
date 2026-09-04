from __future__ import annotations

from pathlib import Path

import pytest
from backend.app.actions.catalog import (
    MEMORY_RECORD_CONFIRM,
    MEMORY_RECORD_FORGET,
    PROVIDER_PROFILE_WRITE,
    CapabilityObservation,
)
from backend.app.artifacts.storage import ACTION_LOG_NAME, read_action_events
from backend.app.services.capability_service import CapabilityService

READY = CapabilityObservation(
    memory_service_present=True,
    memory_curation_present=True,
    provider_store_present=True,
)


def service(evidence_dir: Path, **handlers) -> CapabilityService:
    return CapabilityService(
        observe=lambda: READY, handlers=handlers, evidence_dir=evidence_dir
    )


def confirm_arguments() -> dict:
    return {"fact_id": "fact-1", "expected_revision": 1}


def test_action_evidence_is_durable_without_any_active_session(tmp_path: Path) -> None:
    instance = service(tmp_path, **{MEMORY_RECORD_CONFIRM: lambda args, op: {"ok": True}})

    instance.propose(
        capability_id=MEMORY_RECORD_CONFIRM,
        arguments=confirm_arguments(),
        proposed_by="operator",
        reason="operator confirmed the fact",
    )

    events = read_action_events(tmp_path)
    kinds = [event["kind"] for event in events]
    assert kinds == ["action_proposal", "authorization_decision", "execution_result"]
    assert all(event["capability_id"] == MEMORY_RECORD_CONFIRM for event in events)


def test_the_log_appends_across_process_restarts(tmp_path: Path) -> None:
    first = service(tmp_path, **{MEMORY_RECORD_CONFIRM: lambda args, op: {"ok": True}})
    first.propose(
        capability_id=MEMORY_RECORD_CONFIRM,
        arguments=confirm_arguments(),
        proposed_by="operator",
        reason="operator confirmed the fact",
    )
    before = len(read_action_events(tmp_path))

    second = service(tmp_path, **{MEMORY_RECORD_CONFIRM: lambda args, op: {"ok": True}})
    second.propose(
        capability_id=MEMORY_RECORD_CONFIRM,
        arguments={"fact_id": "fact-2", "expected_revision": 1},
        proposed_by="operator",
        reason="operator confirmed the fact",
    )

    events = read_action_events(tmp_path)
    assert len(events) == before * 2
    assert [event["record"].get("arguments", {}).get("fact_id") for event in events].count("fact-2") >= 1


def test_evidence_outlives_the_bounded_in_memory_audit(tmp_path: Path) -> None:
    instance = service(tmp_path, **{MEMORY_RECORD_CONFIRM: lambda args, op: {"ok": True}})

    for index in range(40):
        instance.propose(
            capability_id=MEMORY_RECORD_CONFIRM,
            arguments={"fact_id": f"fact-{index}", "expected_revision": 1},
            proposed_by="operator",
            reason="operator confirmed the fact",
        )

    # The deque keeps at most MAX_AUDIT_RECORDS; the log keeps every record.
    assert len(instance.audit(limit=100).records) <= 100
    assert len(read_action_events(tmp_path)) == 120


def test_secret_arguments_never_reach_the_durable_log(tmp_path: Path) -> None:
    instance = service(tmp_path, **{PROVIDER_PROFILE_WRITE: lambda args, op: {"ok": True}})

    instance.propose(
        capability_id=PROVIDER_PROFILE_WRITE,
        arguments={
            "name": "cloud",
            "kind": "openai",
            "endpoint": "https://api.openai.com/v1",
            "model": "gpt-4",
            "context_window": 8192,
            "timeout_seconds": 30,
            "api_key": "sk-do-not-leak-this-value",
        },
        proposed_by="operator",
        reason="operator added a provider profile",
    )

    raw = (tmp_path / ACTION_LOG_NAME).read_text(encoding="utf-8")
    assert "sk-do-not-leak-this-value" not in raw
    assert '"api_key": "***"' in raw


def test_an_approval_decision_is_recorded_durably(tmp_path: Path) -> None:
    instance = service(tmp_path, **{MEMORY_RECORD_FORGET: lambda args, op: {"ok": True}})
    parked = instance.propose(
        capability_id=MEMORY_RECORD_FORGET,
        arguments=confirm_arguments(),
        proposed_by="model",
        reason="the model proposed forgetting a fact",
    )

    instance.decide(proposal_id=parked.proposal_id, outcome="approved", decided_by="operator")

    kinds = [event["kind"] for event in read_action_events(tmp_path)]
    assert kinds.count("approval_record") == 1
    assert kinds.count("execution_result") == 1


def test_a_failing_evidence_sink_never_fails_an_action_that_already_ran(tmp_path: Path) -> None:
    unwritable = tmp_path / "log"
    unwritable.write_text("not a directory", encoding="utf-8")
    instance = service(unwritable, **{MEMORY_RECORD_CONFIRM: lambda args, op: {"ok": True}})

    view = instance.propose(
        capability_id=MEMORY_RECORD_CONFIRM,
        arguments=confirm_arguments(),
        proposed_by="operator",
        reason="operator confirmed the fact",
    )

    assert view.status == "success"
    assert len(instance.audit().records) == 3


def test_no_log_is_written_when_no_evidence_directory_is_configured(tmp_path: Path) -> None:
    instance = CapabilityService(
        observe=lambda: READY, handlers={MEMORY_RECORD_CONFIRM: lambda args, op: {"ok": True}}
    )

    instance.propose(
        capability_id=MEMORY_RECORD_CONFIRM,
        arguments=confirm_arguments(),
        proposed_by="operator",
        reason="operator confirmed the fact",
    )

    assert not list(tmp_path.iterdir())
    assert len(instance.audit().records) == 3


@pytest.mark.parametrize("kind", ["action_proposal", "authorization_decision", "execution_result"])
def test_every_logged_entry_is_attributable(tmp_path: Path, kind: str) -> None:
    instance = service(tmp_path, **{MEMORY_RECORD_CONFIRM: lambda args, op: {"ok": True}})
    instance.propose(
        capability_id=MEMORY_RECORD_CONFIRM,
        arguments=confirm_arguments(),
        proposed_by="operator",
        reason="operator confirmed the fact",
    )

    entry = next(event for event in read_action_events(tmp_path) if event["kind"] == kind)

    assert entry["proposal_id"]
    assert entry["recorded_at"]
    assert entry["capability_id"] == MEMORY_RECORD_CONFIRM
