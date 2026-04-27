from __future__ import annotations

from backend.app.artifacts.storage import read_session_artifact, read_turn_artifact
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