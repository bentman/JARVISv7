from __future__ import annotations

import threading

import numpy as np
import pytest
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.personality.loader import load_default_personality
from backend.app.runtimes.internetsearch.base import SearchResponse
from backend.app.runtimes.internetsearch.page_reader import PageResult
from backend.app.services.llm_execution_coordinator import LLMExecutionCoordinator
from backend.tests.unit.cognition.test_search_policy import Model
from backend.tests.unit.services.test_search_service import Provider, SearchService, result

pytestmark = [pytest.mark.search, pytest.mark.turn]


class STT:
    def transcribe(self, audio, sample_rate):
        return "Please search for a public topic"


class TTS:
    def __init__(self):
        self.spoken = []
    def is_available(self):
        return False
    def synthesize(self, text):
        self.spoken.append(text)
        return np.ones(10)
    def sample_rate(self):
        return 16000


def engine_at(tmp_path, model=None, providers=None):
    class Reader:
        def read(self, url, *, cancelled):
            return PageResult(url, "success", "Public page evidence")
    manager = SessionManager(turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")
    engine = TurnEngine(
        stt=STT(), tts=TTS(), llm=model or Model(), personality=load_default_personality(),
        session_manager=manager, llm_coordinator=LLMExecutionCoordinator(),
        search_service=SearchService(providers if providers is not None else [Provider("ddgs", SearchResponse("success", (result(),)), [])], Reader()),
    )
    return engine, manager


@pytest.mark.parametrize("voice", [False, True])
def test_shared_path_evidence_and_single_ticket_release(tmp_path, voice):
    engine, manager = engine_at(tmp_path)
    turn = engine.run_voice_turn(np.ones(10), 16000) if voice else engine.run_text_turn("Please search for a public topic")
    assert turn.failure_reason is None
    assert turn.search["sources"][0]["id"] == "S1"
    assert "[S1]" in turn.response_text
    assert manager.turn_artifacts[0].search["queries"] == ["public topic"]
    assert manager.turn_artifacts[0].tools_invoked == ["ddgs"]
    assert "search_outcome" in [event.event_type for event in manager.timeline.events]
    assert engine.llm_coordinator.snapshot()["interactive_active"] is False
    assert engine.search_service.snapshot() is None
    if voice:
        assert turn.tts_degraded


def test_normal_chat_does_not_plan_or_search(tmp_path):
    engine, manager = engine_at(tmp_path)
    turn = engine.run_text_turn("Hello there")
    assert turn.search is None
    assert manager.turn_artifacts[0].search is None


@pytest.mark.parametrize("action,text", [("none", "Don't search for this"), ("none", 'The phrase "search for cats" is a command'), ("none", "Find my saved note"), ("clarify", "Find Mercury")])
def test_semantic_decisions_cannot_dispatch_network(tmp_path, action, text):
    calls = []
    engine, _ = engine_at(tmp_path, Model(action=action), [Provider("ddgs", SearchResponse("empty"), calls)])
    engine.run_text_turn(text)
    assert not calls


def test_contextual_research_only_gets_bounded_current_user_topic(tmp_path):
    model = Model()
    engine, _ = engine_at(tmp_path, model)
    engine.run_text_turn("Tell me about solar panels")
    model.decision.update(action="research", queries=["solar panel efficiency", "solar panel lifespan"])
    turn = engine.run_text_turn("Please research this")
    assert turn.search["mode"] == "research"
    planner = next(prompt for prompt in model.prompts if prompt.segments[0].text.startswith("Classify"))
    assert planner.segments[1].text == "Tell me about solar panels"


@pytest.mark.parametrize("failure", [False, True])
def test_cancel_during_model_synthesis_preserves_audit_and_releases_ticket(tmp_path, failure):
    started, release = threading.Event(), threading.Event()
    class Blocking(Model):
        def generate_envelope(self, envelope, **kwargs):
            started.set()
            assert release.wait(4)
            if failure:
                raise RuntimeError("model failed")
            return super().generate_envelope(envelope, **kwargs)
    engine, manager = engine_at(tmp_path, Blocking())
    results = []
    worker = threading.Thread(target=lambda: results.append(engine.run_text_turn("Search for public topic")))
    worker.start()
    try:
        assert started.wait(2)
        active = engine.search_service.snapshot()
        with pytest.raises(RuntimeError, match="already active"):
            engine.run_text_turn("overlap")
        assert not engine.cancel_search(active["session_id"], "stale")
        assert engine.cancel_search(active["session_id"], active["turn_id"])
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert results[0].search["outcome"] == "cancelled"
    assert results[0].response_text == "Search cancelled."
    assert manager.turn_artifacts[0].search["attempts"]
    assert engine.llm_coordinator.snapshot()["interactive_active"] is False


def test_close_cancels_and_waits_for_audit_before_session_close(tmp_path):
    started, release = threading.Event(), threading.Event()
    class Blocking(Provider):
        def search(self, query, *, max_results=5):
            started.set()
            assert release.wait(4)
            return super().search(query, max_results=max_results)
    engine, manager = engine_at(tmp_path, providers=[Blocking("ddgs", SearchResponse("empty"), [])])
    worker = threading.Thread(target=lambda: engine.run_text_turn("Search for topic"))
    worker.start()
    try:
        assert started.wait(2)
        with pytest.raises(RuntimeError, match="cancelling"):
            engine.prepare_close(timeout=0)
        assert not manager.turn_artifacts
    finally:
        release.set()
        worker.join(5)
    engine.prepare_close()
    manager.close_session()
    assert manager.turn_artifacts[0].search["outcome"] == "cancelled"
    with pytest.raises(RuntimeError, match="closing"):
        engine.run_text_turn("new request")


def test_old_artifact_search_default():
    artifact = TurnArtifact.from_dict(dict(turn_id="t", session_id="s", input_modality="text", final_state="IDLE"))
    assert artifact.search is None


def test_confirmation_displays_every_query_without_style_truncation(tmp_path):
    queries = [("private topic " * 16 + str(index)) for index in range(3)]
    engine, _ = engine_at(tmp_path, Model(action="research", queries=queries, private=True))
    turn = engine.run_text_turn("Research my personal details")
    assert turn.search["outcome"] == "confirmation_required"
    assert all(query in turn.response_text for query in queries)
    assert not turn.search["attempts"]


def test_speech_excludes_citations_and_urls(tmp_path):
    engine, _ = engine_at(tmp_path)
    engine.tts.is_available = lambda: True
    played = []
    class Playback:
        def play(self, audio, sample_rate):
            played.append(audio)
    engine.playback_api = Playback()
    turn = engine.run_voice_turn(np.ones(10), 16000)
    assert turn.failure_reason is None and played
    assert engine.tts.spoken and "[S" not in engine.tts.spoken[0]
    assert "http" not in engine.tts.spoken[0]
    assert "[S1]" in turn.response_text


def test_cancellation_during_tts_never_starts_playback(tmp_path):
    engine, manager = engine_at(tmp_path)
    engine.tts.is_available = lambda: True
    def synthesize(text):
        active = engine.search_service.snapshot()
        engine.cancel_search(active["session_id"], active["turn_id"])
        return np.ones(10)
    engine.tts.synthesize = synthesize
    class Playback:
        def play(self, *args):
            pytest.fail("cancelled search must never speak")
    engine.playback_api = Playback()
    turn = engine.run_voice_turn(np.ones(10), 16000)
    assert turn.search["outcome"] == "cancelled"
    assert manager.turn_artifacts[0].search["sources"]


def test_tts_failure_preserves_search_evidence(tmp_path):
    engine, manager = engine_at(tmp_path)
    engine.tts.is_available = lambda: True
    def synthesize(text):
        raise RuntimeError("TTS unavailable")
    engine.tts.synthesize = synthesize
    turn = engine.run_voice_turn(np.ones(10), 16000)
    assert turn.failure_reason == "TTS unavailable"
    assert turn.search["outcome"] == "failed"
    assert manager.turn_artifacts[0].search["sources"]
