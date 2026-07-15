from __future__ import annotations

import json

from backend.app.artifacts import storage
from backend.app.artifacts.session_artifact import SESSION_ARTIFACT_FIELDS, SessionArtifact
from backend.app.artifacts.trace_writer import write_trace
from backend.app.artifacts.turn_artifact import TURN_ARTIFACT_FIELDS, TurnArtifact


def _turn_artifact() -> TurnArtifact:
    return TurnArtifact(
        turn_id="turn-1",
        session_id="session-1",
        input_modality="text",
        active_personality_profile_id="test",
        transcript="hello",
        final_prompt_text="User: hello",
        response_text="ready",
        final_state="IDLE",
        runtime_context={"llm": "fake"},
        phase_timestamps={"IDLE": "2026-04-27T00:00:00+00:00"},
        phase_durations_ms={"llm_ms": 12.5},
    )


def test_turn_artifact_serializes_to_json():
    payload = json.loads(_turn_artifact().to_json())

    assert payload["turn_id"] == "turn-1"
    assert payload["session_id"] == "session-1"
    assert payload["runtime_context"] == {"llm": "fake"}
    assert payload["phase_timestamps"]["IDLE"].endswith("+00:00")
    assert payload["phase_durations_ms"] == {"llm_ms": 12.5}
    assert payload["failure_phase"] is None


def test_turn_artifact_roundtrips_via_storage(tmp_path):
    artifact = _turn_artifact()
    storage.write_turn_artifact(artifact, tmp_path)

    loaded = storage.read_turn_artifact("session-1", "turn-1", tmp_path)

    assert loaded == artifact


def test_storage_write_creates_expected_turn_file_path(tmp_path):
    artifact_path = storage.write_turn_artifact(_turn_artifact(), tmp_path)

    assert artifact_path == tmp_path / "session-1" / "turn-1.json"
    assert artifact_path.exists()


def test_storage_read_returns_none_for_missing_artifact(tmp_path):
    assert storage.read_turn_artifact("missing-session", "missing-turn", tmp_path) is None


def test_atomic_write_text_replaces_existing_content_and_removes_tmp(tmp_path):
    target = tmp_path / "file.json"
    target.write_text("old", encoding="utf-8")

    storage._atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"
    assert not target.with_name("file.json.tmp").exists()


def test_storage_writes_leave_no_tmp_files(tmp_path):
    artifact_path = storage.write_turn_artifact(_turn_artifact(), tmp_path)

    assert artifact_path.exists()
    assert list(artifact_path.parent.glob("*.tmp")) == []


def test_storage_write_atomically_replaces_existing_turn_artifact(tmp_path):
    artifact = _turn_artifact()
    storage.write_turn_artifact(artifact, tmp_path)
    artifact.response_text = "updated"
    storage.write_turn_artifact(artifact, tmp_path)

    loaded = storage.read_turn_artifact("session-1", "turn-1", tmp_path)

    assert loaded is not None
    assert loaded.response_text == "updated"


def test_write_trace_is_atomic_and_leaves_no_tmp_file(tmp_path):
    trace_path = write_trace("turn-1", "trace content", tmp_path / "traces")

    assert trace_path.read_text(encoding="utf-8") == "trace content"
    assert list(trace_path.parent.glob("*.tmp")) == []


def test_turn_schema_fields_unchanged():
    assert TURN_ARTIFACT_FIELDS == (
        "turn_id",
        "session_id",
        "input_modality",
        "hardware_profile_id",
        "capability_flags_snapshot",
        "active_personality_profile_id",
        "profile_epoch",
        "raw_audio_path",
        "transcript",
        "final_prompt_text",
        "retrieved_memory_refs",
        "tools_invoked",
        "agent_trace",
        "reasoning_trace_metadata",
        "response_text",
        "audio_output_path",
        "interruption_events",
        "final_state",
        "failure_reason",
        "tts_degraded",
        "tts_degraded_reason",
        "tts_output_device",
        "runtime_context",
        "phase_timestamps",
        "phase_durations_ms",
        "failure_phase",
    )


def test_mutable_defaults_are_not_shared():
    first = TurnArtifact(turn_id="one", session_id="session", input_modality="text", final_state="IDLE")
    second = TurnArtifact(turn_id="two", session_id="session", input_modality="text", final_state="IDLE")

    first.tools_invoked.append("tool")

    assert second.tools_invoked == []


def test_session_artifact_roundtrips_via_storage(tmp_path):
    artifact = SessionArtifact(
        session_id="session-1",
        started_at="2026-04-27T00:00:00+00:00",
        ended_at="2026-04-27T00:00:01+00:00",
        turn_ids=["turn-1"],
        final_state="IDLE",
    )
    artifact_path = storage.write_session_artifact(artifact, tmp_path)

    loaded = storage.read_session_artifact("session-1", tmp_path)

    assert artifact_path == tmp_path / "session-1" / "session.json"
    assert loaded == artifact


def test_session_storage_read_returns_none_for_missing_artifact(tmp_path):
    assert storage.read_session_artifact("missing-session", tmp_path) is None


def test_session_schema_fields_unchanged():
    assert SESSION_ARTIFACT_FIELDS == (
        "session_id",
        "started_at",
        "ended_at",
        "turn_ids",
        "final_state",
        "timeline_path",
        "continuity_summary",
        "memory_curation_candidate",
    )
