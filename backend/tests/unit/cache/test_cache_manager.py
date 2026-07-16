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


def _reset_redis_client_state(monkeypatch) -> None:
    from backend.app.cache import redis_client

    monkeypatch.setattr(redis_client, "_CLIENT", None)
    monkeypatch.setattr(redis_client, "_NEXT_RETRY_AT", None)


def test_get_client_retries_after_cooldown_when_startup_connect_failed(monkeypatch) -> None:
    from backend.app.cache import redis_client

    _reset_redis_client_state(monkeypatch)
    clock = {"now": 1000.0}
    monkeypatch.setattr(redis_client.time, "monotonic", lambda: clock["now"])

    attempts = {"count": 0}

    class _DownThenUpRedis(_FakeRedis):
        def __init__(self, **kwargs) -> None:
            super().__init__()
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ConnectionError("redis down at startup")

    monkeypatch.setattr(redis_client.redis, "Redis", _DownThenUpRedis)

    # Startup failure disables the cache.
    assert redis_client.get_client() is None
    assert attempts["count"] == 1

    # Within the cooldown window: no reconnect attempt.
    clock["now"] += redis_client._RETRY_COOLDOWN_SECONDS / 2
    assert redis_client.get_client() is None
    assert attempts["count"] == 1

    # After the cooldown: exactly one bounded retry, which succeeds and latches.
    clock["now"] += redis_client._RETRY_COOLDOWN_SECONDS
    client = redis_client.get_client()
    assert client is not None
    assert attempts["count"] == 2

    # Established client is reused without further connection attempts.
    assert redis_client.get_client() is client
    assert attempts["count"] == 2


def test_get_client_does_not_hammer_redis_while_it_stays_down(monkeypatch) -> None:
    from backend.app.cache import redis_client

    _reset_redis_client_state(monkeypatch)
    clock = {"now": 5000.0}
    monkeypatch.setattr(redis_client.time, "monotonic", lambda: clock["now"])

    attempts = {"count": 0}

    class _AlwaysDownRedis:
        def __init__(self, **kwargs) -> None:
            attempts["count"] += 1
            raise ConnectionError("redis still down")

    monkeypatch.setattr(redis_client.redis, "Redis", _AlwaysDownRedis)

    for _ in range(10):
        assert redis_client.get_client() is None
    assert attempts["count"] == 1

    clock["now"] += redis_client._RETRY_COOLDOWN_SECONDS + 1
    assert redis_client.get_client() is None
    assert attempts["count"] == 2
