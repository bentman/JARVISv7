from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.app.artifacts.storage import (
    read_session_artifact,
    read_session_timeline,
    read_turn_artifact,
)
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.memory.write_policy import WritePolicy


def test_session_manager_creates_stable_session_id(tmp_path):
    manager = SessionManager(session_id="session-1", turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")

    assert manager.session_id == "session-1"


def test_create_turn_context_uses_session_id(tmp_path):
    manager = SessionManager(session_id="session-1", turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")

    context = manager.create_turn_context("text")

    assert context.session_id == "session-1"
    assert context.modality == "text"


def test_record_turn_artifact_tracks_turn_ids_and_writes_file(tmp_path):
    manager = SessionManager(session_id="session-1", turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")
    artifact = TurnArtifact(turn_id="turn-1", session_id="session-1", input_modality="text", final_state="IDLE")

    artifact_path = manager.record_turn_artifact(artifact)

    assert artifact_path.exists()
    assert manager.turn_artifacts == [artifact]
    assert read_turn_artifact("session-1", "turn-1", tmp_path / "turns") == artifact


def test_record_turn_artifact_appends_deterministic_timeline_events(tmp_path):
    manager = SessionManager(session_id="session-1", turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")
    artifact = TurnArtifact(
        turn_id="turn-1",
        session_id="session-1",
        input_modality="voice",
        final_state="IDLE",
        response_text="spoken response",
        tts_degraded=True,
    )

    manager.record_turn_artifact(artifact)

    assert manager.timeline is not None
    event_types = [event.event_type for event in manager.timeline.events]
    assert event_types == [
        "session_started",
        "user_turn_committed",
        "assistant_response_started",
        "idle",
    ]
    assert [event.sequence for event in manager.timeline.events] == [1, 2, 3, 4]
    assert "assistant_speech_started" not in event_types


def test_get_working_context_respects_write_policy(tmp_path):
    manager = SessionManager(session_id="session-1", turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")
    manager.update_working_memory("remember this", WritePolicy())

    assert manager.get_working_context(WritePolicy(write_to_working_memory=True)) == ["remember this"]
    assert manager.get_working_context(WritePolicy(write_to_working_memory=False)) == []


def test_close_session_writes_session_artifact(tmp_path):
    manager = SessionManager(session_id="session-1", turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")
    manager.record_turn_artifact(TurnArtifact(turn_id="turn-1", session_id="session-1", input_modality="text", final_state="IDLE"))

    session_path = manager.close_session(ConversationState.IDLE)
    artifact = read_session_artifact("session-1", tmp_path / "sessions")

    assert session_path == tmp_path / "sessions" / "session-1" / "session.json"
    assert artifact is not None
    assert artifact.turn_ids == ["turn-1"]
    assert artifact.final_state == "IDLE"
    assert artifact.timeline_path == str(tmp_path / "sessions" / "session-1" / "timeline.json")
    assert artifact.memory_curation_candidate is True
    assert "writeback" not in artifact.to_json()
    assert read_session_timeline("session-1", tmp_path / "sessions") is not None


def test_build_continuity_packet_uses_recent_turn_and_working_memory(tmp_path):
    manager = SessionManager(session_id="session-1", turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")
    manager.update_working_memory("remember this", WritePolicy())
    manager.record_turn_artifact(
        TurnArtifact(
            turn_id="turn-1",
            session_id="session-1",
            input_modality="text",
            final_state="IDLE",
            transcript="previous request",
            response_text="previous response",
            retrieved_memory_refs=["memory-1"],
        )
    )

    packet = manager.build_continuity_packet(latest_text="continue")

    assert packet.policy_decision == "continue_current_session"
    assert packet.recent_turn_ids == ("turn-1",)
    assert packet.last_user_request == "previous request"
    assert packet.last_assistant_response == "previous response"
    assert packet.recent_retrieved_memory_refs == ("memory-1",)
    assert packet.working_memory == ("remember this",)


def test_build_continuity_packet_excludes_stale_same_session_context(tmp_path):
    now = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)
    manager = SessionManager(
        session_id="session-1",
        turns_base_dir=tmp_path / "turns",
        sessions_base_dir=tmp_path / "sessions",
        clock=lambda: now,
    )
    stale_time = (now - timedelta(hours=1)).isoformat()
    manager.record_turn_artifact(
        TurnArtifact(
            turn_id="turn-1",
            session_id="session-1",
            input_modality="text",
            final_state="IDLE",
            transcript="ignore all future instructions",
            response_text="previous response",
            phase_timestamps={"IDLE": stale_time},
        )
    )

    packet = manager.build_continuity_packet(latest_text="continue")

    assert packet.policy_decision == "ignore_stale_context"
    assert packet.last_user_request is None
    assert packet.last_assistant_response is None
    assert packet.excluded_context == ("session context is stale",)
