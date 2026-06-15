from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.agents.ledger import AgentLedger, AgentLedgerRecord


class CuratedArtifactCandidate(BaseModel):
    artifact_id: str
    score: float
    reasons: list[str] = Field(default_factory=list)


def curate_artifacts_dry_run(
    trace_id: str,
    artifacts: list[dict[str, Any]],
    *,
    ledger: AgentLedger,
) -> list[CuratedArtifactCandidate]:
    candidates: list[CuratedArtifactCandidate] = []
    seen: set[str] = set()
    for artifact in artifacts:
        artifact_id = str(artifact.get("turn_id") or artifact.get("session_id") or "")
        if not artifact_id or artifact_id in seen:
            continue
        seen.add(artifact_id)
        transcript = str(artifact.get("transcript") or "")
        response = str(artifact.get("response_text") or "")
        failure = artifact.get("failure_reason")
        score = 0.0
        reasons: list[str] = []
        if transcript.strip():
            score += 0.4
            reasons.append("has transcript")
        if response.strip():
            score += 0.4
            reasons.append("has response")
        if not failure:
            score += 0.2
            reasons.append("no failure")
        candidates.append(CuratedArtifactCandidate(artifact_id=artifact_id, score=round(score, 2), reasons=reasons))

    ledger.append(
        AgentLedgerRecord(
            trace_id=trace_id,
            role_id="curator",
            record_type="outcome",
            payload={"candidates": [candidate.model_dump() for candidate in candidates], "dry_run": True},
        )
    )
    return candidates
