from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from backend.app.cache import redis_client


def _fake_settings() -> SimpleNamespace:
    return SimpleNamespace(
        redis_host="127.0.0.1",
        redis_port=6379,
        redis_db=0,
        redis_max_connections=4,
        redis_socket_timeout=1.0,
    )


def _reset_module_state(monkeypatch) -> None:
    monkeypatch.setattr(redis_client, "_CLIENT", None)
    monkeypatch.setattr(redis_client, "_INITIALIZED", False)
    monkeypatch.setattr(redis_client, "_LAST_FAILURE_MONOTONIC", None)
    monkeypatch.setattr(redis_client, "load_settings", _fake_settings)


def test_failed_init_does_not_retry_within_cooldown(monkeypatch) -> None:
    _reset_module_state(monkeypatch)
    monkeypatch.setattr(redis_client, "_RETRY_INTERVAL_S", 60.0)
    attempts = {"count": 0}

    class _DownRedis:
        def __init__(self, **kwargs) -> None:
            _ = kwargs
            attempts["count"] += 1

        def ping(self) -> bool:
            raise ConnectionError("redis down")

    monkeypatch.setattr(redis_client.redis, "Redis", _DownRedis)

    assert redis_client.get_client() is None
    assert redis_client.get_client() is None
    assert attempts["count"] == 1


def test_failed_init_retries_after_cooldown_and_recovers(monkeypatch) -> None:
    _reset_module_state(monkeypatch)
    monkeypatch.setattr(redis_client, "_RETRY_INTERVAL_S", 0.0)

    class _DownRedis:
        def __init__(self, **kwargs) -> None:
            _ = kwargs

        def ping(self) -> bool:
            raise ConnectionError("redis down")

    class _UpRedis:
        def __init__(self, **kwargs) -> None:
            _ = kwargs

        def ping(self) -> bool:
            return True

    monkeypatch.setattr(redis_client.redis, "Redis", _DownRedis)
    assert redis_client.get_client() is None

    # Cooldown elapsed (interval 0): next call must re-attempt and succeed.
    monkeypatch.setattr(redis_client.redis, "Redis", _UpRedis)
    client = redis_client.get_client()
    assert isinstance(client, _UpRedis)

    # Subsequent calls reuse the cached client.
    assert redis_client.get_client() is client


def test_init_is_thread_safe_and_connects_once(monkeypatch) -> None:
    _reset_module_state(monkeypatch)
    attempts = {"count": 0}

    class _SlowRedis:
        def __init__(self, **kwargs) -> None:
            _ = kwargs
            attempts["count"] += 1
            time.sleep(0.05)

        def ping(self) -> bool:
            return True

    monkeypatch.setattr(redis_client.redis, "Redis", _SlowRedis)

    clients: list[object] = []
    threads = [
        threading.Thread(target=lambda: clients.append(redis_client.get_client()))
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert attempts["count"] == 1
    assert len(clients) == 8
    assert len({id(client) for client in clients}) == 1
