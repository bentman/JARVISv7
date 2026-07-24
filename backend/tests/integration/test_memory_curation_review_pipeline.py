from __future__ import annotations

import json
from pathlib import Path

from backend.app.artifacts.session_artifact import SessionArtifact
from backend.app.artifacts.storage import write_session_artifact, write_turn_artifact
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.cognition.memory_extraction import MemoryCandidateExtractor
from backend.app.cognition.prompt_envelope import PromptEnvelope
from backend.app.memory.curation import CurationJobStatus, LifecycleState, OperationStatus
from backend.app.memory.curation_contract import GovernedMemoryKind
from backend.app.memory.curation_reconciliation import ReviewOnlyCurationPolicy
from backend.app.memory.semantic import SemanticMemory
from backend.app.runtimes.llm.base import LLMBase
from backend.app.services.llm_execution_coordinator import LLMExecutionCoordinator
from backend.app.services.memory_curation_processor import (
    ReviewOnlyMemoryCurationProcessor,
)
from backend.app.services.memory_curation_service import MemoryCurationService

NOW = "2026-07-24T12:00:00+00:00"


class DeterministicExtractionLLM(LLMBase):
    def generate(self, prompt: str, **kwargs: object) -> str:
        raise AssertionError("pipeline must use the envelope path")

    def generate_envelope(self, envelope: PromptEnvelope, **kwargs: object) -> str:
        return json.dumps(
            {
                "candidates": [
                    {
                        "text": "The user lives in Chicago.",
                        "kind": "personal_fact",
                        "claim_key": "model.home_city",
                        "value": "Chicago",
                        "relation": "assertion",
                        "evidence_refs": [
                            {
                                "source_turn_id": "turn-1",
                                "source_field": "transcript",
                                "excerpt": "I live in Chicago.",
                            }
                        ],
                        "confidence": 0.9,
                        "importance": 0.7,
                    }
                ]
            }
        )

    def is_available(self) -> bool:
        return True

    def runtime_name(self) -> str:
        return "deterministic-fake"


def test_persisted_job_creates_one_review_only_candidate(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    turns = tmp_path / "turns"
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    assert memory.update_policy(
        automatic_curation_enabled=True,
        expected_revision=1,
    ).status is OperationStatus.SUCCESS
    turn = TurnArtifact(
        turn_id="turn-1",
        session_id="session-1",
        input_modality="text",
        final_state="IDLE",
        transcript="I live in Chicago.",
        response_text="Thanks.",
    )
    write_turn_artifact(turn, turns)
    artifact_path = write_session_artifact(
        SessionArtifact(
            session_id="session-1",
            started_at=NOW,
            ended_at=NOW,
            turn_ids=[turn.turn_id],
            final_state="IDLE",
            memory_curation_candidate=True,
            memory_curation_authorized_at=NOW,
            memory_curation_policy_revision=2,
        ),
        sessions,
    )
    llm = DeterministicExtractionLLM()
    service = MemoryCurationService(
        semantic_memory=memory,
        sessions_root=sessions,
        turns_root=turns,
        coordinator=LLMExecutionCoordinator(),
        session_is_active=lambda: False,
        processor=ReviewOnlyMemoryCurationProcessor(
            MemoryCandidateExtractor(llm),
            ReviewOnlyCurationPolicy(memory),
        ),
        runtime_status=lambda: {
            "ready": True,
            "runtime_name": llm.runtime_name(),
            "model_id": "deterministic-fake",
            "serve_profile_id": "test",
            "accelerator": "cpu",
        },
        boot_id="integration-boot",
    )
    assert service.enqueue_closed_session(
        session_id="session-1",
        artifact_path=artifact_path,
        policy_revision=2,
        authorized_at=NOW,
    ).status is OperationStatus.SUCCESS

    drain = service.drain(timeout=1)
    service.stop()
    job = memory.read_curation_job("session-1").value
    facts = memory.list_facts().value

    assert drain.outcome == "completed"
    assert job is not None and job.status is CurationJobStatus.SUCCEEDED
    assert facts is not None and len(facts) == 1
    fact = facts[0]
    assert fact.kind == GovernedMemoryKind.UNCLASSIFIED.value
    assert fact.state == LifecycleState.PENDING_REVIEW.value
    assert fact.value_text is None
    detail = memory.read_fact(fact.fact_id).value
    assert detail is not None
    assert len(detail.evidence) == 1
    assert detail.evidence[0].source_turn_id == "turn-1"
    assert len(detail.events) == 1
    assert detail.events[0].event_type == "created"
