"""Production composition of extraction and review-only reconciliation."""

from __future__ import annotations

from backend.app.cognition.memory_extraction import MemoryCandidateExtractor
from backend.app.memory.curation_contract import (
    ProposalContractError,
    build_provisional_candidates,
)
from backend.app.memory.curation_reconciliation import ReviewOnlyCurationPolicy
from backend.app.services.memory_curation_service import (
    CurationProcessorResult,
    PersistedSessionEvidence,
)


class ReviewOnlyMemoryCurationProcessor:
    def __init__(
        self,
        extractor: MemoryCandidateExtractor,
        policy: ReviewOnlyCurationPolicy,
    ) -> None:
        self._extractor = extractor
        self._policy = policy

    def __call__(self, evidence: PersistedSessionEvidence) -> CurationProcessorResult:
        session_id = evidence.session.session_id
        if any(turn.session_id != session_id for turn in evidence.turns):
            return _rejected_result("source_session_mismatch")
        try:
            extraction = self._extractor.extract(
                session_id=session_id,
                turns=evidence.turns,
            )
            candidates = build_provisional_candidates(
                extraction.proposals,
                extraction.persisted_turns,
            )
        except ProposalContractError:
            return _rejected_result("proposal_contract_rejected")
        except Exception:
            return CurationProcessorResult(
                success=False,
                durable=False,
                reason_code="extraction_runtime_failure",
                error_detail="memory extraction runtime failed",
                retryable=True,
                failure_count=1,
            )

        created = 0
        duplicates = 0
        rejected = 0
        owned_values = tuple(
            str(value)
            for turn in evidence.turns
            for value in (
                turn.hardware_profile_id,
                turn.active_personality_profile_id,
                *turn.capability_flags_snapshot.values(),
            )
            if isinstance(value, (str, int, float))
        )
        try:
            for proposal, candidate in zip(
                extraction.proposals,
                candidates,
                strict=True,
            ):
                counts = self._policy.reconcile(
                    proposal=proposal,
                    candidate=candidate,
                    observed_at=evidence.session.ended_at
                    or evidence.session.started_at,
                    additional_owned_values=owned_values,
                )
                created += counts.pending_review_created
                duplicates += counts.duplicate_noops
                rejected += counts.rejected
        except Exception:
            return CurationProcessorResult(
                success=False,
                durable=False,
                reason_code="review_persistence_failure",
                error_detail="review-only candidate persistence failed",
                retryable=True,
                candidates_proposed=len(extraction.proposals),
                candidates_rejected=rejected,
                pending_review_created=created,
                duplicate_noops=duplicates,
                failure_count=1,
            )

        return CurationProcessorResult(
            success=True,
            durable=True,
            reason_code="review_only_candidates_resolved",
            retryable=False,
            candidates_proposed=len(extraction.proposals),
            candidates_rejected=rejected,
            pending_review_created=created,
            duplicate_noops=duplicates,
        )


def _rejected_result(reason_code: str) -> CurationProcessorResult:
    return CurationProcessorResult(
        success=True,
        durable=True,
        reason_code=reason_code,
        retryable=False,
        candidates_rejected=1,
        failure_count=1,
    )
