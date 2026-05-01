from __future__ import annotations

NS_RETRIEVAL = "retrieval"
NS_SESSION = "session"
NS_SEARCH = "search"


def make_key(namespace: str, *parts: str) -> str:
    tokens = [namespace, *parts]
    return ":".join(token for token in tokens if token)
