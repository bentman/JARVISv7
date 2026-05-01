from __future__ import annotations

import logging

import redis

from backend.app.core.settings import load_settings

_LOGGER = logging.getLogger(__name__)
_CLIENT: redis.Redis | None = None
_INITIALIZED = False


def get_client() -> redis.Redis | None:
    global _CLIENT, _INITIALIZED
    if _INITIALIZED:
        return _CLIENT
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
    except Exception as exc:
        _LOGGER.warning("Redis unavailable; cache disabled: %s", exc)
        _CLIENT = None
    return _CLIENT
