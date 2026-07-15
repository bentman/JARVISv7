from __future__ import annotations

import json
from pathlib import Path

from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.memory.episodic import EpisodicEntry, EpisodicMemory
from backend.app.memory.write_policy import WritePolicy


def _artifact(*, turn_id: str = "turn-1", response: str = "this is long enough", failed: bool = False) -> TurnArtifact:
    return TurnArtifact(
        turn_id=turn_id,
        session_id="session-1",
        input_modality="text",
        transcript="remember apples",
        response_text=response,
        final_state="IDLE",
        failure_reason="boom" if failed else None,
    )


def test_write_entry_creates_json_file_under_episodic_path(tmp_path: Path) -> None:
    mem = EpisodicMemory(base_dir=tmp_path / "episodic", sessions_base_dir=tmp_path / "sessions")
    entry = mem.write_entry(_artifact(), WritePolicy())
    assert entry is not None
    assert (tmp_path / "episodic" / "session-1" / "turn-1.json").exists()


def test_write_entry_is_idempotent_for_same_turn_id(tmp_path: Path) -> None:
    mem = EpisodicMemory(base_dir=tmp_path / "episodic", sessions_base_dir=tmp_path / "sessions")
    mem.write_entry(_artifact(), WritePolicy())
    mem.write_entry(_artifact(), WritePolicy())
    assert len(list((tmp_path / "episodic" / "session-1").glob("*.json"))) == 1


def test_write_entry_skips_failed_turn_per_policy(tmp_path: Path) -> None:
    mem = EpisodicMemory(base_dir=tmp_path / "episodic")
    assert mem.write_entry(_artifact(failed=True), WritePolicy()) is None


def test_write_entry_skips_short_response_per_policy(tmp_path: Path) -> None:
    mem = EpisodicMemory(base_dir=tmp_path / "episodic")
    assert mem.write_entry(_artifact(response="short"), WritePolicy()) is None


def test_write_entry_skips_when_episodic_disabled(tmp_path: Path) -> None:
    mem = EpisodicMemory(base_dir=tmp_path / "episodic")
    assert mem.write_entry(_artifact(), WritePolicy(write_to_episodic_memory=False)) is None


def test_retrieve_recent_returns_sorted_by_written_at_desc(tmp_path: Path) -> None:
    root = tmp_path / "episodic" / "session-1"
    root.mkdir(parents=True)
    (root / "a.json").write_text(json.dumps({"turn_id":"a","session_id":"s","session_started_at":"x","transcript":"t","response_text":"r","tools_invoked":[],"written_at":"2026-01-01T00:00:00+00:00"}))
    (root / "b.json").write_text(json.dumps({"turn_id":"b","session_id":"s","session_started_at":"x","transcript":"t","response_text":"r","tools_invoked":[],"written_at":"2026-01-02T00:00:00+00:00"}))
    out = EpisodicMemory(base_dir=tmp_path / "episodic").retrieve_recent()
    assert [e.turn_id for e in out][:2] == ["b", "a"]


def test_retrieve_recent_returns_empty_list_on_io_error(tmp_path: Path) -> None:
    assert EpisodicMemory(base_dir=tmp_path / "missing").retrieve_recent() == []


def test_retrieve_by_keyword_matches_transcript_and_response_case_insensitive(tmp_path: Path) -> None:
    root = tmp_path / "episodic" / "session-1"
    root.mkdir(parents=True)
    (root / "a.json").write_text(json.dumps({"turn_id":"a","session_id":"s","session_started_at":"x","transcript":"Apple pie","response_text":"Banana","tools_invoked":[],"written_at":"2026-01-01T00:00:00+00:00"}))
    mem = EpisodicMemory(base_dir=tmp_path / "episodic")
    assert mem.retrieve_by_keyword("apple")
    assert mem.retrieve_by_keyword("BANANA")
    assert mem.retrieve_by_keyword("nomatch") == []


def test_retrieve_skips_corrupt_files_and_returns_valid_entries(tmp_path: Path) -> None:
    root = tmp_path / "episodic" / "session-1"
    root.mkdir(parents=True)
    (root / "good.json").write_text(json.dumps({"turn_id":"good","session_id":"s","session_started_at":"x","transcript":"t","response_text":"r","tools_invoked":[],"written_at":"2026-01-01T00:00:00+00:00"}))
    (root / "bad.json").write_text("{not valid json")
    out = EpisodicMemory(base_dir=tmp_path / "episodic").retrieve_recent()
    assert [e.turn_id for e in out] == ["good"]


def test_from_dict_tolerates_null_list_fields() -> None:
    entry = EpisodicEntry.from_dict({"turn_id": "a", "tools_invoked": None})
    assert entry.tools_invoked == []


def test_write_entry_is_atomic_and_leaves_no_tmp_file(tmp_path: Path) -> None:
    mem = EpisodicMemory(base_dir=tmp_path / "episodic", sessions_base_dir=tmp_path / "sessions")
    entry = mem.write_entry(_artifact(), WritePolicy())
    assert entry is not None
    session_dir = tmp_path / "episodic" / "session-1"
    assert (session_dir / "turn-1.json").exists()
    assert list(session_dir.glob("*.tmp")) == []


def test_write_entry_succeeds_when_pruning_fails(tmp_path: Path, monkeypatch) -> None:
    mem = EpisodicMemory(base_dir=tmp_path / "episodic", sessions_base_dir=tmp_path / "sessions")

    def _boom(policy: WritePolicy) -> None:
        raise OSError("prune failed")

    monkeypatch.setattr(mem, "_prune_sessions", _boom)
    entry = mem.write_entry(_artifact(), WritePolicy())
    assert entry is not None
    assert (tmp_path / "episodic" / "session-1" / "turn-1.json").exists()
