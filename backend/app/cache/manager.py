from __future__ import annotations

from backend.app.cache.redis_client import get_client


class CacheManager:
    def get(self, key: str) -> str | None:
        client = get_client()
        if client is None:
            return None
        try:
            value = client.get(key)
        except Exception:
            return None
        return value if isinstance(value, str) else None

    def set(self, key: str, value: str, ttl: int) -> bool:
        client = get_client()
        if client is None:
            return False
        try:
            return bool(client.set(key, value, ex=ttl))
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        client = get_client()
        if client is None:
            return False
        try:
            return bool(client.delete(key))
        except Exception:
            return False

    def is_available(self) -> bool:
        client = get_client()
        if client is None:
            return False
        try:
            return bool(client.ping())
        except Exception:
            return False
