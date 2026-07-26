from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any, Literal, cast

from backend.app.cache.keys import NS_RETRIEVAL, make_key
from backend.app.cache.manager import CacheManager
from backend.app.memory.episodic import EpisodicMemory
from backend.app.memory.semantic import SemanticMemory, text_to_vector

DEFAULT_RETRIEVAL_TTL = 300
RRF_K = 60
MAX_EVIDENCE_REFS = 8
_AUTHORITY_RANK = {
    "direct_user_action": 5,
    "direct_user_statement": 4,
    "assistant_inference": 3,
    "synthesized_summary": 2,
    "imported_record": 1,
    "legacy_unknown": 0,
}
_METHOD_ORDER = ("keyword", "lexical", "vector")
_EVIDENCE_REF_FIELDS = {
    "evidence_id",
    "evidence_authority",
    "source_session_id",
    "source_turn_id",
    "source_field",
    "action_id",
    "action_surface",
}


@dataclass(slots=True)
class RetrievedFact:
    turn_id: str
    session_id: str
    content: str
    source_field: str
    relevance_method: str
    source_kind: Literal["episodic", "semantic"] = "episodic"
    semantic_fact_id: str | None = None
    governed_kind: str | None = None
    evidence_authority: str | None = None
    lifecycle_state: str | None = None
    confidence: float | None = None
    importance: float | None = None
    reinforcement_count: int | None = None
    updated_at: str | None = None
    source_evidence_refs: tuple[dict[str, str], ...] = ()
    retrieval_scores: dict[str, float] | None = None

    def to_artifact_evidence(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "source_kind": self.source_kind,
            "relevance_method": self.relevance_method,
        }
        if self.source_kind == "semantic":
            record["semantic_fact_id"] = self.semantic_fact_id
            record["governed_kind"] = self.governed_kind
            record["evidence_authority"] = self.evidence_authority
            record["lifecycle_state"] = self.lifecycle_state
            record["source_evidence_refs"] = [
                dict(ref) for ref in self.source_evidence_refs[:MAX_EVIDENCE_REFS]
            ]
        else:
            record.update(
                {
                    "session_id": self.session_id,
                    "turn_id": self.turn_id,
                    "source_field": self.source_field,
                }
            )
        return record


def _optional_score(value: object) -> float | None:
    if value is None:
        return None
    score = float(value)
    if not math.isfinite(score):
        raise ValueError("cached retrieval score must be finite")
    return score


def _stable_identity(fact: RetrievedFact) -> tuple[str, ...]:
    if fact.source_kind == "semantic":
        return ("semantic", fact.semantic_fact_id or "")
    return ("episodic", fact.session_id, fact.turn_id, fact.source_field)


def _authority_rank(fact: RetrievedFact) -> int:
    authority = fact.evidence_authority
    if fact.source_kind == "episodic":
        authority = (
            "direct_user_statement"
            if fact.source_field == "transcript"
            else "assistant_inference"
        )
    return _AUTHORITY_RANK.get(authority or "", -1)


def _timestamp_rank(value: str | None) -> float:
    if value is None:
        return float("-inf")
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return float("-inf")


def _tie_break_key(
    identity: tuple[str, ...],
    fact: RetrievedFact,
    rrf_score: float,
) -> tuple[Any, ...]:
    return (
        -rrf_score,
        -_authority_rank(fact),
        -(fact.confidence if fact.confidence is not None else -1.0),
        -(fact.importance if fact.importance is not None else -1.0),
        -(fact.reinforcement_count if fact.reinforcement_count is not None else 0),
        -_timestamp_rank(fact.updated_at),
        identity,
    )


class RetrievalManager:
    def _cache_key(
        self,
        query: str | None,
        n: int,
        has_episodic: bool = False,
        has_semantic: bool = False,
        semantic_revision: int | None = None,
        episodic_revision: str | None = None,
    ) -> str:
        # Backend availability is part of the cached result's identity: a result
        # computed with a backend absent must not be served once it is back.
        backends = f"e{int(has_episodic)}s{int(has_semantic)}"
        episodic_suffix = f"e{episodic_revision}" if has_episodic else ""
        if query is None:
            return make_key(NS_RETRIEVAL, "recency", backends, episodic_suffix, str(n))
        query_hash = hashlib.md5(query.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
        suffix = "hybrid" if has_semantic else "keyword"
        revision = f"r{semantic_revision}" if has_semantic else ""
        return make_key(
            NS_RETRIEVAL,
            suffix,
            backends,
            revision,
            episodic_suffix,
            query_hash,
            str(n),
        )

    def _facts_from_cache_value(self, payload: str) -> list[RetrievedFact]:
        raw = json.loads(payload)
        if not isinstance(raw, list):
            raise ValueError("cached retrieval payload must be a list")
        facts: list[RetrievedFact] = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("cached retrieval item must be an object")
            source_kind = str(item.get("source_kind", "episodic"))
            if source_kind not in {"episodic", "semantic"}:
                raise ValueError("cached retrieval source kind is invalid")
            semantic_fact_id = item.get("semantic_fact_id")
            if source_kind == "semantic" and (
                not isinstance(semantic_fact_id, str) or not semantic_fact_id
            ):
                raise ValueError("cached semantic retrieval fact ID is invalid")
            refs_raw = item.get("source_evidence_refs", ())
            if not isinstance(refs_raw, (list, tuple)) or len(refs_raw) > MAX_EVIDENCE_REFS:
                raise ValueError("cached retrieval evidence references are invalid")
            refs: list[dict[str, str]] = []
            for ref in refs_raw:
                if (
                    not isinstance(ref, dict)
                    or not set(ref) <= _EVIDENCE_REF_FIELDS
                    or not all(
                        isinstance(key, str)
                        and isinstance(value, str)
                        and len(value) <= 1_024
                        for key, value in ref.items()
                    )
                ):
                    raise ValueError("cached retrieval evidence reference is invalid")
                refs.append(dict(ref))
            scores_raw = item.get("retrieval_scores")
            scores: dict[str, float] | None = None
            if scores_raw is not None:
                if not isinstance(scores_raw, dict):
                    raise ValueError("cached retrieval scores must be an object")
                scores = {}
                for name, value in scores_raw.items():
                    parsed_score = _optional_score(value)
                    if parsed_score is None:
                        raise ValueError("cached retrieval scores cannot be null")
                    scores[str(name)] = parsed_score
            facts.append(
                RetrievedFact(
                    turn_id=str(item["turn_id"]),
                    session_id=str(item["session_id"]),
                    content=str(item["content"]),
                    source_field=str(item["source_field"]),
                    relevance_method=str(item["relevance_method"]),
                    source_kind=cast(Literal["episodic", "semantic"], source_kind),
                    semantic_fact_id=(
                        None
                        if semantic_fact_id is None
                        else str(semantic_fact_id)
                    ),
                    governed_kind=(
                        None if item.get("governed_kind") is None else str(item["governed_kind"])
                    ),
                    evidence_authority=(
                        None
                        if item.get("evidence_authority") is None
                        else str(item["evidence_authority"])
                    ),
                    lifecycle_state=(
                        None
                        if item.get("lifecycle_state") is None
                        else str(item["lifecycle_state"])
                    ),
                    confidence=_optional_score(item.get("confidence")),
                    importance=_optional_score(item.get("importance")),
                    reinforcement_count=(
                        None
                        if item.get("reinforcement_count") is None
                        else int(item["reinforcement_count"])
                    ),
                    updated_at=(
                        None if item.get("updated_at") is None else str(item["updated_at"])
                    ),
                    source_evidence_refs=tuple(refs),
                    retrieval_scores=scores,
                )
            )
        return facts

    def _facts_to_cache_value(self, facts: list[RetrievedFact]) -> str:
        return json.dumps([asdict(fact) for fact in facts], sort_keys=True)

    def retrieve(
        self,
        query: str | None,
        n: int = 3,
        cache_manager: CacheManager | None = None,
        episodic: EpisodicMemory | None = None,
        semantic: SemanticMemory | None = None,
    ) -> list[RetrievedFact]:
        if episodic is None and semantic is None:
            return []

        semantic_revision: int | None = None
        semantic_cache_safe = True
        episodic_revision: str | None = None
        episodic_cache_safe = True
        if query is not None and semantic is not None:
            try:
                revision_result = semantic.read_content_revision()
                semantic_revision = (
                    revision_result.value if revision_result.succeeded else None
                )
            except Exception:
                semantic_revision = None
            semantic_cache_safe = semantic_revision is not None
        if episodic is not None:
            try:
                episodic_revision = episodic.read_content_revision()
            except Exception:
                episodic_revision = None
            episodic_cache_safe = episodic_revision is not None
        key = self._cache_key(
            query=query,
            n=n,
            has_episodic=(episodic is not None),
            has_semantic=(semantic is not None),
            semantic_revision=semantic_revision,
            episodic_revision=episodic_revision,
        )
        can_use_cache = False
        if cache_manager is not None:
            try:
                can_use_cache = (
                    semantic_cache_safe
                    and episodic_cache_safe
                    and cache_manager.is_available()
                )
            except Exception:
                can_use_cache = False

        if can_use_cache and cache_manager is not None:
            try:
                cached = cache_manager.get(key)
            except Exception:
                cached = None
            if cached is not None:
                try:
                    return self._facts_from_cache_value(cached)
                except Exception:
                    pass

        # Perform retrieval
        facts: list[RetrievedFact] = []

        if query is None:
            # Recency-only retrieval (episodic only)
            if episodic is not None:
                entries = episodic.retrieve_recent(n=n)
                for entry in entries:
                    if entry.response_text and entry.response_text.strip():
                        facts.append(
                            RetrievedFact(
                                turn_id=entry.turn_id,
                                session_id=entry.session_id,
                                content=entry.response_text,
                                source_field="response_text",
                                relevance_method="recency",
                                source_kind="episodic",
                            )
                        )
                    elif entry.transcript and entry.transcript.strip():
                        facts.append(
                            RetrievedFact(
                                turn_id=entry.turn_id,
                                session_id=entry.session_id,
                                content=entry.transcript,
                                source_field="transcript",
                                relevance_method="recency",
                                source_kind="episodic",
                            )
                        )
        else:
            # Query-based search (hybrid retrieval if both exist)
            episodic_candidates: list[RetrievedFact] = []
            if episodic is not None:
                entries = episodic.retrieve_by_keyword(query, n=n)
                for entry in entries:
                    if entry.response_text and entry.response_text.strip():
                        episodic_candidates.append(
                            RetrievedFact(
                                turn_id=entry.turn_id,
                                session_id=entry.session_id,
                                content=entry.response_text,
                                source_field="response_text",
                                relevance_method="keyword",
                                source_kind="episodic",
                            )
                        )
                    elif entry.transcript and entry.transcript.strip():
                        episodic_candidates.append(
                            RetrievedFact(
                                turn_id=entry.turn_id,
                                session_id=entry.session_id,
                                content=entry.transcript,
                                source_field="transcript",
                                relevance_method="keyword",
                                source_kind="episodic",
                            )
                        )

            semantic_lexical_candidates: list[RetrievedFact] = []
            semantic_vector_candidates: list[RetrievedFact] = []
            if semantic is not None:
                # Lexical
                lex_entries = semantic.search_lexical(query, n=n)
                for entry in lex_entries:
                    semantic_lexical_candidates.append(
                        RetrievedFact(
                            turn_id=entry.source_turn_id or "",
                            session_id=entry.source_session_id or "",
                            content=entry.text,
                            source_field=entry.source_field or "text",
                            relevance_method="lexical",
                            source_kind="semantic",
                            semantic_fact_id=entry.fact_id,
                            governed_kind=entry.kind,
                            evidence_authority=entry.evidence_authority,
                            lifecycle_state=entry.state,
                            confidence=entry.confidence,
                            importance=entry.importance,
                            reinforcement_count=entry.reinforcement_count,
                            updated_at=entry.updated_at,
                            source_evidence_refs=entry.evidence_refs,
                            retrieval_scores={},
                        )
                    )
                # Vector
                q_vec = text_to_vector(query)
                vec_results = semantic.search_vector(q_vec, n=n)
                for entry, vector_score in vec_results:
                    semantic_vector_candidates.append(
                        RetrievedFact(
                            turn_id=entry.source_turn_id or "",
                            session_id=entry.source_session_id or "",
                            content=entry.text,
                            source_field=entry.source_field or "text",
                            relevance_method="vector",
                            source_kind="semantic",
                            semantic_fact_id=entry.fact_id,
                            governed_kind=entry.kind,
                            evidence_authority=entry.evidence_authority,
                            lifecycle_state=entry.state,
                            confidence=entry.confidence,
                            importance=entry.importance,
                            reinforcement_count=entry.reinforcement_count,
                            updated_at=entry.updated_at,
                            source_evidence_refs=entry.evidence_refs,
                            retrieval_scores={"vector_similarity": vector_score},
                        )
                    )

            if semantic is None:
                # Standard episodic-only behavior
                facts = episodic_candidates[:n]
            else:
                scores: dict[tuple[str, ...], float] = {}
                fact_map: dict[tuple[str, ...], RetrievedFact] = {}
                methods: dict[tuple[str, ...], set[str]] = {}
                score_metadata: dict[tuple[str, ...], dict[str, float]] = {}
                lists = [
                    ("keyword", episodic_candidates),
                    ("lexical", semantic_lexical_candidates),
                    ("vector", semantic_vector_candidates),
                ]

                for method, lst in lists:
                    for idx, fact in enumerate(lst):
                        identity = _stable_identity(fact)
                        rank = idx + 1
                        contribution = 1.0 / (RRF_K + rank)
                        scores[identity] = scores.get(identity, 0.0) + contribution
                        fact_map.setdefault(identity, fact)
                        methods.setdefault(identity, set()).add(method)
                        metadata = score_metadata.setdefault(
                            identity,
                            dict(fact.retrieval_scores or {}),
                        )
                        metadata[f"{method}_rank"] = float(rank)
                        metadata[f"{method}_rrf"] = contribution

                ordered = sorted(
                    scores,
                    key=lambda identity: _tie_break_key(
                        identity,
                        fact_map[identity],
                        scores[identity],
                    ),
                )
                for identity in ordered[:n]:
                    method = "+".join(
                        item for item in _METHOD_ORDER if item in methods[identity]
                    )
                    metadata = score_metadata[identity]
                    metadata["rrf_score"] = scores[identity]
                    facts.append(
                        replace(
                            fact_map[identity],
                            relevance_method=method,
                            retrieval_scores=metadata,
                        )
                    )

        if can_use_cache and cache_manager is not None:
            try:
                cache_manager.set(key, self._facts_to_cache_value(facts), ttl=DEFAULT_RETRIEVAL_TTL)
            except Exception:
                pass
        return facts
