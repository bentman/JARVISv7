from __future__ import annotations

from dataclasses import dataclass

DEFAULT_RETRIEVAL_TTL = 300
DEFAULT_SESSION_TTL = 3600
DEFAULT_SEARCH_TTL = 60


@dataclass(frozen=True, slots=True)
class CachePolicy:
    ttl_seconds: int
