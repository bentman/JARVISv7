from __future__ import annotations

import json
from pathlib import Path

from backend.app.artifacts.session_artifact import SessionArtifact
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.cognition.memory_extraction import MemoryCandidateExtractor
from backend.app.cognition.prompt_envelope import PromptEnvelope
from backend.app.memory.curation_reconciliation import ReviewOnlyCurationPolicy
from backend.app.memory.semantic import SemanticMemory
from backend.app.runtimes.llm.base import LLMBase
from backend.app.services.memory_curation_processor import (
    ReviewOnlyMemoryCurationProcessor,
)
from backend.app.services.memory_curation_service import PersistedSessionEvidence

NOW = "2026-07-24T12:00:00+00:00"


class FakeLLM(LLMBase):
    def __init__(self, output: str) -> None:
        self.output = output

    def generate(self, prompt: str, **kwargs: object) -> str:
        raise AssertionError

    def generate_envelope(self, envelope: PromptEnvelope, **kwargs: object) -> str:
        return self.output

    def is_available(self) -> bool:
        return True

    def runtime_name(self) -> str:
        return "fake"


def _output() -> str:
    candidates = []
    for index, city in ((1, "Chicago"), (2, "Madison")):
        candidates.append(
            {
                "text": f"The user has lived in {city}.",
                "kind": "personal_fact",
                "claim_key": f"model.city.{index}",
                "value": city,
                "relation": "assertion",
                "evidence_refs": [
                    {
                        "source_turn_id": f"turn-{index}",
                        "source_field": "transcript",
                        "excerpt": f"I lived in {city}.",
                    }
                ],
                "confidence": 0.8,
                "importance": 0.6,
            }
        )
    return json.dumps({"candidates": candidates})


def _evidence(tmp_path: Path) -> PersistedSessionEvidence:
    return PersistedSessionEvidence(
        session=SessionArtifact(
            session_id="session-1",
            started_at=NOW,
            ended_at=NOW,
            turn_ids=["turn-1", "turn-2"],
            memory_curation_candidate=True,
            memory_curation_authorized_at=NOW,
            memory_curation_policy_revision=2,
        ),
        turns=(
            TurnArtifact(
                turn_id="turn-1",
                session_id="session-1",
                input_modality="text",
                final_state="IDLE",
                transcript="I lived in Chicago.",
            ),
            TurnArtifact(
                turn_id="turn-2",
                session_id="session-1",
                input_modality="text",
                final_state="IDLE",
                transcript="I lived in Madison.",
            ),
        ),
        artifact_path=tmp_path / "session.json",
    )


def test_partial_commit_retry_is_resumable_without_duplicate_side_effects(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    base_policy = ReviewOnlyCurationPolicy(memory)

    class FailSecondOnce:
        def __init__(self) -> None:
            self.calls = 0
            self.failed = False

        def reconcile(self, **kwargs):
            self.calls += 1
            if self.calls == 2 and not self.failed:
                self.failed = True
                raise RuntimeError("simulated crash")
            return base_policy.reconcile(**kwargs)

    policy = FailSecondOnce()
    processor = ReviewOnlyMemoryCurationProcessor(
        MemoryCandidateExtractor(FakeLLM(_output())),
        policy,  # type: ignore[arg-type]
    )

    first = processor(_evidence(tmp_path))
    facts_after_crash = memory.list_facts().value
    second = processor(_evidence(tmp_path))
    facts_after_retry = memory.list_facts().value

    assert first.success is False
    assert first.pending_review_created == 1
    assert facts_after_crash is not None and len(facts_after_crash) == 1
    assert second.success is True
    assert second.pending_review_created == 1
    assert second.duplicate_noops == 1
    assert facts_after_retry is not None and len(facts_after_retry) == 2
    for fact in facts_after_retry:
        detail = memory.read_fact(fact.fact_id).value
        assert detail is not None
        assert fact.reinforcement_count == 1
        assert fact.revision == 1
        assert len(detail.evidence) == 1
        assert len(detail.events) == 1
