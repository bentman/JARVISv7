from __future__ import annotations

from backend.app.agents.curator import curate_artifacts_dry_run
from backend.app.agents.ledger import AgentLedger


def test_curator_scores_and_deduplicates_artifacts(tmp_path) -> None:
    ledger = AgentLedger(tmp_path / "ledger.sqlite3")

    candidates = curate_artifacts_dry_run(
        "trace-1",
        [
            {"turn_id": "turn-1", "transcript": "hello", "response_text": "ready", "failure_reason": None},
            {"turn_id": "turn-1", "transcript": "duplicate", "response_text": "duplicate"},
            {"turn_id": "turn-2", "transcript": "", "response_text": "", "failure_reason": "failed"},
        ],
        ledger=ledger,
    )

    assert [candidate.artifact_id for candidate in candidates] == ["turn-1", "turn-2"]
    assert candidates[0].score == 1.0
    assert candidates[1].score == 0.0
    assert ledger.list_by_trace("trace-1")[0].role_id == "curator"
