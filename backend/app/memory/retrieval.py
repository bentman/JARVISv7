from __future__ import annotations

from dataclasses import dataclass

from backend.app.memory.episodic import EpisodicMemory


@dataclass(slots=True)
class RetrievedFact:
    turn_id: str
    session_id: str
    content: str
    source_field: str
    relevance_method: str


class RetrievalManager:
    def retrieve(
        self,
        query: str | None,
        n: int = 3,
        cache_manager: object | None = None,
        episodic: EpisodicMemory | None = None,
    ) -> list[RetrievedFact]:
        _ = cache_manager
        if episodic is None:
            return []

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
        return facts
