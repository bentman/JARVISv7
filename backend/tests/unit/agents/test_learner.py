from __future__ import annotations

from backend.app.agents.curator import CuratedArtifactCandidate
from backend.app.agents.learner import propose_learning_plan_dry_run
from backend.app.agents.ledger import AgentLedger


def test_learner_dry_run_proposes_only_without_training_actions(tmp_path) -> None:
    ledger = AgentLedger(tmp_path / "ledger.sqlite3")
    candidates = [CuratedArtifactCandidate(artifact_id="turn-1", score=1.0)]

    proposal = propose_learning_plan_dry_run("trace-1", candidates, ledger=ledger)

    assert proposal.dry_run is True
    assert proposal.recommended_action == "collect_more_candidates"
    assert proposal.blocked_actions == ["train_model", "deploy_adapter", "route_model"]
    assert ledger.list_by_trace("trace-1")[0].record_type == "plan"
