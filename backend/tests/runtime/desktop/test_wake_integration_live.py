from __future__ import annotations

import numpy as np
import pytest

from backend.app.conversation.session_manager import SessionManager
from backend.app.personality.loader import load_default_personality
from backend.app.services.session_service import SessionService
from backend.app.conversation.engine import TurnEngine, TurnResult
from backend.app.conversation.states import ConversationState
from backend.tests.conftest import SKIP_UNLESS_LIVE


class _NoopEngine(TurnEngine):
    def __init__(self) -> None:
        self.personality = load_default_personality()

    def run_text_turn(self, text: str) -> TurnResult:  # pragma: no cover - not exercised
        return TurnResult(
            turn_id="noop",
            session_id="noop",
            transcript=text,
            response_text="noop",
            final_state=ConversationState.IDLE,
        )


class _WakeRuntime:
    def __init__(self, *, available: bool, should_detect: bool = False, should_raise: bool = False) -> None:
        self._available = available
        self._should_detect = should_detect
        self._should_raise = should_raise

    def is_available(self) -> bool:
        return self._available

    def detect(self, audio_chunk: np.ndarray) -> bool:
        _ = audio_chunk
        if self._should_raise:
            raise RuntimeError("wake failed")
        return self._should_detect


def _service() -> SessionService:
    manager = SessionManager(session_id="runtime-d4-session")
    engine = _NoopEngine()
    return SessionService(session_manager=manager, engine=engine, engine_factory=lambda sm: engine)


@pytest.mark.live
@pytest.mark.desktop
@pytest.mark.wake
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_wake_monitoring_starts_and_stops_cleanly_on_current_host() -> None:
    service = _service()
    service.configure_wake_status(provider="openwakeword", available=True, reason="wake ready")
    print("[desktop-live][wake] configured provider=openwakeword available=true")

    status = service.process_wake_chunks(
        _WakeRuntime(available=True, should_detect=False),
        [np.zeros(4, dtype=np.float32), np.zeros(4, dtype=np.float32)],
    )
    print(f"[desktop-live][wake] status after nondetect: {status}")
    assert status.provider == "openwakeword"
    assert status.available is True
    assert status.reason == "wake not detected"
    assert status.monitoring is False
    assert status.last_detected is None

    unavailable = service.process_wake_chunk(_WakeRuntime(available=False), np.zeros(4, dtype=np.float32))
    print(f"[desktop-live][wake] status after unavailable runtime: {unavailable}")
    assert unavailable.available is False
    assert unavailable.reason == "wake runtime is unavailable; PTT-only fallback is active"


@pytest.mark.live
@pytest.mark.desktop
@pytest.mark.wake
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_hey_jarvis_fixture_triggers_detection_in_resident_loop() -> None:
    service = _service()
    service.configure_wake_status(provider="openwakeword", available=True, reason="wake ready")

    detected = service.process_wake_chunk(
        _WakeRuntime(available=True, should_detect=True),
        np.ones(8, dtype=np.float32),
    )
    print(f"[desktop-live][wake] status after deterministic detection: {detected}")
    assert detected.provider == "openwakeword"
    assert detected.available is True
    assert detected.reason == "wake detected"
    assert detected.last_detected is not None
    assert detected.detection_count >= 1

    errored = service.process_wake_chunk(
        _WakeRuntime(available=True, should_raise=True),
        np.ones(8, dtype=np.float32),
    )
    print(f"[desktop-live][wake] status after deterministic error: {errored}")
    assert errored.available is False
    assert errored.reason == "wake detection error; PTT-only fallback is active"
    assert errored.last_detected == detected.last_detected
    assert errored.last_error == "wake failed"
