from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from backend.app.api.app import ApiState, create_app
from backend.app.cache.manager import CacheManager
from backend.app.conversation.engine import TurnResult
from backend.app.conversation.states import ConversationState
from backend.app.core.capabilities import CapabilityFlags, FullCapabilityReport, HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.personality.schema import (
    PersonalityExample,
    PersonalityProfile,
    PersonalityStyle,
    PersonalityTraits,
)
from backend.app.services.session_service import SessionService
from fastapi.testclient import TestClient


@pytest.fixture
def new_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build session managers under tmp_path, including those /session/create builds."""
    from backend.app.conversation.session_manager import SessionManager

    def build() -> SessionManager:
        return SessionManager(turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")

    # Sessions the route creates must land in tmp_path, not the repo's data/ root.
    monkeypatch.setattr("backend.app.services.session_service.SessionManager", build)
    return build


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
    search_service = None

    def prepare_close(self, timeout=10):
        pass

    personality = PersonalityProfile(
        profile_id="default",
        display_name="JARVIS",
        description="Balanced assistant.",
        locale="en",
        system="Answer directly.",
        style=PersonalityStyle(
            max_words_default=120,
            structure="Answer first.",
            do=("Lead with the answer.",),
            avoid=("Filler.",),
        ),
        traits=PersonalityTraits(
            warmth="medium", assertiveness="medium", detail="medium", humor="light"
        ),
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
    session_manager = _SessionManager()
    engine = _Engine()
    session_service = SessionService(
        session_manager=session_manager,  # type: ignore[arg-type]
        engine=engine,  # type: ignore[arg-type]
        engine_factory=lambda manager: _Engine(),  # type: ignore[arg-type, return-value]
    )
    from unittest.mock import MagicMock

    from backend.app.services.wake_monitor import WakeMonitorService
    wake_monitor = WakeMonitorService(
        session_service=session_service,
        runtime_factory=lambda: MagicMock(),
    )
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
            description="Balanced assistant.",
            locale="en",
            system="Answer directly.",
            style=PersonalityStyle(
                max_words_default=120,
                structure="Answer first.",
                do=("Lead with the answer.",),
                avoid=("Filler.",),
            ),
            traits=PersonalityTraits(
                warmth="medium", assertiveness="medium", detail="medium", humor="light"
            ),
            examples=(PersonalityExample(user="Status?", assistant="Ready."),),
            generation={
                "temperature": 0.5,
                "top_p": 0.9,
                "top_k": 40,
                "repeat_penalty": 1.08,
                "max_tokens": 120,
                "stop": ["\nUser:", "\nAssistant:"],
            },
        ),
        stt=runtime,  # type: ignore[arg-type]
        tts=runtime,  # type: ignore[arg-type]
        llm=runtime,  # type: ignore[arg-type]
        session_manager=session_manager,  # type: ignore[arg-type]
        engine=engine,  # type: ignore[arg-type]
        session_service=session_service,
        wake_monitor=wake_monitor,
        cache_manager=CacheManager(),
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


@pytest.mark.usefixtures("new_manager")
def test_headless_client_can_create_and_close_session() -> None:
    client = _client()
    created = client.post("/session/create", json={})
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    closed = client.post("/session/close", json={"session_id": session_id})
    assert closed.status_code == 200
    assert closed.json()["closed"] is True


def test_headless_client_drives_three_text_turns_in_one_active_session(new_manager) -> None:
    profile = HardwareProfile(os_name="windows", arch="amd64", profile_id="profile-integration")
    flags = CapabilityFlags(supports_local_stt=True, supports_local_tts=True, supports_wake_word=True)
    runtime = _FakeRuntime()
    manager = new_manager()

    def build_engine(session_manager):
        return __import__("backend.app.conversation.engine", fromlist=["TurnEngine"]).TurnEngine(
            stt=runtime,
            tts=runtime,
            llm=runtime,
            personality=PersonalityProfile(
                profile_id="default",
                display_name="JARVIS",
                description="Balanced assistant.",
                locale="en",
                system="Answer directly.",
                style=PersonalityStyle(
                    max_words_default=120,
                    structure="Answer first.",
                    do=("Lead with the answer.",),
                    avoid=("Filler.",),
                ),
                traits=PersonalityTraits(
                    warmth="medium", assertiveness="medium", detail="medium", humor="light"
                ),
                examples=(PersonalityExample(user="Status?", assistant="Ready."),),
                generation={
                    "temperature": 0.5,
                    "top_p": 0.9,
                    "top_k": 40,
                    "repeat_penalty": 1.08,
                    "max_tokens": 120,
                    "stop": ["\nUser:", "\nAssistant:"],
                },
            ),
            session_manager=session_manager,
        )

    engine = build_engine(manager)
    session_service = SessionService(session_manager=manager, engine=engine, engine_factory=build_engine)
    from unittest.mock import MagicMock

    from backend.app.services.wake_monitor import WakeMonitorService
    wake_monitor = WakeMonitorService(
        session_service=session_service,
        runtime_factory=lambda: MagicMock(),
    )

    state = ApiState(
        report=FullCapabilityReport(profile=profile, flags=flags),
        profile=profile,
        extras=["dev"],
        preflight=PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={}),
        readiness={"stt": ("cpu", True, "stt ready"), "tts": ("cpu", False, "tts unavailable"), "llm": ("cpu", True, "llm ready"), "wake": ("cpu", False, "wake unavailable")},
        personality=PersonalityProfile(
            profile_id="default",
            display_name="JARVIS",
            description="Balanced assistant.",
            locale="en",
            system="Answer directly.",
            style=PersonalityStyle(
                max_words_default=120,
                structure="Answer first.",
                do=("Lead with the answer.",),
                avoid=("Filler.",),
            ),
            traits=PersonalityTraits(
                warmth="medium", assertiveness="medium", detail="medium", humor="light"
            ),
            examples=(PersonalityExample(user="Status?", assistant="Ready."),),
            generation={
                "temperature": 0.5,
                "top_p": 0.9,
                "top_k": 40,
                "repeat_penalty": 1.08,
                "max_tokens": 120,
                "stop": ["\nUser:", "\nAssistant:"],
            },
        ),
        stt=runtime,  # type: ignore[arg-type]
        tts=runtime,  # type: ignore[arg-type]
        llm=runtime,  # type: ignore[arg-type]
        session_manager=manager,
        engine=engine,
        session_service=session_service,
        wake_monitor=wake_monitor,
        cache_manager=CacheManager(),
    )
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


def test_headless_client_manages_an_agent_profile_and_records_its_delegated_run(
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace

    from backend.app.actions.catalog import CapabilityObservation
    from backend.app.agents.registry import AgentRegistry
    from backend.app.api.routes.agents import router
    from backend.app.conversation.engine import TurnEngine
    from backend.app.conversation.session_manager import SessionManager
    from backend.app.personality.loader import load_default_personality
    from backend.app.runtimes.llm.base import LLMBase
    from backend.app.services.capability_service import CapabilityService, build_agent_handlers
    from fastapi import FastAPI

    class Model(LLMBase):
        def generate(self, prompt: str, **kwargs: object) -> str:
            return "agent answer"

        def is_available(self) -> bool:
            return True

        def runtime_name(self) -> str:
            return "fake-llm"

    registry = AgentRegistry(tmp_path / "config", tmp_path / "data")
    manager = SessionManager(turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions")
    capabilities = CapabilityService(
        observe=lambda: CapabilityObservation(
            agents=tuple(registry.to_capability_records()), agent_registry_present=True
        )
    )
    engine = TurnEngine(
        stt=None, tts=None, llm=Model(), personality=load_default_personality(),  # type: ignore[arg-type]
        session_manager=manager, capability_service=capabilities, agent_registry=registry,
    )
    capabilities.bind_handler_provider(lambda: build_agent_handlers(
        agent_registry_provider=lambda: registry, engine_provider=lambda: engine,
    ))
    app = FastAPI()
    app.include_router(router)
    app.state.jarvis_state = SimpleNamespace(agent_registry=registry, capability_service=capabilities)
    client = TestClient(app)
    profile = {
        "profile_id": "notes", "display_name": "Notes", "purpose": "Tidy notes",
        "instructions": "Answer briefly.", "invocation_modes": ["direct"], "capability_ids": [],
        "memory_scope": "none", "approval_class": "none", "timeout_ms": 5000,
        "cancellable": True, "output_contract": {"type": "object"}, "provider_model_policy": {},
    }

    created = client.post("/agents", json={"profile": profile})
    assert created.status_code == 201
    listed = client.get("/agents").json()["agents"]
    assert [(item["profile_id"], item["editable"], item["source"]) for item in listed] == [
        ("notes", True, "data/agents/notes.yaml"),
    ]

    stale = client.put("/agents/notes", json={"profile": profile, "expected_fingerprint": "stale"})
    assert stale.status_code == 409
    updated = client.put(
        "/agents/notes",
        json={"profile": {**profile, "purpose": "Tidy meeting notes"},
              "expected_fingerprint": created.json()["fingerprint"]},
    )
    assert updated.status_code == 200

    invoked = client.post("/agents/invoke", json={"profile_id": "notes", "prompt": "tidy"}).json()
    assert (invoked["status"], invoked["output"]) == ("success", {"response": "agent answer"})
    [artifact] = manager.turn_artifacts
    [run] = artifact.delegated_runs
    assert (run["kind"], run["target_id"], run["mode"], run["status"]) == (
        "agent", "notes", "direct", "success",
    )

    audit = [record["capability_id"] for record in capabilities.audit(limit=100).records]
    assert {"agent-profile-write", "agent-invoke-notes"} <= set(audit)
    runs = client.get("/agents/runs").json()["records"]
    assert runs and {record["capability_id"] for record in runs} == {"agent-invoke-notes"}
    assert client.post("/agents/notes/cancel").json() == {"profile_id": "notes", "cancelled": False}

    # The operator's stop control reaches a run that is still working.
    started, release = threading.Event(), threading.Event()

    def slow_generate(prompt: str, **kwargs: object) -> str:
        started.set()
        release.wait(timeout=5)
        return "late answer"

    engine.llm.generate = slow_generate  # type: ignore[method-assign]
    running: list[dict] = []
    worker = threading.Thread(target=lambda: running.append(
        client.post("/agents/invoke", json={"profile_id": "notes", "prompt": "tidy again"}).json()
    ))
    worker.start()
    assert started.wait(timeout=5)
    assert client.post("/agents/notes/cancel").json() == {"profile_id": "notes", "cancelled": True}
    release.set()
    worker.join(timeout=5)
    [cancelled] = running
    assert cancelled["status"] == "cancelled"
    assert manager.turn_artifacts[-1].delegated_runs[0]["status"] == "cancelled"

    deleted = client.delete(
        "/agents/notes", params={"expected_fingerprint": updated.json()["fingerprint"]}
    )
    assert deleted.status_code == 200
    assert client.get("/agents").json()["agents"] == []


def test_headless_client_hands_a_session_to_an_agent_and_ends_the_handoff(
    tmp_path: Path, new_manager
) -> None:
    from types import SimpleNamespace

    import yaml
    from backend.app.actions.catalog import CapabilityObservation
    from backend.app.agents.registry import AgentRegistry
    from backend.app.api.routes.session import router as session_router
    from backend.app.api.routes.task import router as task_router
    from backend.app.conversation.engine import TurnEngine
    from backend.app.conversation.session_manager import SessionManager
    from backend.app.personality.loader import load_default_personality
    from backend.app.runtimes.llm.base import LLMBase
    from backend.app.services.capability_service import CapabilityService, build_agent_handlers
    from fastapi import FastAPI

    class Model(LLMBase):
        def generate(self, prompt: str, **kwargs: object) -> str:
            return "agent answer"

        def is_available(self) -> bool:
            return True

        def runtime_name(self) -> str:
            return "fake-llm"

    (tmp_path / "config" / "agents").mkdir(parents=True)
    (tmp_path / "config" / "agents" / "notes.yaml").write_text(yaml.safe_dump({
        "profile_id": "notes", "display_name": "Notes", "purpose": "Tidy notes",
        "instructions": "Answer briefly.", "invocation_modes": ["handoff"], "capability_ids": [],
        "memory_scope": "none", "approval_class": "none", "timeout_ms": 5000,
        "cancellable": True, "output_contract": {"type": "object"}, "provider_model_policy": {},
    }), encoding="utf-8")
    registry = AgentRegistry(tmp_path / "config")
    capabilities = CapabilityService(
        observe=lambda: CapabilityObservation(agents=tuple(registry.to_capability_records()))
    )

    def build_engine(manager: SessionManager) -> TurnEngine:
        return TurnEngine(
            stt=None, tts=None, llm=Model(), personality=load_default_personality(),  # type: ignore[arg-type]
            session_manager=manager, capability_service=capabilities, agent_registry=registry,
        )

    manager = new_manager()
    session_service = SessionService(
        session_manager=manager, engine=build_engine(manager), engine_factory=build_engine,
    )
    capabilities.bind_handler_provider(lambda: build_agent_handlers(
        agent_registry_provider=lambda: registry, engine_provider=session_service.engine,
    ))
    app = FastAPI()
    app.include_router(session_router)
    app.include_router(task_router)
    app.state.jarvis_state = SimpleNamespace(session_service=session_service)
    client = TestClient(app)
    session_id = client.post("/session/create", json={}).json()["session_id"]

    started = client.post("/task/text", json={"text": "Talk to Notes"}).json()
    assert started["response_text"].startswith("You're now talking to Notes.")
    assert client.get("/session/status").json()["active_agent"] == {
        "profile_id": "notes", "display_name": "Notes",
    }

    handed = client.post("/task/text", json={"text": "tidy the agenda"}).json()
    assert handed["response_text"] == "agent answer"
    artifact = session_service.engine().session_manager.turn_artifacts[-1]
    assert [(run["target_id"], run["mode"]) for run in artifact.delegated_runs] == [("notes", "handoff")]

    ended = client.post("/session/handoff/end", json={"session_id": session_id}).json()
    assert ended == {"ended": True}
    assert client.get("/session/status").json()["active_agent"] is None


def test_production_wiring_runs_an_operator_extension_on_the_current_sessions_engine(
    tmp_path: Path, new_manager, monkeypatch: pytest.MonkeyPatch
) -> None:
    # create_app installs the extension executor and bind_session rebuilds the engine per
    # session; both are the production functions here, not test-assembled stand-ins.
    from unittest.mock import MagicMock

    import backend.app.extensions.acp as acp
    from backend.app.actions import boundaries
    from backend.app.actions.catalog import CapabilityObservation
    from backend.app.api.app import bind_session
    from backend.app.personality.loader import load_default_personality
    from backend.app.services.capability_service import CapabilityService
    from backend.app.services.extension_runtime_service import ExtensionRuntimeService

    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    monkeypatch.setattr(boundaries, "REPO_ROOT", repo)
    (tmp_path / "config" / "extensions" / "acp").mkdir(parents=True)
    (tmp_path / "config" / "extensions" / "acp" / "agent.yaml").write_text(
        "id: agent\nname: Agent\nversion: '1'\ndefinition:\n  command: [agent-bin, serve]\n"
        "  process:\n    subprocess: true\n    argv_allowlist: [agent-bin]\n"
        "    env_passthrough: []\n    working_root: data\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(acp, "run_acp", lambda _manager, definition, prompt, operation, **_kwargs: {
        "agent_id": definition.agent_id, "prompt": prompt,
    })
    runtime = ExtensionRuntimeService(
        CapabilityService(observe=lambda: CapabilityObservation(extension_catalog_present=True)),
        config_dir=tmp_path / "config", data_dir=repo / "data", db_path=repo / "data" / "operator.sqlite",
    )
    profile = HardwareProfile(os_name="windows", arch="amd64", profile_id="profile-integration")
    state = ApiState(
        report=FullCapabilityReport(profile=profile, flags=CapabilityFlags()),
        profile=profile, extras=["dev"],
        preflight=PreflightResult(tokens=[], dll_discovery_log=[], probe_errors={}),
        readiness={}, personality=load_default_personality(),
        stt=_FakeRuntime(), tts=_FakeRuntime(), llm=_FakeRuntime(),  # type: ignore[arg-type]
        session_manager=new_manager(), engine=None,  # type: ignore[arg-type]
        session_service=None,  # type: ignore[arg-type]
        wake_monitor=MagicMock(), cache_manager=CacheManager(), extension_runtime=runtime,
    )
    first_engine = bind_session(state, state.session_manager)
    state.session_service = SessionService(
        session_manager=state.session_manager, engine=first_engine,
        engine_factory=lambda manager: bind_session(state, manager),
    )
    client = TestClient(create_app(state))
    capability_id = runtime.detail("acp:agent")["operations"][0]["capability_id"]
    invoke = {"capability_id": capability_id, "arguments": {"prompt": "summarize"}}

    session_id = client.post("/session/create", json={}).json()["session_id"]
    executed = client.post("/extensions/acp:agent/invoke", json=invoke).json()

    assert executed["status"] == "success"
    assert state.engine is not first_engine
    assert state.engine is state.session_service.engine()
    [artifact] = state.session_manager.turn_artifacts
    assert artifact.session_id == session_id
    assert [run["target_id"] for run in artifact.delegated_runs] == ["acp:agent"]
    assert first_engine.session_manager.turn_artifacts == []

    client.post("/session/close", json={"session_id": session_id})
    refused = client.post("/extensions/acp:agent/invoke", json=invoke).json()
    assert refused["status"] == "failure"
    assert state.session_manager.turn_artifacts == [artifact]
