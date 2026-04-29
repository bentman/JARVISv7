from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.personality.schema import PersonalityProfile
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


def _engine(manager: SessionManager) -> TurnEngine:
    return TurnEngine(
        stt=_FakeSTT(),  # type: ignore[arg-type]
        tts=_FakeTTS(),  # type: ignore[arg-type]
        llm=_FakeLLM(),  # type: ignore[arg-type]
        personality=PersonalityProfile(
            profile_id="default",
            display_name="JARVIS",
            tone="professional",
            brevity="concise",
            formality="semi-formal",
        ),
        session_manager=manager,
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
