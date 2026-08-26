from __future__ import annotations

from pathlib import Path

import httpx
import yaml
from backend.app.api.service_status import _probe_searxng
from backend.app.core.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[4]


class _Response:
    def __init__(self, status_code: int = 200, payload: object | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {"results": []}

    def json(self) -> object:
        return self._payload


class _InvalidJsonResponse(_Response):
    def json(self) -> object:
        raise ValueError("not json")


def _searxng_settings() -> Settings:
    settings = Settings()
    settings.use_searxng = True
    settings.searxng_base_url = "http://searxng.test:8080"
    return settings


def test_repo_searxng_settings_enable_default_settings_and_json_format() -> None:
    config_path = REPO_ROOT / "config" / "search" / "searxng" / "settings.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert config["use_default_settings"] is True
    assert "json" in set(config["search"]["formats"])


def test_compose_points_searxng_to_repo_mounted_settings() -> None:
    compose_path = REPO_ROOT / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    service = compose["services"]["searxng"]

    assert "SEARXNG_SETTINGS_PATH=/etc/searxng/settings.yml" in service["environment"]
    assert "./config/search/searxng:/etc/searxng:rw" in service["volumes"]


def test_searxng_probe_reports_json_usable(monkeypatch) -> None:
    def _get(url: str, **kwargs: object) -> _Response:
        if url.endswith("/healthz"):
            return _Response()
        assert kwargs["params"] == {"q": "", "format": "json"}
        return _Response(status_code=400, payload={"error": "No query"})

    monkeypatch.setattr("backend.app.api.service_status.httpx.get", _get)

    status = _probe_searxng(_searxng_settings())

    assert status.reachable is True
    assert status.reason == "container reachable; json usable"


def test_searxng_probe_accepts_empty_query_error_as_json_usable(monkeypatch) -> None:
    def _get(url: str, **kwargs: object) -> _Response:
        if url.endswith("/healthz"):
            return _Response()
        assert kwargs["params"] == {"q": "", "format": "json"}
        return _Response(payload={"results": []})

    monkeypatch.setattr("backend.app.api.service_status.httpx.get", _get)

    status = _probe_searxng(_searxng_settings())

    assert status.reachable is True
    assert status.reason == "container reachable; json usable"


def test_searxng_probe_reports_container_unreachable(monkeypatch) -> None:
    def _get(url: str, **kwargs: object) -> _Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr("backend.app.api.service_status.httpx.get", _get)

    status = _probe_searxng(_searxng_settings())

    assert status.reachable is False
    assert status.reason == "unreachable: ConnectError"


def test_searxng_probe_reports_json_unavailable(monkeypatch) -> None:
    def _get(url: str, **kwargs: object) -> _Response:
        if url.endswith("/healthz"):
            return _Response()
        return _Response(status_code=403)

    monkeypatch.setattr("backend.app.api.service_status.httpx.get", _get)

    status = _probe_searxng(_searxng_settings())

    assert status.reachable is False
    assert status.reason == "container reachable; json unavailable: HTTP 403"


def test_searxng_probe_reports_json_probe_timeout(monkeypatch) -> None:
    def _get(url: str, **kwargs: object) -> _Response:
        if url.endswith("/healthz"):
            return _Response()
        raise httpx.ReadTimeout("search timed out")

    monkeypatch.setattr("backend.app.api.service_status.httpx.get", _get)

    status = _probe_searxng(_searxng_settings())

    assert status.reachable is False
    assert status.reason == "container reachable; json probe timeout: ReadTimeout"


def test_searxng_probe_reports_invalid_json(monkeypatch) -> None:
    def _get(url: str, **kwargs: object) -> _Response:
        if url.endswith("/healthz"):
            return _Response()
        return _InvalidJsonResponse()

    monkeypatch.setattr("backend.app.api.service_status.httpx.get", _get)

    status = _probe_searxng(_searxng_settings())

    assert status.reachable is False
    assert status.reason == "container reachable; json unavailable: invalid JSON"
