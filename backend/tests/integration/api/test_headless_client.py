from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.app import ApiState, create_app
from backend.app.cache.manager import CacheManager
from backend.app.conversation.engine import TurnResult
from backend.app.conversation.states import ConversationState
from backend.app.core.capabilities import CapabilityFlags, FullCapabilityReport, HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.personality.schema import PersonalityProfile
from backend.app.services.session_service import SessionService


class _FakeRuntime:
    device = "cpu"
    model_path = Path("models/fake")

    def is_available(self) -> bool:
        return False

    def runtime_name(self) -> str:
        return "fake-llm"

    def generate(self, prompt: str, **kwargs: object) -> str:
        return "integrated response"


@dataclass(slots=True)
class _SessionManager:
    session_id: str = "session-integration"
    turn_artifacts: list[object] = field(default_factory=list)

    def close_session(self, final_state: str = "IDLE") -> Path:
        _ = final_state
        return Path("data/sessions/session-integration.json")


class _Engine:
    personality = PersonalityProfile(
        profile_id="default",
        display_name="JARVIS",
        tone="professional",
        brevity="concise",
        formality="semi-formal",
    )

    def run_text_turn(self, text: str) -> TurnResult:
        return TurnResult(
            turn_id="turn-integration",
            session_id="session-integration",
            transcript=text,
            response_text="integrated response",
            final_state=ConversationState.IDLE,
        )


def _client() -> TestClient:
    profile = HardwareProfile(os_name="windows", arch="amd64", profile_id="profile-integration")
    flags = CapabilityFlags(supports_local_stt=True, supports_local_tts=True, supports_wake_word=True)
    runtime = _FakeRuntime()
    state = ApiState(
        report=FullCapabilityReport(profile=profile, flags=flags),
        profile=profile,
        extras=["dev"],
        preflight=PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={}),
        readiness={
            "stt": ("cpu", True, "stt ready"),
            "tts": ("cpu", False, "tts unavailable"),
            "llm": ("cpu", True, "llm ready"),
            "wake": ("cpu", False, "wake unavailable"),
        },
        personality=PersonalityProfile(
            profile_id="default",
            display_name="JARVIS",
            tone="professional",
            brevity="concise",
            formality="semi-formal",
        ),
        stt=runtime,  # type: ignore[arg-type]
        tts=runtime,  # type: ignore[arg-type]
        llm=runtime,  # type: ignore[arg-type]
        session_manager=_SessionManager(),  # type: ignore[arg-type]
        engine=_Engine(),  # type: ignore[arg-type]
        session_service=None,  # type: ignore[arg-type]
        wake_monitor=None,  # type: ignore[arg-type]
        cache_manager=CacheManager(),
    )
    state.session_service = SessionService(
        session_manager=state.session_manager,  # type: ignore[arg-type]
        engine=state.engine,
        engine_factory=lambda manager: _Engine(),  # type: ignore[arg-type]
    )
    return TestClient(create_app(state))


def test_headless_client_can_call_health_endpoint() -> None:
    response = _client().get("/health")
    assert response.status_code == 200


def test_headless_client_can_call_readiness_endpoint() -> None:
    response = _client().get("/readiness")
    assert response.status_code == 200
    assert response.json()["families"]["stt"]["ready"] is True


def test_headless_client_can_drive_text_turn_with_stubbed_llm() -> None:
    response = _client().post("/task/text", json={"text": "hello"})
    assert response.status_code == 200
    assert response.json()["response_text"] == "integrated response"


def test_headless_client_can_create_and_close_session() -> None:
    client = _client()
    created = client.post("/session/create", json={})
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    closed = client.post("/session/close", json={"session_id": session_id})
    assert closed.status_code == 200
    assert closed.json()["closed"] is True


def test_headless_client_drives_three_text_turns_in_one_active_session(tmp_path: Path) -> None:
    profile = HardwareProfile(os_name="windows", arch="amd64", profile_id="profile-integration")
    flags = CapabilityFlags(supports_local_stt=True, supports_local_tts=True, supports_wake_word=True)
    runtime = _FakeRuntime()
    manager = __import__("backend.app.conversation.session_manager", fromlist=["SessionManager"]).SessionManager(
        turns_base_dir=tmp_path / "turns",
        sessions_base_dir=tmp_path / "sessions",
    )

    def build_engine(session_manager):
        return __import__("backend.app.conversation.engine", fromlist=["TurnEngine"]).TurnEngine(
            stt=runtime,  # type: ignore[arg-type]
            tts=runtime,  # type: ignore[arg-type]
            llm=runtime,  # type: ignore[arg-type]
            personality=PersonalityProfile(
                profile_id="default",
                display_name="JARVIS",
                tone="professional",
                brevity="concise",
                formality="semi-formal",
            ),
            session_manager=session_manager,
        )

    state = ApiState(
        report=FullCapabilityReport(profile=profile, flags=flags),
        profile=profile,
        extras=["dev"],
        preflight=PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={}),
        readiness={"stt": ("cpu", True, "stt ready"), "tts": ("cpu", False, "tts unavailable"), "llm": ("cpu", True, "llm ready"), "wake": ("cpu", False, "wake unavailable")},
        personality=PersonalityProfile(profile_id="default", display_name="JARVIS", tone="professional", brevity="concise", formality="semi-formal"),
        stt=runtime,  # type: ignore[arg-type]
        tts=runtime,  # type: ignore[arg-type]
        llm=runtime,  # type: ignore[arg-type]
        session_manager=manager,
        engine=build_engine(manager),
        session_service=None,  # type: ignore[arg-type]
        wake_monitor=None,  # type: ignore[arg-type]
        cache_manager=CacheManager(),
    )
    state.session_service = SessionService(session_manager=manager, engine=state.engine, engine_factory=build_engine)
    client = TestClient(create_app(state))
    created = client.post("/session/create", json={})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    responses = [client.post("/task/text", json={"text": f"hello {index}", "session_id": session_id}) for index in range(3)]
    assert [response.status_code for response in responses] == [200, 200, 200]
    assert {response.json()["session_id"] for response in responses} == {session_id}

    status = client.get("/session/status")
    assert status.status_code == 200
    assert status.json()["session_id"] == session_id
    assert status.json()["active"] is True
    assert status.json()["turn_count"] == 3
