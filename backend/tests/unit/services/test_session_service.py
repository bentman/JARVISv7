from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.personality.schema import PersonalityExample, PersonalityProfile, PersonalityStyle, PersonalityTraits
from backend.app.services.session_service import SessionService


class _FakeSTT:
    device = "cpu"
    model_path = Path("models/stt/fake")

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        return "hello"

    def is_available(self) -> bool:
        return True


class _FakeTTS:
    device = "cpu"
    model_path = Path("models/tts/fake")

    def synthesize(self, text: str) -> np.ndarray:
        return np.zeros(1, dtype=np.float32)

    def sample_rate(self) -> int:
        return 16000

    def is_available(self) -> bool:
        return False


class _FakeLLM:
    def runtime_name(self) -> str:
        return "fake-llm"

    def is_available(self) -> bool:
        return True

    def generate(self, prompt: str, **kwargs: object) -> str:
        return f"response to {prompt}"


class _FakeWakeRuntime:
    def __init__(self, *, available: bool = True, detections: list[bool] | None = None, error: Exception | None = None) -> None:
        self.available = available
        self.detections = detections or []
        self.error = error
        self.last_score = 0.0
        self.threshold = 0.5

    def is_available(self) -> bool:
        return self.available

    def detect(self, audio_chunk: np.ndarray) -> bool:
        _ = audio_chunk
        if self.error is not None:
            self.last_score = 0.25
            raise self.error
        detected = self.detections.pop(0) if self.detections else False
        self.last_score = 0.8 if detected else 0.2
        return detected


def _engine(manager: SessionManager) -> TurnEngine:
    return TurnEngine(
        stt=_FakeSTT(),  # type: ignore[arg-type]
        tts=_FakeTTS(),  # type: ignore[arg-type]
        llm=_FakeLLM(),  # type: ignore[arg-type]
        personality=_personality(),
        session_manager=manager,
    )


def _personality(profile_id: str = "default", display_name: str = "Morgan") -> PersonalityProfile:
    return PersonalityProfile(
        profile_id=profile_id,
        display_name=display_name,
        description="Balanced assistant.",
        locale="en",
        system="Answer directly.",
        style=PersonalityStyle(
            max_words_default=120,
            structure="Answer first, then context.",
            do=("Lead with the answer.",),
            avoid=("Filler.",),
        ),
        traits=PersonalityTraits(warmth="medium", assertiveness="medium", detail="medium", humor="light"),
        examples=(PersonalityExample(user="Status?", assistant="Ready."),),
        generation={
            "temperature": 0.5,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.08,
            "max_tokens": 120,
            "stop": ["\nUser:", "\nAssistant:"],
        },
    )


def _service(tmp_path: Path) -> SessionService:
    manager = SessionManager(turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")

    def factory(new_manager: SessionManager) -> TurnEngine:
        new_manager.turns_base_dir = tmp_path / "turns"
        new_manager.sessions_base_dir = tmp_path / "sessions"
        return _engine(new_manager)

    return SessionService(session_manager=manager, engine=_engine(manager), engine_factory=factory)


def test_start_session_creates_active_session_id(tmp_path: Path) -> None:
    service = _service(tmp_path)
    previous_session_id = service.status().session_id
    status = service.start_session()
    assert status.active is True
    assert status.session_id
    assert status.session_id != previous_session_id
    assert status.turn_count == 0


def test_status_reports_active_session_and_turn_count(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = service.engine().run_text_turn("hello")
    status = service.status()
    assert result.session_id == status.session_id
    assert status.active is True
    assert status.turn_count == 1
    assert status.latest_turn is not None
    assert status.latest_turn.turn_id == result.turn_id
    assert status.latest_turn.input_modality == "text"
    assert status.latest_turn.runtime_context == {"llm": "fake-llm"}
    assert status.latest_turn.artifact_path == str(tmp_path / "turns" / result.session_id / f"{result.turn_id}.json")


def test_status_reports_no_latest_turn_before_artifact_exists(tmp_path: Path) -> None:
    service = _service(tmp_path)

    status = service.status()

    assert status.turn_count == 0
    assert status.latest_turn is None


def test_status_reports_voice_latest_turn_runtime_context(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = service.engine().run_voice_turn(np.zeros(160, dtype=np.float32), 16000)

    status = service.status()

    assert status.latest_turn is not None
    assert status.latest_turn.turn_id == result.turn_id
    assert status.latest_turn.input_modality == "voice"
    assert status.latest_turn.runtime_context == {
        "stt": "fake-stt/cpu",
        "llm": "fake-llm",
    }


def test_status_reports_tts_degraded_artifact_turn(tmp_path: Path) -> None:
    service = _service(tmp_path)
    session_id = service.status().session_id
    assert session_id is not None
    service.session_manager.record_turn_artifact(
        TurnArtifact(
            turn_id="tts-degraded-turn",
            session_id=session_id,
            input_modality="voice",
            final_state="IDLE",
            tts_degraded=True,
            tts_degraded_reason="TTS runtime is unavailable",
            runtime_context={"stt": "fake-stt/cpu", "llm": "fake-llm", "tts": "fake-tts/cpu"},
        )
    )

    status = service.status()

    assert status.latest_turn is not None
    assert status.latest_turn.turn_id == "tts-degraded-turn"
    assert status.latest_turn.degraded_reason == "TTS runtime is unavailable"
    assert status.latest_turn.runtime_context == {
        "stt": "fake-stt/cpu",
        "llm": "fake-llm",
        "tts": "fake-tts/cpu",
    }


def test_pre_engine_voice_failure_uses_live_status_without_latest_turn(tmp_path: Path) -> None:
    service = _service(tmp_path)

    service.begin_voice_invocation("ptt")
    service.record_voice_capture_diagnostics(
        source="ptt",
        stage="segment",
        diagnostics={"reason": "no-speech", "speech_started": False},
    )
    status = service.fail_voice_invocation("voice capture did not produce speech")

    assert status.state == "FAILED"
    assert status.failure_reason == "voice capture did not produce speech"
    assert status.invocation_source == "ptt"
    assert status.latest_turn is None
    assert status.voice_capture_diagnostics is not None
    assert status.voice_capture_diagnostics["speech_started"] is False


def test_status_reports_failed_artifact_turn(tmp_path: Path) -> None:
    service = _service(tmp_path)
    session_id = service.status().session_id
    assert session_id is not None
    service.session_manager.record_turn_artifact(
        TurnArtifact(
            turn_id="failed-turn",
            session_id=session_id,
            input_modality="text",
            final_state="FAILED",
            failure_reason="llm failed",
            runtime_context={"llm": "fake-llm"},
        )
    )

    status = service.status()

    assert status.latest_turn is not None
    assert status.latest_turn.turn_id == "failed-turn"
    assert status.latest_turn.final_state == "FAILED"
    assert status.latest_turn.failure_reason == "llm failed"
    assert status.latest_turn.runtime_context == {"llm": "fake-llm"}


def test_end_session_marks_service_inactive(tmp_path: Path) -> None:
    service = _service(tmp_path)
    session_id = service.status().session_id
    assert session_id is not None
    closed = service.end_session(session_id)
    status = service.status()
    assert closed.closed is True
    assert status.active is False
    assert status.session_id is None


def test_assert_active_session_accepts_matching_id(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.assert_active_session(service.status().session_id)


def test_assert_active_session_rejects_mismatched_id(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        service.assert_active_session("missing")
    except ValueError as exc:
        assert str(exc) == "session_id is not active"
    else:
        raise AssertionError("mismatched session id was accepted")


def test_engine_is_bound_to_active_session_manager(tmp_path: Path) -> None:
    service = _service(tmp_path)
    session_id = service.status().session_id
    result = service.engine().run_text_turn("bound session")
    assert result.session_id == session_id


def test_voice_transient_state_marker_accepts_only_realtime_snapshot_phases(tmp_path: Path) -> None:
    service = _service(tmp_path)

    status = service.mark_voice_transient_state(ConversationState.RESPONDING)

    assert status.state == "RESPONDING"
    try:
        service.mark_voice_transient_state(ConversationState.IDLE)
    except ValueError as exc:
        assert str(exc) == "state is not a transient voice snapshot state: IDLE"
    else:
        raise AssertionError("non-transient voice snapshot state was accepted")


def test_select_personality_updates_engine_without_resetting_session_or_wake(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.configure_wake_status(provider="openwakeword", available=True, reason="wake ready")
    before = service.status()
    selected = _personality("warm", "Avery")

    active = service.select_personality(selected)
    after = service.status()

    assert active == selected
    assert service.active_personality() == selected
    assert service.engine().personality == selected
    assert after.session_id == before.session_id
    assert after.turn_count == before.turn_count
    assert service.wake_status().reason == "wake ready"
    assert service.session_manager.profile_epoch == 1


def test_wake_status_defaults_to_configured_readiness(tmp_path: Path) -> None:
    service = _service(tmp_path)
    status = service.configure_wake_status(provider="openwakeword", available=True, reason="wake ready")
    assert status.provider == "openwakeword"
    assert status.available is True
    assert status.reason == "wake ready"
    assert status.active is False
    assert status.enabled is False
    assert status.monitoring is False
    assert status.last_detected is None
    assert status.detection_count == 0
    assert status.last_error is None


def test_process_wake_chunks_records_positive_detection(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.configure_wake_status(provider="openwakeword", available=True, reason="wake ready")
    runtime = _FakeWakeRuntime(detections=[False, True])
    status = service.process_wake_chunks(runtime, [np.zeros(4), np.ones(4)])
    assert status.available is True
    assert status.last_detected is not None
    assert status.detection_count == 1
    assert status.reason == "wake detected"
    assert status.last_score == 0.8
    assert status.threshold == 0.5


def test_process_wake_chunks_records_no_detection_without_error(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.configure_wake_status(provider="openwakeword", available=True, reason="wake ready")
    status = service.process_wake_chunks(_FakeWakeRuntime(detections=[False]), [np.zeros(4)])
    assert status.available is True
    assert status.last_detected is None
    assert status.detection_count == 0
    assert status.reason == "wake not detected"
    assert status.last_error is None
    assert status.last_score == 0.2
    assert status.threshold == 0.5


def test_wake_unavailable_degrades_to_ptt_only_without_error(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.configure_wake_status(provider="openwakeword", available=False, reason="wake unavailable")
    status = service.process_wake_chunks(_FakeWakeRuntime(available=False), [np.zeros(4)])
    assert status.available is False
    assert status.monitoring is False
    assert status.active is False
    assert status.enabled is False
    assert status.last_detected is None
    assert status.reason == "wake runtime is unavailable; PTT-only fallback is active"
    assert status.last_error is None


def test_wake_detection_error_records_last_error(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.configure_wake_status(provider="openwakeword", available=True, reason="wake ready")
    status = service.process_wake_chunks(_FakeWakeRuntime(error=RuntimeError("mic failed")), [np.zeros(4)])
    assert status.available is False
    assert status.monitoring is False
    assert status.active is False
    assert status.enabled is False
    assert status.last_detected is None
    assert status.reason == "wake detection error; PTT-only fallback is active"
    assert status.last_error == "mic failed"
    assert status.last_score == 0.25
    assert status.threshold == 0.5


def test_start_and_stop_wake_monitor_updates_status_without_readiness_change(tmp_path: Path) -> None:
    service = _service(tmp_path)
    started = service.start_wake_monitor(provider="openwakeword", available=True, reason="wake ready")

    assert started.available is True
    assert started.active is True
    assert started.enabled is True
    assert started.monitoring is True
    assert started.reason == "wake ready"

    stopped = service.stop_wake_monitor()
    assert stopped.available is True
    assert stopped.active is False
    assert stopped.enabled is False
    assert stopped.monitoring is False
    assert stopped.reason == "wake monitoring stopped; manual PTT is active"
