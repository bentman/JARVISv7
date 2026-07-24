from __future__ import annotations

from types import SimpleNamespace

from backend.app.api.app import lifespan
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _Stopper:
    def __init__(self, name: str, events: list[str]) -> None:
        self.name = name
        self.events = events

    def stop(self, timeout: float | None = None) -> None:
        suffix = f":{timeout}" if timeout is not None else ""
        self.events.append(f"{self.name}{suffix}")


def test_lifespan_stops_curation_before_audio_and_llm_sidecar() -> None:
    events: list[str] = []
    app = FastAPI(lifespan=lifespan)
    app.state.jarvis_state = SimpleNamespace(
        memory_curation_service=_Stopper("curation", events),
        resident_audio_stream=_Stopper("audio", events),
        local_llm_sidecar=_Stopper("sidecar", events),
    )

    with TestClient(app):
        pass

    assert events == ["curation:1.0", "audio", "sidecar"]
