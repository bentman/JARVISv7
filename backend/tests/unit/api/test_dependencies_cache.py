from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from backend.app.api.dependencies import get_cache_manager
from backend.app.cache.manager import CacheManager


def test_get_cache_manager_returns_app_state_cache_manager() -> None:
    expected = CacheManager()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(jarvis_state=SimpleNamespace(cache_manager=expected))))
    assert get_cache_manager(cast(Any, request)) is expected
