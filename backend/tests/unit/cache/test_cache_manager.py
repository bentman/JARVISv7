from __future__ import annotations

from backend.app.cache.keys import make_key
from backend.app.cache.manager import CacheManager


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int):
        _ = ex
        self.store[key] = value
        return True

    def delete(self, key: str):
        return 1 if self.store.pop(key, None) is not None else 0

    def ping(self):
        return True


def test_make_key_joins_parts_with_colon() -> None:
    assert make_key("retrieval", "user", "abc") == "retrieval:user:abc"


def test_get_returns_none_when_redis_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.cache.manager.get_client", lambda: None)
    assert CacheManager().get("k") is None


def test_set_returns_false_when_redis_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.cache.manager.get_client", lambda: None)
    assert CacheManager().set("k", "v", 30) is False


def test_delete_returns_false_when_redis_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.cache.manager.get_client", lambda: None)
    assert CacheManager().delete("k") is False


def test_is_available_false_when_client_none(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.cache.manager.get_client", lambda: None)
    assert CacheManager().is_available() is False


def test_get_returns_value_when_redis_available(monkeypatch) -> None:
    fake = _FakeRedis()
    fake.store["k"] = "v"
    monkeypatch.setattr("backend.app.cache.manager.get_client", lambda: fake)
    assert CacheManager().get("k") == "v"


def test_set_stores_value_with_ttl(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr("backend.app.cache.manager.get_client", lambda: fake)
    assert CacheManager().set("k", "v", 60) is True
    assert fake.store["k"] == "v"
