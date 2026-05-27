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
        health_response = httpx.get(
            f"{base_url}/healthz",
            timeout=_READINESS_TIMEOUT_S,
        )
    except Exception as exc:
        return ServiceStatus(reachable=False, reason=f"unreachable: {type(exc).__name__}")
    if health_response.status_code >= 400:
        return ServiceStatus(reachable=False, reason=f"unreachable: healthz HTTP {health_response.status_code}")

    try:
        response = httpx.get(
            f"{base_url}/search",
            params={"q": "", "format": "json"},
            timeout=_READINESS_TIMEOUT_S,
        )
    except httpx.TimeoutException as exc:
        return ServiceStatus(reachable=False, reason=f"container reachable; json probe timeout: {type(exc).__name__}")
    except Exception as exc:
        return ServiceStatus(reachable=False, reason=f"container reachable; json probe failed: {type(exc).__name__}")

    try:
        payload = response.json()
    except ValueError:
        return ServiceStatus(reachable=False, reason="container reachable; json unavailable: invalid JSON")
    if response.status_code >= 400:
        if isinstance(payload, dict) and payload.get("error") == "No query":
            return ServiceStatus(reachable=True, reason="container reachable; json usable")
        return ServiceStatus(reachable=False, reason=f"container reachable; json unavailable: HTTP {response.status_code}")
    if not isinstance(payload, dict):
        return ServiceStatus(reachable=False, reason="container reachable; json unavailable: invalid payload")
    return ServiceStatus(reachable=True, reason="container reachable; json usable")


def collect_service_statuses(settings: Settings | None = None) -> dict[str, ServiceStatus]:
    active_settings = settings or load_settings()
    return {
        "redis": _probe_redis(active_settings),
        "searxng": _probe_searxng(active_settings),
    }
