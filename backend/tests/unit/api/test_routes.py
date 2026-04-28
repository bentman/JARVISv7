from __future__ import annotations

import io
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from backend.app.api.app import ApiState, create_app
from backend.app.conversation.engine import TurnResult
from backend.app.conversation.states import ConversationState
from backend.app.core.capabilities import CapabilityFlags, FullCapabilityReport, HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.personality.schema import PersonalityProfile


class _FakeSTT:
    device = "cpu"
    model_path = Path("models/stt/fake")

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        return "hello voice"

    def is_available(self) -> bool:
        return True


class _FakeTTS:
    device = "cpu"
    model_path = Path("models/tts/fake")

    def synthesize(self, text: str) -> np.ndarray:
        return np.zeros(8, dtype=np.float32)

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


@dataclass(slots=True)
class _FakeSessionManager:
    session_id: str = "session-test"
    turn_artifacts: list[object] = field(default_factory=list)

    def close_session(self, final_state: str = "IDLE") -> Path:
        _ = final_state
        return Path("data/sessions/session-test.json")


class _FakeEngine:
    def run_text_turn(self, text: str) -> TurnResult:
        return TurnResult(
            turn_id="turn-text",
            session_id="session-test",
            transcript=text.strip(),
            response_text="text response",
            final_state=ConversationState.IDLE,
        )

    def run_voice_turn(self, audio: np.ndarray, sample_rate: int) -> TurnResult:
        assert sample_rate == 16000
        assert audio.size > 0
        return TurnResult(
            turn_id="turn-voice",
            session_id="session-test",
            transcript="hello voice",
            response_text="voice response",
            final_state=ConversationState.IDLE,
            tts_degraded=True,
            tts_degraded_reason="TTS runtime is unavailable",
        )


def _state() -> ApiState:
    profile = HardwareProfile(
        os_name="windows",
        arch="amd64",
        profile_id="profile-test",
        profiled_at="2026-04-28T00:00:00Z",
    )
    flags = CapabilityFlags(
        supports_local_stt=True,
        supports_local_tts=True,
        supports_local_llm=True,
        supports_wake_word=True,
        requires_degraded_mode=False,
    )
    session_manager = _FakeSessionManager()
    return ApiState(
        report=FullCapabilityReport(profile=profile, flags=flags),
        profile=profile,
        extras=["dev"],
        preflight=PreflightResult(tokens=["import:onnxruntime"], dll_discovery_log=[], probe_errors={}),
        readiness={
            "stt": ("cpu", True, "stt ready"),
            "tts": ("cpu", True, "tts ready"),
            "llm": ("cpu", True, "llm ready"),
            "wake": ("cpu", True, "wake ready"),
        },
        personality=PersonalityProfile(
            profile_id="default",
            display_name="JARVIS",
            tone="professional",
            brevity="concise",
            formality="semi-formal",
        ),
        stt=_FakeSTT(),  # type: ignore[arg-type]
        tts=_FakeTTS(),  # type: ignore[arg-type]
        llm=_FakeLLM(),  # type: ignore[arg-type]
        session_manager=session_manager,  # type: ignore[arg-type]
        engine=_FakeEngine(),  # type: ignore[arg-type]
    )


def _client() -> TestClient:
    return TestClient(create_app(_state()))


def _wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes((np.zeros(160, dtype="<i2")).tobytes())
    return buffer.getvalue()


def test_health_returns_200() -> None:
    response = _client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "jarvisv7-backend"}


def test_readiness_returns_family_readiness() -> None:
    response = _client().get("/readiness")
    payload = response.json()
    assert response.status_code == 200
    assert payload["profile_id"] == "profile-test"
    assert set(payload["families"]) == {"stt", "tts", "llm", "wake"}
    assert payload["families"]["wake"]["ready"] is True


def test_session_create_returns_session_id() -> None:
    response = _client().post("/session/create", json={})
    assert response.status_code == 200
    assert response.json()["session_id"]
    assert response.json()["state"] == "IDLE"


def test_session_close_returns_closed() -> None:
    client = _client()
    session_id = client.app.state.jarvis_state.session_manager.session_id
    response = client.post("/session/close", json={"session_id": session_id})
    assert response.status_code == 200
    assert response.json()["closed"] is True


def test_session_close_rejects_unknown_session_id() -> None:
    response = _client().post("/session/close", json={"session_id": "missing"})
    assert response.status_code == 404


def test_text_turn_returns_turn_result() -> None:
    response = _client().post("/task/text", json={"text": "hello"})
    payload = response.json()
    assert response.status_code == 200
    assert payload["turn_id"] == "turn-text"
    assert payload["response_text"] == "text response"


def test_text_turn_rejects_empty_text() -> None:
    response = _client().post("/task/text", json={"text": "   "})
    assert response.status_code == 400


def test_voice_turn_accepts_wav_bytes_and_returns_result() -> None:
    response = _client().post(
        "/task/voice",
        content=_wav_bytes(),
        headers={"content-type": "audio/wav"},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["turn_id"] == "turn-voice"
    assert payload["tts_degraded"] is True


def test_diagnostics_profile_returns_profile_payload() -> None:
    response = _client().get("/diagnostics/profile")
    payload = response.json()
    assert response.status_code == 200
    assert payload["profile"]["arch"] == "amd64"
    assert payload["flags"]["supports_local_stt"] is True


def test_diagnostics_preflight_returns_tokens_and_errors() -> None:
    response = _client().get("/diagnostics/preflight")
    payload = response.json()
    assert response.status_code == 200
    assert payload["tokens"] == ["import:onnxruntime"]
    assert payload["probe_errors"] == {}


def test_agents_status_is_disabled_read_only() -> None:
    response = _client().get("/agents/status")
    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "read_only": True,
        "reason": "Group I not implemented",
    }


def test_wake_status_uses_readiness_without_starting_monitor() -> None:
    response = _client().get("/status/wake")
    assert response.status_code == 200
    assert response.json() == {"provider": "openwakeword", "available": True, "reason": "wake ready"}