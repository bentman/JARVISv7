from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from backend.app.cache.keys import NS_RETRIEVAL, make_key
from backend.app.cache.manager import CacheManager
from backend.app.memory.episodic import EpisodicMemory
from backend.app.memory.semantic import SemanticMemory, text_to_vector

DEFAULT_RETRIEVAL_TTL = 300


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


@dataclass(slots=True)
class RetrievedFact:
    turn_id: str
    session_id: str
    content: str
    source_field: str
    relevance_method: str


class RetrievalManager:
    def _cache_key(self, query: str | None, n: int, has_semantic: bool = False) -> str:
        if query is None:
            return make_key(NS_RETRIEVAL, "recency", str(n))
        query_hash = hashlib.md5(query.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
        suffix = "hybrid" if has_semantic else "keyword"
        return make_key(NS_RETRIEVAL, suffix, query_hash, str(n))

    def _facts_from_cache_value(self, payload: str) -> list[RetrievedFact]:
        raw = json.loads(payload)
        if not isinstance(raw, list):
            raise ValueError("cached retrieval payload must be a list")
        facts: list[RetrievedFact] = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("cached retrieval item must be an object")
            facts.append(
                RetrievedFact(
                    turn_id=str(item["turn_id"]),
                    session_id=str(item["session_id"]),
                    content=str(item["content"]),
                    source_field=str(item["source_field"]),
                    relevance_method=str(item["relevance_method"]),
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

        key = self._cache_key(query=query, n=n, has_semantic=(semantic is not None))
        can_use_cache = False
        if cache_manager is not None:
            try:
                can_use_cache = cache_manager.is_available()
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
                        )
                    )
                # Vector
                q_vec = text_to_vector(query)
                vec_results = semantic.search_vector(q_vec, n=n)
                for entry, _score in vec_results:
                    semantic_vector_candidates.append(
                        RetrievedFact(
                            turn_id=entry.source_turn_id or "",
                            session_id=entry.source_session_id or "",
                            content=entry.text,
                            source_field=entry.source_field or "text",
                            relevance_method="vector",
                        )
                    )

            if semantic is None:
                # Standard episodic-only behavior
                facts = episodic_candidates[:n]
            else:
                # Reciprocal Rank Fusion (RRF) to merge candidate lists
                # k=60 is standard
                k = 60
                scores: dict[str, float] = {}
                fact_map: dict[str, RetrievedFact] = {}
                lists = [
                    episodic_candidates,
                    semantic_lexical_candidates,
                    semantic_vector_candidates,
                ]

                for lst in lists:
                    for idx, fact in enumerate(lst):
                        norm_content = _normalize_text(fact.content)
                        rank = idx + 1
                        scores[norm_content] = scores.get(norm_content, 0.0) + (
                            1.0 / (k + rank)
                        )
                        if norm_content not in fact_map:
                            fact_map[norm_content] = fact

                sorted_norm = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
                for norm_content in sorted_norm[:n]:
                    facts.append(fact_map[norm_content])

        if can_use_cache and cache_manager is not None:
            try:
                cache_manager.set(key, self._facts_to_cache_value(facts), ttl=DEFAULT_RETRIEVAL_TTL)
            except Exception:
                pass
        return facts
