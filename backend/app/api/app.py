from __future__ import annotations

from dataclasses import dataclass


from fastapi import FastAPI


from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.core.capabilities import FullCapabilityReport, HardwareProfile
from backend.app.hardware.preflight import PreflightResult, run_preflight
from backend.app.hardware.profiler import run_profiler
from backend.app.hardware.provisioning import resolve_required_extras
from backend.app.hardware.readiness import (
    derive_llm_device_readiness,
    derive_stt_device_readiness,
    derive_tts_device_readiness,
    derive_wake_device_readiness,
)
from backend.app.personality.loader import load_default_personality
from backend.app.personality.schema import PersonalityProfile
from backend.app.runtimes.llm.base import LLMBase
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.stt.stt_runtime import select_stt_runtime
from backend.app.runtimes.tts.base import TTSBase
from backend.app.runtimes.tts.tts_runtime import select_tts_runtime


ReadinessMap = dict[str, tuple[str, bool, str]]


@dataclass(slots=True)
class ApiState:
    report: FullCapabilityReport
    profile: HardwareProfile
    extras: list[str]
    preflight: PreflightResult
    readiness: ReadinessMap
    personality: PersonalityProfile
    stt: STTBase
    tts: TTSBase
    llm: LLMBase
    session_manager: SessionManager
    engine: TurnEngine


def _derive_readiness(preflight: PreflightResult, profile: HardwareProfile) -> ReadinessMap:
    return {
        "stt": derive_stt_device_readiness(preflight, profile),
        "tts": derive_tts_device_readiness(preflight, profile),
        "llm": derive_llm_device_readiness(preflight, profile),
        "wake": derive_wake_device_readiness(preflight, profile),
    }


def build_engine(state: ApiState, session_manager: SessionManager | None = None) -> TurnEngine:
    manager = session_manager or state.session_manager
    return TurnEngine(
        stt=state.stt,
        tts=state.tts,
        llm=state.llm,
        personality=state.personality,
        session_manager=manager,
    )


def build_startup_state() -> ApiState:
    report = run_profiler()
    profile = report.profile
    extras = resolve_required_extras(profile)
    preflight = run_preflight(profile, extras)
    readiness = _derive_readiness(preflight, profile)
    personality = load_default_personality()
    stt = select_stt_runtime(preflight, profile)
    tts = select_tts_runtime(preflight, profile)
    llm = OllamaLLM()
    session_manager = SessionManager()
    state = ApiState(
        report=report,
        profile=profile,
        extras=extras,
        preflight=preflight,
        readiness=readiness,
        personality=personality,
        stt=stt,
        tts=tts,
        llm=llm,
        session_manager=session_manager,
        engine=None,  # type: ignore[arg-type]
    )
    state.engine = build_engine(state, session_manager)
    return state


def install_state(app: FastAPI, state: ApiState) -> None:
    app.state.jarvis_state = state


def create_app(startup_state: ApiState | None = None) -> FastAPI:
    from backend.app.api.routes import agents, diagnostics, health, readiness, session, status, task, voice

    app = FastAPI(title="JARVISv7 Backend API", version="0.0.1")
    install_state(app, startup_state or build_startup_state())
    app.include_router(health.router)
    app.include_router(readiness.router)
    app.include_router(session.router)
    app.include_router(task.router)
    app.include_router(voice.router)
    app.include_router(diagnostics.router)
    app.include_router(agents.router)
    app.include_router(status.router)
    return app