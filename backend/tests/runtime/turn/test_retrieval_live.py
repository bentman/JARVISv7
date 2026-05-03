from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.memory.episodic import EpisodicMemory
from backend.app.personality.loader import load_default_personality
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.tts.tts_runtime import NullTTSRuntime
from backend.tests.conftest import SKIP_UNLESS_LIVE, SKIP_UNLESS_OLLAMA, ollama_base_url


class UnusedSTT(STTBase):
    def __init__(self) -> None:
        super().__init__(device="cpu", model_path=Path("unused"))

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        raise AssertionError("text turn must not call STT")

    def is_available(self) -> bool:
        return False


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.requires_ollama
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_OLLAMA, reason="OLLAMA_BASE_URL not set")
def test_episodic_entry_written_after_text_turn(tmp_path: Path) -> None:
    manager = SessionManager(session_id="retrieval-live-1", turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")
    episodic = EpisodicMemory(base_dir=tmp_path / "episodic", sessions_base_dir=tmp_path / "sessions")
    engine = TurnEngine(
        stt=UnusedSTT(),
        tts=NullTTSRuntime(reason="not used"),
        llm=OllamaLLM(base_url=ollama_base_url()),
        personality=load_default_personality(),
        session_manager=manager,
        episodic=episodic,
    )
    result = engine.run_text_turn("Reply with exactly: episodic proof")
    assert result.failure_reason is None
    assert (tmp_path / "episodic" / "retrieval-live-1" / f"{result.turn_id}.json").exists()


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_retrieve_recent_returns_entry_from_prior_session(tmp_path: Path) -> None:
    episodic = EpisodicMemory(base_dir=tmp_path / "episodic", sessions_base_dir=tmp_path / "sessions")
    session_dir = tmp_path / "episodic" / "prior-session"
    session_dir.mkdir(parents=True)
    (session_dir / "prior-turn.json").write_text(
        """{
  \"turn_id\": \"prior-turn\",
  \"session_id\": \"prior-session\",
  \"session_started_at\": \"2026-01-01T00:00:00+00:00\",
  \"transcript\": \"prior transcript\",
  \"response_text\": \"prior response\",
  \"tools_invoked\": [],
  \"written_at\": \"2026-01-01T00:00:00+00:00\"
}
""",
        encoding="utf-8",
    )
    out = episodic.retrieve_recent(n=1)
    assert len(out) == 1
    assert out[0].turn_id == "prior-turn"


@pytest.mark.g2_required
def test_turn_artifact_retrieved_memory_refs_populated_after_retrieval() -> None:
    pytest.skip("G.2 scope: retrieved_memory_refs population")
