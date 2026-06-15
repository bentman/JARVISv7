from __future__ import annotations

import io
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from backend.app.api.routes import config as config_route
from backend.app.api import service_status
from backend.app.agents.ledger import AgentLedger, AgentLedgerRecord
from backend.app.api.app import ApiState, create_app
from backend.app.cache.manager import CacheManager
from backend.app.conversation.engine import TurnResult
from backend.app.conversation.states import ConversationState
from backend.app.core.capabilities import CapabilityFlags, FullCapabilityReport, HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.personality.schema import PersonalityProfile
from backend.app.services.session_service import SessionService
from backend.app.services.resident_voice_invocation import ResidentVoiceInvocationService
from backend.app.services.wake_monitor import WakeMonitorService


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


class _FakeWakeRuntime:
    last_score = 0.0
    threshold = 0.5

    def is_available(self) -> bool:
        return True

    def detect(self, audio_chunk: np.ndarray) -> bool:
        _ = audio_chunk
        self.last_score = 0.1
        return False


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
        resident_voice=None,  # type: ignore[arg-type]
        wake_monitor=None,  # type: ignore[arg-type]
        cache_manager=CacheManager(),
    )
    state.session_service = SessionService(
        session_manager=state.session_manager,  # type: ignore[arg-type]
        engine=state.engine,
        engine_factory=lambda manager: _FakeEngine(),  # type: ignore[arg-type]
    )
    state.resident_voice = ResidentVoiceInvocationService(
        session_service=state.session_service,
        engine_provider=lambda: state.session_service.engine(),
        audio_capture=lambda: (np.ones(8, dtype=np.float32), 16000),
    )
    state.wake_monitor = WakeMonitorService(
        session_service=state.session_service,
        runtime_factory=lambda: _FakeWakeRuntime(),  # type: ignore[arg-type]
        chunk_source=_wake_source,
        invocation_callback=state.resident_voice.enqueue,
    )
    state.resident_voice.set_invocation_hooks(
        before_invocation=state.wake_monitor.pause_for_voice_invocation,
        after_invocation=state.wake_monitor.resume_after_voice_invocation,
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


def _wake_source(stop_event):
    while not stop_event.is_set():
        time.sleep(0.01)
        yield np.zeros(4)


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


def test_readiness_returns_additive_service_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.api.routes.readiness.collect_service_statuses",
        lambda: {
            "redis": service_status.ServiceStatus(reachable=True, reason="reachable"),
            "searxng": service_status.ServiceStatus(reachable=True, reason="container reachable; json usable"),
        },
    )

    response = _client().get("/readiness")
    payload = response.json()

    assert response.status_code == 200
    assert payload["services"]["redis"] == {"reachable": True, "reason": "reachable"}
    assert payload["services"]["searxng"] == {"reachable": True, "reason": "container reachable; json usable"}
    assert set(payload["families"]) == {"stt", "tts", "llm", "wake"}


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
    assert response.json() == {
        "session_id": session_id,
        "active": True,
        "state": "IDLE",
        "turn_count": 0,
        "last_transcript": None,
        "last_response": None,
        "failure_reason": None,
        "invocation_source": None,
        "tts_output_device": None,
    }


def test_session_ptt_queues_resident_voice_invocation() -> None:
    client = _client()

    response = client.post("/session/ptt")

    assert response.status_code == 200
    deadline = time.monotonic() + 1.0
    payload = {}
    while time.monotonic() < deadline:
        payload = client.get("/session/status").json()
        if payload["last_transcript"] == "hello voice":
            break
        time.sleep(0.01)
    assert payload["state"] == "IDLE"
    assert payload["last_transcript"] == "hello voice"
    assert payload["last_response"] == "voice response"
    assert payload["failure_reason"] is None
    assert payload["invocation_source"] == "ptt"


def test_session_ptt_works_when_wake_is_unavailable() -> None:
    client = _client()
    client.app.state.jarvis_state.readiness["wake"] = ("cpu", False, "wake unavailable")

    response = client.post("/session/ptt")

    assert response.status_code == 200
    deadline = time.monotonic() + 1.0
    payload = {}
    while time.monotonic() < deadline:
        payload = client.get("/session/status").json()
        if payload["last_transcript"] == "hello voice":
            break
        time.sleep(0.01)
    assert payload["state"] == "IDLE"
    assert payload["last_transcript"] == "hello voice"
    assert payload["last_response"] == "voice response"
    assert payload["failure_reason"] is None
    assert payload["invocation_source"] == "ptt"


def test_session_ptt_works_while_wake_monitoring_is_enabled() -> None:
    client = _client()
    wake_started = client.post("/status/wake/start")
    assert wake_started.status_code == 200
    assert wake_started.json()["active"] is True

    response = client.post("/session/ptt")

    assert response.status_code == 200
    deadline = time.monotonic() + 1.0
    payload = {}
    while time.monotonic() < deadline:
        payload = client.get("/session/status").json()
        if payload["last_transcript"] == "hello voice":
            break
        time.sleep(0.01)
    assert payload["state"] == "IDLE"
    assert payload["last_transcript"] == "hello voice"
    assert payload["last_response"] == "voice response"
    assert payload["failure_reason"] is None
    assert payload["invocation_source"] == "ptt"

    wake_status = client.get("/status/wake").json()
    assert wake_status["available"] is True
    assert wake_status["active"] is True


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
    assert payload["stt_device"] in {"cpu", "cuda", "directml", "qnn", None}


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


def test_diagnostics_audio_ingress_returns_backend_capture_diagnostics(monkeypatch) -> None:
    from backend.app.services.voice_service import AudioIngressDiagnostics

    monkeypatch.setattr(
        "backend.app.api.routes.diagnostics.diagnose_audio_ingress",
        lambda duration_s: AudioIngressDiagnostics(
            usable=True,
            sample_rate=16000,
            sample_count=1600,
            dtype="float32",
            duration=duration_s,
            input_device="3: USB mic",
            rms=0.12,
            peak=0.4,
            reason="capture succeeded with non-silent audio",
        ),
    )

    response = _client().post("/diagnostics/audio-ingress?duration_s=0.5")

    assert response.status_code == 200
    assert response.json() == {
        "usable": True,
        "sample_rate": 16000,
        "sample_count": 1600,
        "dtype": "float32",
        "duration": 0.5,
        "input_device": "3: USB mic",
        "rms": 0.12,
        "peak": 0.4,
        "reason": "capture succeeded with non-silent audio",
    }


def test_agents_status_is_disabled_read_only() -> None:
    response = _client().get("/agents/status")
    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "read_only": True,
        "reason": "Agent boundary is disabled by policy",
        "allowed_roles": ["planner", "executor", "critic", "curator", "learner"],
        "allowed_tools": [],
    }


def test_agents_trace_endpoint_is_read_only(monkeypatch, tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    ledger = AgentLedger(ledger_path)
    ledger.append(
        AgentLedgerRecord(
            record_id="record-1",
            trace_id="trace-1",
            role_id="planner",
            record_type="plan",
            payload={"dry_run": True},
            created_at="2026-06-15T00:00:00+00:00",
        )
    )
    monkeypatch.setattr("backend.app.api.routes.agents.AgentLedger", lambda: AgentLedger(ledger_path))

    response = _client().get("/agents/traces/trace-1")

    assert response.status_code == 200
    assert response.json() == {
        "trace_id": "trace-1",
        "read_only": True,
        "records": [
            {
                "record_id": "record-1",
                "trace_id": "trace-1",
                "record_type": "plan",
                "payload": {"dry_run": True},
                "role_id": "planner",
                "session_id": None,
                "turn_id": None,
                "parent_record_id": None,
                "created_at": "2026-06-15T00:00:00+00:00",
            }
        ],
    }


def test_wake_status_uses_readiness_without_starting_monitor() -> None:
    response = _client().get("/status/wake")
    assert response.status_code == 200
    assert response.json() == {
        "provider": "openwakeword",
        "available": True,
        "reason": "wake ready",
        "active": False,
        "enabled": False,
        "monitoring": False,
        "last_detected": None,
        "detection_count": 0,
        "last_error": None,
        "last_score": None,
        "threshold": None,
    }


def test_wake_monitor_start_stop_and_toggle_endpoints() -> None:
    client = _client()

    started = client.post("/status/wake/start")
    assert started.status_code == 200
    assert started.json()["active"] is True
    assert started.json()["enabled"] is True
    assert started.json()["monitoring"] is True

    stopped = client.post("/status/wake/stop")
    assert stopped.status_code == 200
    assert stopped.json()["active"] is False
    assert stopped.json()["enabled"] is False
    assert stopped.json()["monitoring"] is False

    toggled_on = client.post("/status/wake/toggle")
    assert toggled_on.status_code == 200
    assert toggled_on.json()["active"] is True

    toggled_off = client.post("/status/wake/toggle")
    assert toggled_off.status_code == 200
    assert toggled_off.json()["active"] is False


def test_wake_status_reflects_deterministic_detection_state() -> None:
    client = _client()

    class WakeRuntime:
        last_score = 0.0
        threshold = 0.5

        def is_available(self) -> bool:
            return True

        def detect(self, audio_chunk: np.ndarray) -> bool:
            _ = audio_chunk
            self.last_score = 0.7
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
    assert payload["last_detected"] is not None
    assert payload["detection_count"] == 1
    assert payload["last_error"] is None
    assert payload["last_score"] == 0.7
    assert payload["threshold"] == 0.5


def test_wake_status_reflects_error_state() -> None:
    client = _client()

    class WakeRuntime:
        last_score = 0.0
        threshold = 0.5

        def is_available(self) -> bool:
            return True

        def detect(self, audio_chunk: np.ndarray) -> bool:
            _ = audio_chunk
            self.last_score = 0.25
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
    assert payload["active"] is False
    assert payload["enabled"] is False
    assert payload["last_detected"] is None
    assert payload["detection_count"] == 0
    assert payload["last_error"] == "wake failed"
    assert payload["last_score"] == 0.25
    assert payload["threshold"] == 0.5


def test_operator_config_returns_allowlisted_fields_and_masks_secret(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "USE_OLLAMA=true\n"
        "OLLAMA_BASE_URL=http://localhost:11434\n"
        "TAVILY_API_KEY=secret-token\n"
        "UNRELATED=value\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_route, "ENV_FILE", env_file)

    response = _client().get("/config/operator")
    payload = response.json()

    assert response.status_code == 200
    fields = {field["key"]: field for field in payload["fields"]}
    assert set(fields) == {spec.key for spec in config_route.OPERATOR_FIELD_SPECS}
    assert fields["USE_OLLAMA"]["value"] == "true"
    assert fields["USE_OLLAMA"]["editable"] is True
    assert fields["USE_OLLAMA"]["restart_required"] is True
    assert fields["USE_OLLAMA"]["description"]
    assert fields["TAVILY_API_KEY"]["secret"] is True
    assert fields["TAVILY_API_KEY"]["has_value"] is True
    assert fields["TAVILY_API_KEY"]["value"] == "***"
    assert "secret-token" not in str(payload)
    assert "UNRELATED" not in fields


def test_operator_config_missing_env_returns_409_without_creating_file(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    monkeypatch.setattr(config_route, "ENV_FILE", env_file)

    response = _client().get("/config/operator")

    assert response.status_code == 409
    assert response.json()["detail"] == {"error": "env_file_missing"}
    assert not env_file.exists()


def test_operator_config_write_rejects_non_allowlisted_keys_and_preserves_unknown_lines(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# leading comment\n"
        "USE_OLLAMA=true\n"
        "UNRELATED=value\n"
        "TAVILY_API_KEY=old-secret\n"
        "REDIS_PORT=6379\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_route, "ENV_FILE", env_file)

    response = _client().post(
        "/config/operator",
        json={"fields": {"USE_OLLAMA": "false", "TAVILY_API_KEY": "new-secret", "NOT_ALLOWED": "x"}},
    )

    assert response.status_code == 200
    assert response.json() == {
        "written": ["USE_OLLAMA", "TAVILY_API_KEY"],
        "rejected": [{"key": "NOT_ALLOWED", "reason": "not_allowlisted"}],
    }
    assert env_file.read_text(encoding="utf-8") == (
        "# leading comment\n"
        "USE_OLLAMA=false\n"
        "UNRELATED=value\n"
        "TAVILY_API_KEY=new-secret\n"
        "REDIS_PORT=6379\n"
    )


def test_operator_config_write_appends_missing_allowlisted_key_without_creating_missing_env(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("USE_OLLAMA=true\n", encoding="utf-8")
    monkeypatch.setattr(config_route, "ENV_FILE", env_file)

    response = _client().post("/config/operator", json={"fields": {"REDIS_HOST": "127.0.0.1"}})

    assert response.status_code == 200
    assert response.json() == {"written": ["REDIS_HOST"], "rejected": []}
    assert env_file.read_text(encoding="utf-8") == "USE_OLLAMA=true\nREDIS_HOST=127.0.0.1\n"
