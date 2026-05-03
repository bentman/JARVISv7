from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from dataclasses import dataclass

from backend.app.cache.keys import NS_RETRIEVAL, make_key
from backend.app.cache.manager import CacheManager
from backend.app.memory.episodic import EpisodicMemory

DEFAULT_RETRIEVAL_TTL = 300


@dataclass(slots=True)
class RetrievedFact:
    turn_id: str
    session_id: str
    content: str
    source_field: str
    relevance_method: str


class RetrievalManager:
    def _cache_key(self, query: str | None, n: int) -> str:
        if query is None:
            return make_key(NS_RETRIEVAL, "recency", str(n))
        query_hash = hashlib.md5(query.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
        return make_key(NS_RETRIEVAL, "keyword", query_hash, str(n))

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
    ) -> list[RetrievedFact]:
        if episodic is None:
            return []

        key = self._cache_key(query=query, n=n)
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

        entries = episodic.retrieve_by_keyword(query, n=n) if query is not None else episodic.retrieve_recent(n=n)
        facts: list[RetrievedFact] = []
        for entry in entries:
            if entry.response_text and entry.response_text.strip():
                facts.append(
                    RetrievedFact(
                        turn_id=entry.turn_id,
                        session_id=entry.session_id,
                        content=entry.response_text,
                        source_field="response_text",
                        relevance_method="keyword" if query is not None else "recency",
                    )
                )
            elif entry.transcript and entry.transcript.strip():
                facts.append(
                    RetrievedFact(
                        turn_id=entry.turn_id,
                        session_id=entry.session_id,
                        content=entry.transcript,
                        source_field="transcript",
                        relevance_method="keyword" if query is not None else "recency",
                    )
                )
        if can_use_cache and cache_manager is not None:
            try:
                cache_manager.set(key, self._facts_to_cache_value(facts), ttl=DEFAULT_RETRIEVAL_TTL)
            except Exception:
                pass
        return facts
