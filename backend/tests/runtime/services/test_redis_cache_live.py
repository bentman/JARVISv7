from __future__ import annotations

import pytest
from backend.app.cache.manager import CacheManager


@pytest.mark.live
@pytest.mark.requires_docker
@pytest.mark.requires_redis
def test_cache_roundtrip_against_running_redis() -> None:
    manager = CacheManager()
    if not manager.is_available():
        pytest.skip("Redis unavailable")
    key = "runtime:test:roundtrip"
    assert manager.set(key, "ok", 30) is True
    assert manager.get(key) == "ok"


@pytest.mark.live
@pytest.mark.requires_docker
@pytest.mark.requires_redis
def test_cache_returns_none_when_key_missing() -> None:
    manager = CacheManager()
    if not manager.is_available():
        pytest.skip("Redis unavailable")
    assert manager.get("runtime:test:missing") is None


@pytest.mark.live
@pytest.mark.requires_docker
@pytest.mark.requires_redis
def test_cache_is_available_true_when_redis_running() -> None:
    manager = CacheManager()
    if not manager.is_available():
        pytest.skip("Redis unavailable")
    assert manager.is_available() is True
