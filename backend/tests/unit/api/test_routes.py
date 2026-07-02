from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from backend.app.agents.ledger import AgentLedger, AgentLedgerRecord
from backend.app.api import app as app_module
from backend.app.api import service_status
from backend.app.api.app import ApiState, create_app
from backend.app.api.routes import config as config_route
from backend.app.cache.manager import CacheManager
from backend.app.conversation.engine import TurnResult
from backend.app.conversation.states import ConversationState
from backend.app.core.capabilities import CapabilityFlags, FullCapabilityReport, HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.personality.schema import PersonalityProfile
from backend.app.routing.runtime_selector import SelectionTrace
from backend.app.services.startup_context import StartupContext
from backend.app.services.resident_voice_invocation import ResidentVoiceInvocationService
from backend.app.services.session_service import SessionService
from backend.app.services.wake_monitor import WakeMonitorService
from fastapi.testclient import TestClient


class _FakeSTT:
    device = "cpu"
    model_path = Path("models/stt/fake")

    def runtime_name(self) -> str:
        return "fake-stt"

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        return "hello voice"

    def is_available(self) -> bool:
        return True


class _FakeTTS:
    device = "cpu"
    model_path = Path("models/tts/fake")

    def runtime_name(self) -> str:
        return "fake-tts"

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


class _FakeLocalLLM(_FakeLLM):
    model = "assistant-small-q4"
    route = "voice_chat"
    serve_profile_id = "windows_amd64_gpu_nvidia_cuda"
    accelerator = "gpu.cuda"
    base_url = "http://127.0.0.1:8080"
    selected_reason = "selected current-host gpu.cuda serve profile windows_amd64_gpu_nvidia_cuda"
    model_mode = "prod"
    model_policy = "auto"
    model_role = "balanced"
    model_selection_reason = "policy auto mapped windows_amd64_gpu_nvidia_cuda to role balanced"
    reason = "llama.cpp /v1/models reachable"

    def runtime_name(self) -> str:
        return "llama.cpp"

    def is_available(self) -> bool:
        self.reason = "llama.cpp /v1/models reachable"
        return True


class _FakeOllamaLLM(_FakeLLM):
    def runtime_name(self) -> str:
        return "ollama"


class _DeadLocalLLM(_FakeLocalLLM):
    reason = "managed llama.cpp sidecar is not running"

    def is_available(self) -> bool:
        self.reason = "managed llama.cpp sidecar is not running"
        return False


class _FakeSidecar:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


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


def test_build_startup_state_uses_runtime_selector_for_llm(monkeypatch) -> None:
    profile = HardwareProfile(os_name="windows", arch="amd64", profile_id="profile-test")
    report = FullCapabilityReport(profile=profile, flags=CapabilityFlags())
    preflight = PreflightResult(tokens=["import:ollama"], dll_discovery_log=[], probe_errors={})
    policy = {"llm": {"cloud_enabled": False}}
    selected_llm = _FakeLLM()
    prepared_local = _FakeLocalLLM()
    prepare_calls: list[tuple[HardwareProfile, PreflightResult, CapabilityFlags]] = []
    selector_calls: list[tuple[dict[str, object], PreflightResult, HardwareProfile, object]] = []

    monkeypatch.setattr(
        app_module,
        "load_startup_context",
        lambda: StartupContext(
            report=report,
            profile=profile,
            extras=["dev"],
            preflight=preflight,
            readiness={
                "stt": ("cpu", True, "stt ready"),
                "tts": ("cpu", True, "tts ready"),
                "llm": ("cpu", True, "llm ready"),
                "wake": ("cpu", True, "wake ready"),
            },
        ),
    )
    monkeypatch.setattr(app_module, "_load_runtime_policy", lambda: policy)
    monkeypatch.setattr(app_module, "load_default_personality", lambda: _FakeEngine.personality)
    monkeypatch.setattr(app_module, "select_stt_runtime", lambda preflight, profile: _FakeSTT())
    monkeypatch.setattr(app_module, "select_tts_runtime", lambda preflight, profile: _FakeTTS())

    def fake_prepare_managed_local_llm(runtime_profile, runtime_preflight, *, flags):
        prepare_calls.append((runtime_profile, runtime_preflight, flags))
        return type(
            "PreparedLocal",
            (),
            {"runtime": prepared_local, "sidecar": None, "degraded_reason": None},
        )()

    def fake_select_llm(runtime_policy, runtime_preflight, runtime_profile, *, local=None):
        selector_calls.append((runtime_policy, runtime_preflight, runtime_profile, local))
        return selected_llm, object()

    monkeypatch.setattr(app_module, "prepare_managed_local_llm", fake_prepare_managed_local_llm)
    monkeypatch.setattr(app_module, "select_llm", fake_select_llm)

    state = app_module.build_startup_state()

    assert state.llm is selected_llm
    assert prepare_calls == [(profile, preflight, report.flags)]
    assert selector_calls == [(policy, preflight, profile, prepared_local)]
    assert state.resident_audio_stream is not None
    assert state.utterance_segmenter is not None
    assert state.engine.barge_in_detector is not None
    assert state.engine.interruption_audio_chunks is None


def test_build_engine_injects_resident_interruption_chunks_when_stream_running() -> None:
    state = _state()
    assert state.resident_audio_stream is None

    from backend.app.services.audio_stream import ResidentAudioStream

    def blocking_source(stop_event):
        while not stop_event.is_set():
            time.sleep(0.01)
            if False:
                yield np.array([], dtype=np.float32)

    stream = ResidentAudioStream(chunk_source_factory=blocking_source)
    stream.start()
    try:
        state.resident_audio_stream = stream
        engine = app_module.build_engine(state)  # type: ignore[arg-type]
    finally:
        stream.stop()

    assert engine.barge_in_detector is not None
    assert engine.interruption_audio_chunks is not None


def test_app_shutdown_stops_managed_local_llm_sidecar() -> None:
    state = _state()
    sidecar = _FakeSidecar()
    state.local_llm_sidecar = sidecar  # type: ignore[assignment]

    with TestClient(create_app(state)) as client:
        assert client.get("/health").status_code == 200

    assert sidecar.stop_calls == 1
    assert state.local_llm_sidecar is None


def test_app_shutdown_stops_resident_audio_stream() -> None:
    state = _state()
    from backend.app.services.audio_stream import ResidentAudioStream

    state.resident_audio_stream = ResidentAudioStream(chunk_source_factory=_wake_source)

    with TestClient(create_app(state)) as client:
        response = client.post("/status/resident-voice/start")
        assert response.status_code == 200
        assert state.resident_audio_stream.status().running is True

    assert state.resident_audio_stream.status().running is False


def test_app_shutdown_tolerates_missing_managed_local_llm_sidecar() -> None:
    state = _state()
    state.local_llm_sidecar = None

    with TestClient(create_app(state)) as client:
        assert client.get("/health").status_code == 200

    assert state.local_llm_sidecar is None


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
    assert payload["resident_audio"]["mode"] == "ptt+wake"
    assert payload["resident_audio"]["stream_present"] is False
    assert payload["resident_audio"]["vad_configured"] is False
    assert payload["families"]["stt"]["runtime"] == "fake-stt"
    assert payload["families"]["tts"]["runtime"] == "fake-tts"
    assert payload["families"]["llm"]["runtime"] == "fake-llm"
    assert payload["families"]["wake"]["runtime"] == "openwakeword"
    assert payload["families"]["wake"]["ready"] is True


def test_readiness_returns_llm_selection_trace_for_local_runtime() -> None:
    state = _state()
    state.llm = _FakeLocalLLM()  # type: ignore[assignment]
    state.llm_trace = SelectionTrace(
        runtime_name="llama.cpp",
        reason="local llama.cpp available",
        model_id="assistant-small-q4",
        route="voice_chat",
        serve_profile_id="windows_amd64_cpu",
        accelerator="cpu",
        base_url="http://127.0.0.1:8080",
        selected_reason="selected current-host CPU serve profile windows_amd64_cpu",
        model_mode="prod",
        model_policy="auto",
        model_role="portable",
        model_selection_reason="policy auto mapped windows_amd64_cpu to role portable",
    )

    response = TestClient(create_app(state)).get("/readiness")
    llm = response.json()["families"]["llm"]

    assert response.status_code == 200
    assert llm["runtime"] == "llama.cpp"
    assert llm["ready"] is True
    assert llm["model"] == "assistant-small-q4"
    assert llm["route"] == "voice_chat"
    assert llm["serve_profile_id"] == "windows_amd64_gpu_nvidia_cuda"
    assert llm["accelerator"] == "gpu.cuda"
    assert llm["base_url"] == "http://127.0.0.1:8080"
    assert llm["selected_reason"] == "selected current-host gpu.cuda serve profile windows_amd64_gpu_nvidia_cuda"
    assert llm["degraded_reason"] == "llama.cpp /v1/models reachable"
    assert llm["model_mode"] == "prod"
    assert llm["model_policy"] == "auto"
    assert llm["model_role"] == "balanced"
    assert "role balanced" in llm["model_selection_reason"]


def test_readiness_refreshes_dead_local_llm_instead_of_using_stale_trace() -> None:
    state = _state()
    state.llm = _DeadLocalLLM()  # type: ignore[assignment]
    state.llm_trace = SelectionTrace(
        runtime_name="llama.cpp",
        reason="local llama.cpp available",
        model_id="assistant-small-q4",
        route="voice_chat",
        serve_profile_id="windows_amd64_cpu",
        accelerator="cpu",
        base_url="http://127.0.0.1:8080",
        selected_reason="selected current-host CPU serve profile windows_amd64_cpu",
        degraded_reason="llama.cpp /v1/models reachable",
    )

    response = TestClient(create_app(state)).get("/readiness")
    llm = response.json()["families"]["llm"]

    assert response.status_code == 200
    assert llm["runtime"] == "llama.cpp"
    assert llm["ready"] is False
    assert llm["reason"] == "managed llama.cpp sidecar is not running"
    assert llm["serve_profile_id"] == "windows_amd64_gpu_nvidia_cuda"
    assert llm["accelerator"] == "gpu.cuda"
    assert llm["degraded_reason"] == "managed llama.cpp sidecar is not running"


def test_readiness_returns_llm_fallback_degraded_reason() -> None:
    state = _state()
    state.llm = _FakeOllamaLLM()  # type: ignore[assignment]
    state.llm_trace = SelectionTrace(
        runtime_name="ollama",
        reason="test ollama available",
        degraded_reason="Degraded-no-local-model-artifact",
    )

    response = TestClient(create_app(state)).get("/readiness")
    llm = response.json()["families"]["llm"]

    assert response.status_code == 200
    assert llm["runtime"] == "ollama"
    assert llm["ready"] is True
    assert llm["reason"] == "test ollama available"
    assert llm["degraded_reason"] == "Degraded-no-local-model-artifact"
    assert llm["accelerator"] is None


def test_readiness_reports_selected_ollama_ready_when_local_readiness_is_unavailable() -> None:
    state = _state()
    state.readiness["llm"] = ("cpu", False, "local runtime unavailable")
    state.llm = _FakeOllamaLLM()  # type: ignore[assignment]
    state.llm_trace = SelectionTrace(
        runtime_name="ollama",
        reason="test ollama available",
        degraded_reason="Degraded-no-sidecar-binary",
    )

    response = TestClient(create_app(state)).get("/readiness")
    llm = response.json()["families"]["llm"]

    assert response.status_code == 200
    assert llm["runtime"] == "ollama"
    assert llm["ready"] is True
    assert llm["reason"] == "test ollama available"
    assert llm["degraded_reason"] == "Degraded-no-sidecar-binary"


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
    assert payload["services"]["redis"] == {"reachable": True, "reason": "reachable", "endpoint": None}
    assert payload["services"]["searxng"] == {
        "reachable": True,
        "reason": "container reachable; json usable",
        "endpoint": None,
    }
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
        "voice_capture_diagnostics": None,
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
            resident_speech_rms_threshold=0.02,
            resident_vad_speech=True,
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
        "resident_speech_rms_threshold": 0.02,
        "resident_vad_speech": True,
    }


def test_agents_status_is_disabled_read_only() -> None:
    response = _client().get("/agents/status")
    payload = response.json()

    assert response.status_code == 200
    assert payload["enabled"] is False
    assert payload["read_only"] is True
    assert payload["reason"] == "Agent boundary is disabled by policy"
    assert payload["allowed_roles"] == ["planner", "executor", "critic", "curator", "learner"]
    assert payload["allowed_tools"] == []
    known_specs = {spec["spec_id"]: spec for spec in payload["known_specs"]}
    assert sorted(known_specs) == ["agent_creator", "critic", "curator", "executor", "learner", "planner"]
    assert known_specs["planner"]["enabled"] is False
    assert known_specs["planner"]["policy_allowed"] is False


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


def test_resident_voice_status_reports_configured_stream_and_vad() -> None:
    state = _state()

    from backend.app.services.audio_stream import ResidentAudioStream
    from backend.app.services.resident_voice_invocation import default_utterance_segmenter

    state.resident_audio_stream = ResidentAudioStream()
    state.utterance_segmenter = default_utterance_segmenter()
    response = TestClient(create_app(state)).get("/status/resident-voice")
    payload = response.json()

    assert response.status_code == 200
    assert payload["mode"] == "ptt+wake"
    assert payload["available"] is False
    assert payload["degraded_reasons"] == ["resident audio stream is stopped"]
    assert payload["stream"] == {
        "present": True,
        "running": False,
        "subscribers": 0,
        "buffer_chunks": 0,
        "dropped_chunks": 0,
        "last_error": None,
    }
    assert payload["stream_present"] is True
    assert payload["stream_running"] is False
    assert payload["vad_configured"] is True
    assert payload["ptt_supported"] is True
    assert payload["wake_supported"] is True
    assert payload["barge_in_supported"] is False
    assert payload["barge_in_wired"] is False


def test_resident_voice_stream_start_stop_endpoints_report_lifecycle_truth() -> None:
    state = _state()

    from backend.app.services.audio_stream import ResidentAudioStream
    from backend.app.services.resident_voice_invocation import default_utterance_segmenter

    state.resident_audio_stream = ResidentAudioStream(chunk_source_factory=_wake_source)
    state.utterance_segmenter = default_utterance_segmenter()
    client = TestClient(create_app(state))

    started = client.post("/status/resident-voice/start")
    assert started.status_code == 200
    started_payload = started.json()
    assert started_payload["available"] is True
    assert started_payload["stream_running"] is True
    assert started_payload["degraded_reasons"] == []
    assert started_payload["barge_in_supported"] is True
    assert started_payload["barge_in_wired"] is True
    assert started_payload["stream"]["running"] is True
    assert client.app.state.jarvis_state.session_service.engine().interruption_audio_chunks is not None

    stopped = client.post("/status/resident-voice/stop")
    assert stopped.status_code == 200
    stopped_payload = stopped.json()
    assert stopped_payload["available"] is False
    assert stopped_payload["stream_running"] is False
    assert stopped_payload["degraded_reasons"] == ["resident audio stream is stopped"]
    assert stopped_payload["barge_in_supported"] is False
    assert stopped_payload["barge_in_wired"] is False
    assert stopped_payload["stream"]["running"] is False
    assert client.app.state.jarvis_state.session_service.engine().interruption_audio_chunks is None


def test_resident_voice_stream_start_endpoint_rejects_missing_stream() -> None:
    state = _state()
    state.resident_audio_stream = None

    response = TestClient(create_app(state)).post("/status/resident-voice/start")

    assert response.status_code == 409
    assert response.json()["detail"] == "resident audio stream is not configured"


def test_resident_voice_mode_endpoint_sets_visible_mode_and_stops_wake_for_ptt_only() -> None:
    client = _client()
    wake_started = client.post("/status/wake/start")
    assert wake_started.status_code == 200
    assert wake_started.json()["active"] is True

    response = client.put("/status/resident-voice/mode", json={"mode": "ptt-only"})
    payload = response.json()

    assert response.status_code == 200
    assert payload["mode"] == "ptt-only"
    assert payload["wake_active"] is False
    assert payload["wake_monitoring"] is False
    assert payload["barge_in_supported"] is False
    assert client.get("/status/wake").json()["active"] is False


def test_resident_voice_status_reconciles_ptt_only_with_active_wake() -> None:
    client = _client()
    state = client.app.state.jarvis_state
    state.resident_voice.set_mode("ptt-only")
    wake_started = client.post("/status/wake/start")
    assert wake_started.status_code == 200
    assert wake_started.json()["active"] is True

    response = client.get("/status/resident-voice")
    payload = response.json()

    assert response.status_code == 200
    assert payload["mode"] == "ptt-only"
    assert payload["wake_active"] is False
    assert payload["wake_monitoring"] is False
    assert client.get("/status/wake").json()["active"] is False


def test_resident_voice_mode_endpoint_rejects_unknown_mode() -> None:
    response = _client().put("/status/resident-voice/mode", json={"mode": "ambient"})

    assert response.status_code == 400
    assert "unsupported resident voice mode" in response.json()["detail"]


def test_resident_voice_hands_free_mode_is_visible_without_unimplemented_degradation() -> None:
    client = _client()

    response = client.put("/status/resident-voice/mode", json={"mode": "hands-free"})
    payload = response.json()

    assert response.status_code == 200
    assert payload["mode"] == "hands-free"
    assert "resident mode hands-free follow-up behavior is not implemented" not in payload["degraded_reasons"]
    assert payload["follow_up_listening"] is False
    assert payload["follow_up_source"] is None
    assert payload["continuous_active"] is False


def test_resident_voice_continuous_mode_reports_active_state() -> None:
    client = _client()

    response = client.put("/status/resident-voice/mode", json={"mode": "continuous"})
    payload = response.json()

    assert response.status_code == 200
    assert payload["mode"] == "continuous"
    assert payload["continuous_active"] is True
    assert payload["follow_up_listening"] is False
    assert payload["follow_up_source"] is None
    assert "resident mode continuous follow-up behavior is not implemented" not in payload["degraded_reasons"]


def test_resident_voice_status_reports_degraded_missing_stream_and_vad() -> None:
    state = _state()
    state.resident_audio_stream = None
    state.utterance_segmenter = None

    response = TestClient(create_app(state)).get("/status/resident-voice")
    payload = response.json()

    assert response.status_code == 200
    assert payload["available"] is False
    assert "resident audio stream is not configured" in payload["degraded_reasons"]
    assert "utterance segmenter is not configured" in payload["degraded_reasons"]
    assert payload["stream"]["present"] is False
    assert payload["stream"]["running"] is False
    assert payload["stream_present"] is False
    assert payload["vad_configured"] is False


def test_readiness_embeds_resident_voice_diagnostics() -> None:
    state = _state()

    from backend.app.services.audio_stream import ResidentAudioStream
    from backend.app.services.resident_voice_invocation import default_utterance_segmenter

    state.resident_audio_stream = ResidentAudioStream()
    state.utterance_segmenter = default_utterance_segmenter()
    response = TestClient(create_app(state)).get("/readiness")
    payload = response.json()

    assert response.status_code == 200
    assert payload["resident_audio"]["available"] is False
    assert payload["resident_audio"]["stream_present"] is True
    assert payload["resident_audio"]["vad_configured"] is True
    assert payload["resident_audio"]["barge_in_supported"] is False


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
    assert fields["APP_NAME"]["section"] == "App Defaults"
    assert fields["JARVIS_LANGUAGE"]["section"] == "App Defaults"
    assert fields["USE_LOCAL_MODEL"]["section"] == "Local LLM intent (llama.cpp)"
    assert fields["USE_LOCAL_MODEL"]["advanced"] is False
    assert fields["LLM_MODEL_MODE"]["options"] == ["dev", "prod"]
    assert fields["LLM_MODEL_MODE"]["section"] == "Local LLM intent (llama.cpp)"
    assert fields["LLM_MODEL_MODE"]["advanced"] is False
    assert fields["LLM_MODEL_MODE"]["restart_required"] is True
    assert fields["LOCAL_MODEL_FETCH"]["section"] == "Local LLM intent (llama.cpp)"
    assert fields["LOCAL_MODEL_FETCH"]["advanced"] is True
    assert fields["LLM_MODEL_POLICY"]["options"] == ["auto", "portable", "balanced", "quality", "vision_preview", "diagnostic"]
    assert fields["LLM_MODEL_POLICY"]["section"] == "Local LLM intent (llama.cpp)"
    assert fields["LLM_MODEL_ID"]["advanced"] is True
    ordered_keys = [field["key"] for field in payload["fields"]]
    assert ordered_keys.index("USE_LOCAL_MODEL") < ordered_keys.index("LLM_MODEL_MODE")
    assert ordered_keys.index("LLM_MODEL_MODE") < ordered_keys.index("LLM_MODEL_POLICY")
    assert fields["USE_OLLAMA"]["section"] == "Use Local Ollama intent"
    assert fields["OLLAMA_MODEL"]["section"] == "Use Local Ollama intent"
    assert fields["OLLAMA_BASE_URL"]["section"] == "Use Local Ollama intent"
    assert fields["OLLAMA_BASE_URL"]["advanced"] is True
    assert fields["USE_SEARXNG"]["section"] == "Optional Services"
    assert fields["SEARXNG_PORT"]["section"] == "Optional Services"
    assert fields["SEARXNG_PORT"]["advanced"] is False
    assert fields["SEARXNG_BASE_URL"]["section"] == "Optional Services"
    assert fields["SEARXNG_BASE_URL"]["advanced"] is True
    assert fields["TAVILY_API_KEY"]["secret"] is True
    assert fields["TAVILY_API_KEY"]["section"] == "Optional Services"
    assert fields["TAVILY_API_KEY"]["advanced"] is True
    assert fields["TAVILY_API_KEY"]["has_value"] is True
    assert fields["TAVILY_API_KEY"]["value"] == "***"
    assert fields["REDIS_HOST"]["section"] == "Optional Services"
    assert fields["REDIS_HOST"]["advanced"] is False
    assert fields["REDIS_PORT"]["section"] == "Optional Services"
    assert fields["REDIS_PORT"]["advanced"] is False
    assert fields["DATA_PATH"]["section"] == "App Paths"
    assert fields["TOOL_FILESYSTEM_SANDBOX_PATH"]["section"] == "App Paths"
    assert fields["CONFIG_PATH"]["section"] == "App Paths"
    assert fields["MODEL_PATH"]["section"] == "App Paths"
    assert fields["STT_MODELS"]["section"] == "App Paths"
    assert fields["STT_MODELS"]["advanced"] is True
    assert fields["WAKE_MODEL"]["section"] == "Optional Wake"
    assert fields["WAKE_MODEL"]["advanced"] is True
    assert fields["PICOVOICE_ACCESS_KEY"]["section"] == "Optional Wake"
    assert fields["PICOVOICE_ACCESS_KEY"]["secret"] is True
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


def test_operator_config_exposes_llama_cpp_sidecar_controls(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LLAMA_CPP_MODEL_PATH=models/llm/assistant-small-q4/qwen2.5-0.5b-instruct-q4_k_m.gguf\n"
        "LLAMA_CPP_BASE_URL=http://127.0.0.1:8080\n"
        "LLAMA_CPP_HOST=127.0.0.1\n"
        "LLAMA_CPP_PORT=8080\n"
        "LLAMA_CPP_BINARY_PATH=\n"
        "LLAMA_CPP_MANAGED=false\n"
        "LLAMA_CPP_MODEL_NAME=assistant-small-q4\n"
        "LLAMA_CPP_TIMEOUT_SECONDS=30\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_route, "ENV_FILE", env_file)

    response = _client().get("/config/operator")
    fields = {field["key"]: field for field in response.json()["fields"]}

    assert response.status_code == 200
    for key in (
        "LLAMA_CPP_MODEL_PATH",
        "LLAMA_CPP_BASE_URL",
        "LLAMA_CPP_HOST",
        "LLAMA_CPP_PORT",
        "LLAMA_CPP_BINARY_PATH",
        "LLAMA_CPP_MANAGED",
        "LLAMA_CPP_MODEL_NAME",
        "LLAMA_CPP_TIMEOUT_SECONDS",
    ):
        assert key in fields
        assert fields[key]["editable"] is True
        assert fields[key]["restart_required"] is True
        assert fields[key]["section"] == "Local LLM intent (llama.cpp)"
        assert fields[key]["advanced"] is True
