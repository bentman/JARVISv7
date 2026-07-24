from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

from backend.app.artifacts.session_artifact import SessionArtifact
from backend.app.artifacts.storage import (
    write_session_artifact,
    write_turn_artifact,
)
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.api.app import lifespan
from backend.app.memory.semantic import SemanticMemory
from backend.app.services.llm_execution_coordinator import LLMExecutionCoordinator
from backend.app.services.memory_curation_service import (
    CurationProcessorResult,
    MemoryCurationService,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

NOW = "2026-07-24T12:00:00+00:00"


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
        llm_coordinator=None,
        resident_audio_stream=_Stopper("audio", events),
        local_llm_sidecar=_Stopper("sidecar", events),
    )

    with TestClient(app):
        pass

    assert events == ["curation:1.0", "audio", "sidecar"]


def test_lifespan_keeps_sidecar_alive_for_in_flight_non_preemptible_processor(
    tmp_path: Path,
) -> None:
    memory = SemanticMemory(tmp_path / "memory.sqlite")
    enabled = memory.update_policy(
        automatic_curation_enabled=True,
        expected_revision=1,
    )
    assert enabled.value is not None
    sessions_root = tmp_path / "sessions"
    turns_root = tmp_path / "turns"
    turn = TurnArtifact(
        turn_id="turn-1",
        session_id="session-1",
        input_modality="text",
        final_state="IDLE",
        transcript="remember this",
        response_text="acknowledged",
    )
    write_turn_artifact(turn, turns_root)
    artifact_path = write_session_artifact(
        SessionArtifact(
            session_id="session-1",
            started_at=NOW,
            ended_at=NOW,
            turn_ids=[turn.turn_id],
            final_state="IDLE",
            memory_curation_candidate=True,
            memory_curation_authorized_at=NOW,
            memory_curation_policy_revision=enabled.value.revision,
        ),
        sessions_root,
    )
    coordinator = LLMExecutionCoordinator()
    processor_started = threading.Event()
    release_processor = threading.Event()

    def processor(_evidence) -> CurationProcessorResult:
        processor_started.set()
        assert release_processor.wait(5)
        return CurationProcessorResult(success=True, durable=True)

    service = MemoryCurationService(
        semantic_memory=memory,
        sessions_root=sessions_root,
        turns_root=turns_root,
        coordinator=coordinator,
        session_is_active=lambda: False,
        processor=processor,
        runtime_status=lambda: {"ready": True},
        boot_id="test-boot",
    )
    enqueue = service.enqueue_closed_session(
        session_id="session-1",
        artifact_path=artifact_path,
        policy_revision=enabled.value.revision,
        authorized_at=NOW,
    )
    assert enqueue.succeeded
    drain_thread = threading.Thread(
        target=lambda: service.drain(timeout=5),
        daemon=True,
    )
    drain_thread.start()
    try:
        assert processor_started.wait(1)
        assert coordinator.snapshot()["background_active"] is True

        events: list[str] = []
        app = FastAPI(lifespan=lifespan)
        app.state.jarvis_state = SimpleNamespace(
            memory_curation_service=service,
            llm_coordinator=coordinator,
            resident_audio_stream=_Stopper("audio", events),
            local_llm_sidecar=_Stopper("sidecar", events),
        )

        with TestClient(app):
            pass

        assert coordinator.snapshot()["background_active"] is True
        assert events == ["audio"]
    finally:
        release_processor.set()
        drain_thread.join(2)
        service.stop(timeout=1)
    assert not drain_thread.is_alive()
