from __future__ import annotations

import logging
import time

import redis

from backend.app.core.settings import load_settings

_LOGGER = logging.getLogger(__name__)
_CLIENT: redis.Redis | None = None
_NEXT_RETRY_AT: float | None = None
_RETRY_COOLDOWN_SECONDS = 30.0


def get_client() -> redis.Redis | None:
    global _CLIENT, _NEXT_RETRY_AT
    if _CLIENT is not None:
        return _CLIENT
    now = time.monotonic()
    if _NEXT_RETRY_AT is not None and now < _NEXT_RETRY_AT:
        return None
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
        _NEXT_RETRY_AT = None
    except Exception as exc:
        _LOGGER.warning("Redis unavailable; cache disabled: %s", exc)
        _CLIENT = None
        _NEXT_RETRY_AT = time.monotonic() + _RETRY_COOLDOWN_SECONDS
    return _CLIENT
