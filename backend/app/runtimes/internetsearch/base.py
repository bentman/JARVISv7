from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str


class SearchBase(ABC):
    @abstractmethod
    def runtime_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        raise NotImplementedError


class NullSearchRuntime(SearchBase):
    def __init__(self, reason: str = "search unavailable") -> None:
        self.reason = reason

    def runtime_name(self) -> str:
        return "null"

    def is_available(self) -> bool:
        return False

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return []
