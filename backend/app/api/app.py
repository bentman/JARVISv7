from __future__ import annotations

from dataclasses import dataclass


from fastapi import FastAPI
import yaml


from backend.app.cache.manager import CacheManager
from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.core.capabilities import FullCapabilityReport, HardwareProfile
from backend.app.core.paths import CONFIG_DIR
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
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.stt.stt_runtime import select_stt_runtime
from backend.app.runtimes.tts.base import TTSBase
from backend.app.runtimes.tts.tts_runtime import select_tts_runtime
from backend.app.runtimes.wake.wake_runtime import select_wake_runtime
from backend.app.routing.runtime_selector import SelectionTrace, select_llm
from backend.app.services.session_service import SessionService
from backend.app.services.resident_voice_invocation import ResidentVoiceInvocationService
from backend.app.services.wake_monitor import WakeMonitorService


ReadinessMap = dict[str, tuple[str, bool, str]]
DEFAULT_POLICY_PATH = CONFIG_DIR / "app" / "policies.yaml"


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
    session_service: SessionService
    wake_monitor: WakeMonitorService
    cache_manager: CacheManager
    resident_voice: ResidentVoiceInvocationService | None = None
    llm_trace: SelectionTrace | None = None


def _derive_readiness(preflight: PreflightResult, profile: HardwareProfile) -> ReadinessMap:
    return {
        "stt": derive_stt_device_readiness(preflight, profile),
        "tts": derive_tts_device_readiness(preflight, profile),
        "llm": derive_llm_device_readiness(preflight, profile),
        "wake": derive_wake_device_readiness(preflight, profile),
    }


def _load_runtime_policy(path=DEFAULT_POLICY_PATH) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("runtime policy must be a mapping")
    return payload


def build_engine(state: ApiState, session_manager: SessionManager | None = None) -> TurnEngine:
    manager = session_manager or state.session_manager
    return TurnEngine(
        stt=state.stt,
        tts=state.tts,
        llm=state.llm,
        personality=state.personality,
        session_manager=manager,
        cache_manager=state.cache_manager,
    )


def bind_session(state: ApiState, session_manager: SessionManager) -> TurnEngine:
    state.session_manager = session_manager
    state.engine = build_engine(state, session_manager)
    return state.engine


def build_startup_state() -> ApiState:
    report = run_profiler()
    profile = report.profile
    extras = resolve_required_extras(profile)
    preflight = run_preflight(profile, extras)
    readiness = _derive_readiness(preflight, profile)
    personality = load_default_personality()
    stt = select_stt_runtime(preflight, profile)
    tts = select_tts_runtime(preflight, profile)
    llm, llm_trace = select_llm(_load_runtime_policy(), preflight, profile)
    session_manager = SessionManager()
    cache_manager = CacheManager()
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
        session_service=None,  # type: ignore[arg-type]
        resident_voice=None,  # type: ignore[arg-type]
        wake_monitor=None,  # type: ignore[arg-type]
        cache_manager=cache_manager,
        llm_trace=llm_trace,
    )
    state.engine = build_engine(state, session_manager)
    state.session_service = SessionService(
        session_manager=session_manager,
        engine=state.engine,
        engine_factory=lambda manager: bind_session(state, manager),
    )
    state.resident_voice = ResidentVoiceInvocationService(
        session_service=state.session_service,
        engine_provider=lambda: state.session_service.engine(),
    )
    state.wake_monitor = WakeMonitorService(
        session_service=state.session_service,
        runtime_factory=lambda: select_wake_runtime(state.preflight, state.profile),
        invocation_callback=state.resident_voice.enqueue,
    )
    state.resident_voice.set_invocation_hooks(
        before_invocation=state.wake_monitor.pause_for_voice_invocation,
        after_invocation=state.wake_monitor.resume_after_voice_invocation,
    )
    return state


def install_state(app: FastAPI, state: ApiState) -> None:
    app.state.jarvis_state = state


def create_app(startup_state: ApiState | None = None) -> FastAPI:
    from backend.app.api.routes import agents, config, diagnostics, health, personality, readiness, session, status, task

    app = FastAPI(title="JARVISv7 Backend API", version="0.0.1")
    install_state(app, startup_state or build_startup_state())
    app.include_router(health.router)
    app.include_router(readiness.router)
    app.include_router(personality.router)
    app.include_router(session.router)
    app.include_router(task.router)
    app.include_router(diagnostics.router)
    app.include_router(agents.router)
    app.include_router(status.router)
    app.include_router(config.router)
    return app
