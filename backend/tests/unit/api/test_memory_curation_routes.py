from __future__ import annotations

from dataclasses import dataclass

from backend.app.api.dependencies import get_api_state
from backend.app.api.routes.memory_curation import router
from backend.app.services.memory_curation_service import DrainResult
from fastapi import FastAPI
from fastapi.testclient import TestClient


@dataclass
class _Status:
    jobs: tuple[object, ...] = ()


class _Service:
    def __init__(self) -> None:
        self.status_calls = 0
        self.drain_calls: list[float] = []

    def status(self) -> _Status:
        self.status_calls += 1
        return _Status()

    def drain(self, timeout: float) -> DrainResult:
        self.drain_calls.append(timeout)
        return DrainResult("no_work", None, 0, False)


@dataclass
class _State:
    memory_curation_service: _Service | None


def _client(state: _State) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_api_state] = lambda: state
    return TestClient(app)


def test_get_status_is_read_only_adapter() -> None:
    service = _Service()
    response = _client(_State(service)).get("/memory/curation/status")

    assert response.status_code == 200
    assert response.json() == {"jobs": []}
    assert service.status_calls == 1
    assert service.drain_calls == []


def test_post_drain_uses_explicit_eight_second_server_budget() -> None:
    service = _Service()
    response = _client(_State(service)).post("/memory/curation/drain")

    assert response.status_code == 200
    assert response.json()["outcome"] == "no_work"
    assert service.drain_calls == [8.0]


def test_routes_report_unavailable_service() -> None:
    client = _client(_State(None))

    assert client.get("/memory/curation/status").status_code == 503
    assert client.post("/memory/curation/drain").status_code == 503
