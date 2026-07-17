from __future__ import annotations

from types import SimpleNamespace

from backend.app.cache import redis_client
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


def test_redis_connection_failures_retry_at_most_once_per_cooldown(monkeypatch) -> None:
    now = [0.0]
    attempts: list[object] = []

    class UnavailableRedis:
        def ping(self) -> None:
            raise ConnectionError("redis unavailable")

    def create_redis(**kwargs):
        attempts.append(kwargs)
        return UnavailableRedis()

    monkeypatch.setattr(redis_client, "_CLIENT", None)
    monkeypatch.setattr(redis_client, "_NEXT_RETRY_AT", None)
    monkeypatch.setattr(redis_client.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(redis_client, "load_settings", _redis_settings)
    monkeypatch.setattr(redis_client.redis, "Redis", create_redis)

    assert redis_client.get_client() is None
    assert len(attempts) == 1

    now[0] = 29.999
    assert redis_client.get_client() is None
    assert len(attempts) == 1

    now[0] = 30.0
    assert redis_client.get_client() is None
    assert len(attempts) == 2

    now[0] = 59.999
    assert redis_client.get_client() is None
    assert len(attempts) == 2

    now[0] = 60.0
    assert redis_client.get_client() is None
    assert len(attempts) == 3


def test_redis_retry_success_caches_client_and_clears_cooldown(monkeypatch) -> None:
    now = [0.0]
    attempts: list[object] = []

    class FakeRedis:
        def __init__(self, *, available: bool) -> None:
            self.available = available

        def ping(self) -> bool:
            if not self.available:
                raise ConnectionError("redis unavailable")
            return True

    def create_redis(**kwargs):
        client = FakeRedis(available=len(attempts) > 0)
        attempts.append(kwargs)
        return client

    monkeypatch.setattr(redis_client, "_CLIENT", None)
    monkeypatch.setattr(redis_client, "_NEXT_RETRY_AT", None)
    monkeypatch.setattr(redis_client.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(redis_client, "load_settings", _redis_settings)
    monkeypatch.setattr(redis_client.redis, "Redis", create_redis)

    assert redis_client.get_client() is None
    assert len(attempts) == 1

    now[0] = 30.0
    connected = redis_client.get_client()
    assert connected is not None
    assert len(attempts) == 2
    assert redis_client._NEXT_RETRY_AT is None

    now[0] = 300.0
    assert redis_client.get_client() is connected
    assert len(attempts) == 2


def _redis_settings():
    return SimpleNamespace(
        redis_host="127.0.0.1",
        redis_port=6379,
        redis_db=0,
        redis_max_connections=4,
        redis_socket_timeout=0.5,
    )
