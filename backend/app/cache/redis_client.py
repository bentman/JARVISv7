from __future__ import annotations

import logging
import threading
import time

import redis
from backend.app.core.settings import load_settings

_LOGGER = logging.getLogger(__name__)
_CLIENT: redis.Redis | None = None
_INITIALIZED = False
_INIT_LOCK = threading.Lock()
_RETRY_INTERVAL_S = 30.0
_LAST_FAILURE_MONOTONIC: float | None = None


def get_client() -> redis.Redis | None:
    global _CLIENT, _INITIALIZED, _LAST_FAILURE_MONOTONIC
    if _INITIALIZED and _CLIENT is not None:
        return _CLIENT
    with _INIT_LOCK:
        if _INITIALIZED and _CLIENT is not None:
            return _CLIENT
        if (
            _INITIALIZED
            and _LAST_FAILURE_MONOTONIC is not None
            and (time.monotonic() - _LAST_FAILURE_MONOTONIC) < _RETRY_INTERVAL_S
        ):
            return None
        _INITIALIZED = True
        settings = load_settings()
        try:
            client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                max_connections=settings.redis_max_connections,
                socket_timeout=settings.redis_socket_timeout,
                decode_responses=True,
            )
            client.ping()
            _CLIENT = client
            _LAST_FAILURE_MONOTONIC = None
        except Exception as exc:
            _LOGGER.warning("Redis unavailable; cache disabled: %s", exc)
            _CLIENT = None
            _LAST_FAILURE_MONOTONIC = time.monotonic()
        return _CLIENT
