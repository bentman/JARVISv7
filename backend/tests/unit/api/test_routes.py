from __future__ import annotations

import io
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from backend.app.api.app import ApiState, create_app
from backend.app.cache.manager import CacheManager
from backend.app.conversation.engine import TurnResult
from backend.app.conversation.states import ConversationState
from backend.app.core.capabilities import CapabilityFlags, FullCapabilityReport, HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.personality.schema import PersonalityProfile
from backend.app.services.session_service import SessionService


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
    personality = PersonalityProfile(
        profile_id="default",
        display_name="JARVIS",
        tone="professional",
        brevity="concise",
        formality="semi-formal",
    )

    def run_text_turn(self, text: str) -> TurnResult:
        return TurnResult(
            turn_id="turn-text",
            session_id="session-test",
            transcript=text.strip(),
            response_text="text response",
            final_state=ConversationState.IDLE,
            tool_results=[
                {
                    "tool_name": "time",
                    "tool_input": {},
                    "tool_output": "2026-05-03T00:00:00Z",
                    "success": True,
                    "error": None,
                }
            ],
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
    state = ApiState(
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
        session_service=None,  # type: ignore[arg-type]
        cache_manager=CacheManager(),
    )
    state.session_service = SessionService(
        session_manager=state.session_manager,  # type: ignore[arg-type]
        engine=state.engine,
        engine_factory=lambda manager: _FakeEngine(),  # type: ignore[arg-type]
    )
    return state


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


def test_personality_list_returns_available_profiles() -> None:
    response = _client().get("/personality/list")
    payload = response.json()

    assert response.status_code == 200
    assert payload["active_profile_id"] == "default"
    assert {profile["profile_id"] for profile in payload["profiles"]} >= {"default", "concise", "warm"}


def test_personality_select_switches_active_profile_without_session_reset() -> None:
    client = _client()
    before = client.get("/session/status").json()

    response = client.post("/personality/select", json={"profile_id": "warm"})
    after = client.get("/session/status").json()
    readiness = client.get("/readiness").json()

    assert response.status_code == 200
    assert response.json()["active"]["profile_id"] == "warm"
    assert after["session_id"] == before["session_id"]
    assert after["turn_count"] == before["turn_count"]
    assert readiness["active_personality_profile_id"] == "warm"
    assert client.app.state.jarvis_state.session_service.engine().personality.profile_id == "warm"


def test_personality_select_rejects_unknown_profile() -> None:
    response = _client().post("/personality/select", json={"profile_id": "missing"})

    assert response.status_code == 404


def test_session_create_returns_session_id() -> None:
    response = _client().post("/session/create", json={})
    assert response.status_code == 200
    assert response.json()["session_id"]
    assert response.json()["state"] == "IDLE"


def test_session_status_returns_active_session() -> None:
    client = _client()
    session_id = client.app.state.jarvis_state.session_service.status().session_id
    response = client.get("/session/status")
    assert response.status_code == 200
    assert response.json() == {"session_id": session_id, "active": True, "state": "IDLE", "turn_count": 0}


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
    assert payload["tool_calls"][0]["tool_name"] == "time"


def test_voice_turn_response_tool_calls_none_when_absent() -> None:
    response = _client().post(
        "/task/voice",
        content=_wav_bytes(),
        headers={"content-type": "audio/wav"},
    )
    assert response.status_code == 200
    assert response.json()["tool_calls"] is None


def test_text_turn_accepts_active_session_id() -> None:
    client = _client()
    session_id = client.app.state.jarvis_state.session_service.status().session_id
    response = client.post("/task/text", json={"text": "hello", "session_id": session_id})
    assert response.status_code == 200
    assert response.json()["session_id"] == "session-test"


def test_text_turn_rejects_mismatched_session_id() -> None:
    response = _client().post("/task/text", json={"text": "hello", "session_id": "missing"})
    assert response.status_code == 400
    assert response.json()["detail"] == "session_id is not active"


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
    assert response.json() == {
        "provider": "openwakeword",
        "available": True,
        "reason": "wake ready",
        "monitoring": False,
        "last_detected": False,
        "detection_count": 0,
        "last_error": None,
    }


def test_wake_status_reflects_deterministic_detection_state() -> None:
    client = _client()

    class WakeRuntime:
        def is_available(self) -> bool:
            return True

        def detect(self, audio_chunk: np.ndarray) -> bool:
            _ = audio_chunk
            return True

    client.app.state.jarvis_state.session_service.configure_wake_status(
        provider="openwakeword",
        available=True,
        reason="wake ready",
    )
    client.app.state.jarvis_state.session_service.process_wake_chunk(WakeRuntime(), np.zeros(4))
    response = client.get("/status/wake")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openwakeword"
    assert payload["available"] is True
    assert payload["reason"] == "wake detected"
    assert payload["last_detected"] is True
    assert payload["detection_count"] == 1
    assert payload["last_error"] is None


def test_wake_status_reflects_error_state() -> None:
    client = _client()

    class WakeRuntime:
        def is_available(self) -> bool:
            return True

        def detect(self, audio_chunk: np.ndarray) -> bool:
            _ = audio_chunk
            raise RuntimeError("wake failed")

    client.app.state.jarvis_state.session_service.configure_wake_status(
        provider="openwakeword",
        available=True,
        reason="wake ready",
    )
    client.app.state.jarvis_state.session_service.process_wake_chunk(WakeRuntime(), np.zeros(4))
    response = client.get("/status/wake")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["reason"] == "wake detection error; PTT-only fallback is active"
    assert payload["last_detected"] is False
    assert payload["detection_count"] == 0
    assert payload["last_error"] == "wake failed"