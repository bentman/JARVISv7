from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from backend.app.core.settings import Settings
from backend.app.runtimes.internetsearch.base import SearchBase, SearchResponse, search_failure
from backend.app.runtimes.internetsearch.ddgs_runtime import DDGSRuntime
from backend.app.runtimes.internetsearch.page_reader import (
    PublicPageReader,
    check_cancelled,
    public_web_url,
)
from backend.app.runtimes.internetsearch.searxng_runtime import SearXNGRuntime
from backend.app.runtimes.internetsearch.tavily_runtime import TavilyRuntime
from pydantic import BaseModel, Field


class SearchSource(BaseModel):
    id: str
    title: str
    url: str
    excerpt: str
    providers: list[str]
    retrieved_at: str
    basis: Literal["search_excerpt", "page_excerpt"] = "search_excerpt"
    page_status: str | None = None
    page_duration_ms: float | None = None


class SearchAttempt(BaseModel):
    query: str
    provider: str
    status: str
    result_count: int = 0
    reason: str | None = None
    duration_ms: float = 0


class SearchEvidence(BaseModel):
    session_id: str
    turn_id: str
    mode: Literal["search", "research"] = "search"
    topic: str = ""
    queries: list[str] = Field(default_factory=list)
    attempts: list[SearchAttempt] = Field(default_factory=list)
    sources: list[SearchSource] = Field(default_factory=list)
    outcome: str = "running"
    stage: str = "planning"
    limitations: list[str] = Field(default_factory=list)
    duration_ms: float = 0
    cancel_requested: bool = False
    retrieval_ms: float = 0
    current_provider: str | None = None


class SearchOperation:
    def __init__(self, session_id: str, turn_id: str) -> None:
        self.evidence = SearchEvidence(session_id=session_id, turn_id=turn_id)
        self.cancel = threading.Event()
        self.done = threading.Event()
        self.started = time.monotonic()
        self.lock = threading.RLock()

    def check(self) -> None:
        check_cancelled(self.cancel.is_set)

    def stage(self, stage: str) -> None:
        with self.lock:
            self.check()
            self.evidence.stage = stage

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            self.evidence.cancel_requested = self.cancel.is_set()
            self.evidence.duration_ms = round((time.monotonic() - self.started) * 1000, 3)
            return self.evidence.model_dump()


class SearchService:
    def __init__(self, providers: list[SearchBase], reader: PublicPageReader | None = None) -> None:
        self.providers = tuple(providers)
        self.reader = reader or PublicPageReader()
        self._lock = threading.Lock()
        self._active: SearchOperation | None = None
        self._last_cancelled: tuple[str, str] | None = None

    @classmethod
    def configured(cls, settings: Settings) -> SearchService:
        return cls([DDGSRuntime(settings), SearXNGRuntime(settings), TavilyRuntime(settings)])

    @contextmanager
    def operation(self, session_id: str, turn_id: str) -> Iterator[SearchOperation]:
        operation = SearchOperation(session_id, turn_id)
        with self._lock:
            if self._active is not None:
                raise RuntimeError("a search turn is already active")
            self._active = operation
        try:
            yield operation
        finally:
            with self._lock:
                if operation.cancel.is_set():
                    self._last_cancelled = (session_id, turn_id)
                self._active = None
                operation.done.set()

    def snapshot(self) -> dict[str, object] | None:
        with self._lock:
            operation = self._active
        return operation.snapshot() if operation else None

    def cancel(self, session_id: str, turn_id: str) -> bool:
        with self._lock:
            operation = self._active
            if operation and (operation.evidence.session_id, operation.evidence.turn_id) == (session_id, turn_id):
                with operation.lock:
                    if operation.evidence.stage == "complete":
                        return False
                    operation.cancel.set()
                    return True
            return self._last_cancelled == (session_id, turn_id)

    def cancel_and_wait(self, timeout: float = 10.0) -> bool:
        with self._lock:
            operation = self._active
            if operation:
                with operation.lock:
                    if operation.evidence.stage != "complete":
                        operation.cancel.set()
        return operation is None or operation.done.wait(timeout)

    def retrieve(self, operation: SearchOperation, *, mode: Literal["search", "research"], topic: str, queries: list[str]) -> SearchEvidence:
        evidence = operation.evidence
        evidence.mode, evidence.topic = mode, topic
        evidence.queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:3 if mode == "research" else 1]
        for query in evidence.queries:
            operation.stage("searching")
            found = False
            for provider in self.providers:
                operation.check()
                started = time.monotonic()
                with operation.lock:
                    evidence.current_provider = provider.runtime_name()
                try:
                    response = provider.search(query, max_results=5)
                except Exception as exc:
                    response = search_failure(exc)
                usable = self._usable_response(response)
                with operation.lock:
                    evidence.attempts.append(SearchAttempt(
                        query=query, provider=provider.runtime_name(), status=usable.status,
                        reason=usable.reason, result_count=len(usable.results),
                        duration_ms=round((time.monotonic() - started) * 1000, 3),
                    ))
                    evidence.current_provider = None
                    operation.check()
                    for result in usable.results:
                        existing = next((source for source in evidence.sources if source.url == result.url), None)
                        if existing:
                            if result.source not in existing.providers:
                                existing.providers.append(result.source)
                            continue
                        evidence.sources.append(SearchSource(
                            id=f"S{len(evidence.sources) + 1}", title=result.title,
                            url=result.url, excerpt=result.snippet, providers=[result.source],
                            retrieved_at=datetime.now(UTC).isoformat(),
                        ))
                if usable.results:
                    found = True
                    break
            if not found:
                evidence.limitations.append("A planned query returned no usable evidence.")
        if mode == "research" and evidence.sources:
            operation.stage("reading")
            selected: list[SearchSource] = []
            hosts: set[str | None] = set()
            for source in evidence.sources:
                host = urlsplit(source.url).hostname
                if host not in hosts:
                    hosts.add(host)
                    selected.append(source)
            selected.extend(source for source in evidence.sources if source not in selected)
            for source in selected[:3]:
                operation.check()
                page_started = time.monotonic()
                page = self.reader.read(source.url, cancelled=operation.cancel.is_set)
                operation.check()
                source.page_status = page.status
                source.page_duration_ms = round((time.monotonic() - page_started) * 1000, 3)
                if page.status == "success" and page.text:
                    source.url = page.url
                    source.excerpt = page.text
                    source.basis = "page_excerpt"
                    source.retrieved_at = datetime.now(UTC).isoformat()
                else:
                    evidence.limitations.append(f"[{source.id}] Page unavailable; using search excerpt ({page.status}).")
        operation.check()
        unique_sources: dict[str, SearchSource] = {}
        for source in evidence.sources:
            if source.url in unique_sources:
                original = unique_sources[source.url]
                original.providers = list(dict.fromkeys([*original.providers, *source.providers]))
            else:
                unique_sources[source.url] = source
        evidence.sources = list(unique_sources.values())
        evidence.outcome = "partial" if evidence.limitations and evidence.sources else "success" if evidence.sources else "unavailable"
        operation.stage("synthesizing")
        return evidence

    @staticmethod
    def _usable_response(response: SearchResponse) -> SearchResponse:
        from dataclasses import replace

        results = []
        if response.status != "success":
            return SearchResponse(response.status, reason=response.reason)
        for result in response.results[:5]:
            try:
                url = public_web_url(result.url)
            except ValueError:
                continue
            if result.snippet.strip():
                results.append(replace(result, url=url))
        if response.status == "success" and not results:
            return SearchResponse("empty", reason="no usable public search results")
        return SearchResponse(response.status, tuple(results), response.reason)
