from __future__ import annotations

from dataclasses import dataclass

import httpx
import redis

from backend.app.core.settings import Settings, load_settings


_READINESS_TIMEOUT_S = 0.5


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    reachable: bool
    reason: str


def _probe_redis(settings: Settings) -> ServiceStatus:
    try:
        client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            socket_timeout=min(settings.redis_socket_timeout, _READINESS_TIMEOUT_S),
            socket_connect_timeout=_READINESS_TIMEOUT_S,
            decode_responses=True,
        )
        client.ping()
        return ServiceStatus(reachable=True, reason="reachable")
    except Exception as exc:
        return ServiceStatus(reachable=False, reason=f"unreachable: {type(exc).__name__}")


def _probe_searxng(settings: Settings) -> ServiceStatus:
    base_url = settings.searxng_base_url.rstrip("/")
    if not settings.use_searxng or not base_url:
        return ServiceStatus(reachable=False, reason="not configured")
    try:
        response = httpx.get(
            f"{base_url}/search",
            params={"q": "jarvis", "format": "json"},
            timeout=_READINESS_TIMEOUT_S,
        )
        response.raise_for_status()
        return ServiceStatus(reachable=True, reason="reachable")
    except Exception as exc:
        return ServiceStatus(reachable=False, reason=f"unreachable: {type(exc).__name__}")


def collect_service_statuses(settings: Settings | None = None) -> dict[str, ServiceStatus]:
    active_settings = settings or load_settings()
    return {
        "redis": _probe_redis(active_settings),
        "searxng": _probe_searxng(active_settings),
    }