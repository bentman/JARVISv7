from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.api.dependencies import get_memory_service
from backend.app.api.routes.memory import router
from backend.app.memory.curation import (
    EvidenceInput,
    GovernedEvidenceAuthority,
    GovernedFactInput,
    LifecycleState,
)
from backend.app.memory.curation_contract import (
    GovernedClaimIdentity,
    GovernedMemoryKind,
)
from backend.app.memory.semantic import SemanticMemory
from backend.app.services.llm_execution_coordinator import LLMExecutionCoordinator
from backend.app.services.memory_curation_service import MemoryCurationService
from backend.app.services.memory_service import MemoryService
from fastapi import FastAPI
from fastapi.testclient import TestClient

NOW = "2026-07-25T12:00:00+00:00"


def _fact(memory: SemanticMemory, state: LifecycleState = LifecycleState.PENDING_REVIEW):
    result = memory.create_governed_fact(
        GovernedFactInput(
            text="The user prefers concise answers.",
            identity=GovernedClaimIdentity(
                kind=GovernedMemoryKind.USER_PREFERENCE,
                claim_key="preference.response_style",
            ),
            value_text="concise",
            evidence_authority=GovernedEvidenceAuthority.DIRECT_USER_STATEMENT,
            state=state,
            confidence=0.9,
            importance=0.8,
            evidence=(
                EvidenceInput(
                    authority=GovernedEvidenceAuthority.DIRECT_USER_STATEMENT,
                    observed_at=NOW,
                    source_session_id="session-1",
                    source_turn_id="turn-1",
                    source_field="transcript",
                    metadata={"raw_output": "hidden"},
                ),
            ),
            vector=(0.1, 0.2),
            vectorizer_id="hidden-vectorizer",
            metadata={"database_path": "C:/secret/memory.sqlite"},
        )
    )
    assert result.value is not None
    return result.value


def _client(service: object) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_memory_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def test_memory_routes_are_typed_bounded_and_omit_internal_fields(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    fact = _fact(memory)
    client = _client(MemoryService(semantic_memory=memory, curation_service=None))
    revision_before = memory.read_content_revision().value

    listing = client.get("/memory")
    detail = client.get(f"/memory/{fact.fact_id}?evidence_limit=1&events_limit=1")

    assert listing.status_code == 200
    assert listing.json()["returned_count"] == 1
    assert listing.json()["records"][0]["lifecycle_state"] == "pending_review"
    assert detail.status_code == 200
    assert detail.json()["evidence_limit"] == 1
    assert detail.json()["events_limit"] == 1
    serialized = listing.text + detail.text
    for prohibited in (
        "vector",
        "hidden-vectorizer",
        "database_path",
        "C:/secret",
        "raw_output",
        "metadata",
    ):
        assert prohibited not in serialized
    assert memory.read_content_revision().value == revision_before


def test_policy_and_record_conflicts_share_actionable_shape(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    fact = _fact(memory)
    client = _client(MemoryService(semantic_memory=memory, curation_service=None))
    initial_policy = client.get("/memory/policy").json()
    updated_policy = client.put(
        "/memory/policy",
        json={
            "automatic_curation_enabled": True,
            "expected_revision": initial_policy["revision"],
        },
    )
    assert updated_policy.status_code == 200

    stale_policy = client.put(
        "/memory/policy",
        json={
            "automatic_curation_enabled": False,
            "expected_revision": initial_policy["revision"],
        },
    )
    confirmed = client.post(
        f"/memory/{fact.fact_id}/confirm",
        json={"expected_revision": fact.revision},
    )
    stale_record = client.post(
        f"/memory/{fact.fact_id}/dispute",
        json={"expected_revision": fact.revision},
    )

    assert confirmed.status_code == 200
    assert stale_policy.status_code == 409
    assert stale_record.status_code == 409
    for response in (stale_policy, stale_record):
        assert set(response.json()["detail"]) == {
            "error",
            "message",
            "current_revision",
            "current_state",
        }
        assert response.json()["detail"]["error"] == "conflict"


def test_correction_contract_forbids_authority_and_identity_fields(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    fact = _fact(memory, LifecycleState.ACTIVE)
    client = _client(MemoryService(semantic_memory=memory, curation_service=None))

    rejected = client.post(
        f"/memory/{fact.fact_id}/correct",
        json={
            "expected_revision": fact.revision,
            "replacement_text": "The user prefers detailed answers.",
            "replacement_value": "detailed",
            "kind": "personal_fact",
            "evidence_authority": "assistant_inference",
        },
    )
    accepted = client.post(
        f"/memory/{fact.fact_id}/correct",
        json={
            "expected_revision": fact.revision,
            "replacement_text": "The user prefers detailed answers.",
            "replacement_value": "detailed",
        },
    )

    assert rejected.status_code == 422
    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["original"]["fact_id"] == fact.fact_id
    assert payload["original"]["superseded_by_fact_id"] == payload["replacement"]["fact_id"]
    assert payload["replacement"]["kind"] == fact.kind
    assert payload["replacement"]["claim_key"] == fact.claim_key


def test_delete_requires_query_revision_and_reports_narrow_forgetting_scope(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    fact = _fact(memory, LifecycleState.ACTIVE)
    client = _client(MemoryService(semantic_memory=memory, curation_service=None))

    missing = client.delete(f"/memory/{fact.fact_id}")
    forgotten = client.delete(
        f"/memory/{fact.fact_id}",
        params={"expected_revision": fact.revision, "reason": "user request"},
    )

    assert missing.status_code == 422
    assert forgotten.status_code == 200
    assert forgotten.json()["record"]["lifecycle_state"] == "forgotten"
    assert "separate evidence" in forgotten.json()["forgetting_scope"]
    assert "erased by this operation" in forgotten.json()["forgetting_scope"]


def test_curation_status_is_truthful_sanitized_and_has_no_retry_route(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    enabled = memory.update_policy(
        automatic_curation_enabled=True,
        expected_revision=1,
    )
    assert enabled.value is not None
    queued = memory.enqueue_curation_job(
        session_id="session-safe",
        artifact_ref="C:/private/session.json",
        policy_revision=enabled.value.revision,
        authorized_at=NOW,
    )
    assert queued.value is not None
    curation = MemoryCurationService(
        semantic_memory=memory,
        sessions_root=tmp_path / "sessions",
        turns_root=tmp_path / "turns",
        coordinator=LLMExecutionCoordinator(),
        session_is_active=lambda: False,
        processor=None,
        runtime_status=lambda: {
            "ready": True,
            "model_id": "secret-model",
            "runtime_name": "secret-runtime",
        },
    )
    client = _client(MemoryService(semantic_memory=memory, curation_service=curation))

    status = client.get("/memory/curation/status")
    retry = client.post("/memory/curation/retry")

    assert status.status_code == 200
    assert status.json()["automatic_curation_enabled"] is True
    assert status.json()["pending_count"] == 1
    assert status.json()["degraded"] is True
    assert retry.status_code == 404
    for prohibited in ("C:/private", "artifact", "secret-model", "secret-runtime"):
        assert prohibited not in status.text


@dataclass
class _ExplodingService:
    def read_policy(self):
        raise RuntimeError("sqlite failed at C:/private/memory.sqlite with token=secret")


def test_unexpected_failures_return_sanitized_500() -> None:
    response = _client(_ExplodingService()).get("/memory/policy")

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "error": "internal_error",
        "message": "memory operation failed",
    }
    assert "private" not in response.text
    assert "secret" not in response.text


def test_store_and_curation_unavailability_are_visible_and_sanitized(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    service = MemoryService(semantic_memory=memory, curation_service=None)
    memory._schema_ready = False
    memory.schema_error = "sqlite failed at C:/private/memory.sqlite"
    client = _client(service)

    store_response = client.get("/memory")
    curation_response = client.get("/memory/curation/status")

    assert store_response.status_code == 503
    assert store_response.json()["detail"] == {
        "error": "unavailable",
        "message": "list memory is unavailable",
    }
    assert curation_response.status_code == 503
    assert curation_response.json()["detail"] == {
        "error": "unavailable",
        "message": "memory curation is unavailable",
    }
    assert "private" not in store_response.text + curation_response.text
