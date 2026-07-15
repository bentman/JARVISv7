from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, replace

import yaml
from backend.app.cache.manager import CacheManager
from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.core.capabilities import FullCapabilityReport, HardwareProfile
from backend.app.core.paths import CONFIG_DIR
from backend.app.hardware.preflight import PreflightResult
from backend.app.memory.semantic import SemanticMemory
from backend.app.personality.loader import load_default_personality
from backend.app.personality.schema import PersonalityProfile
from backend.app.routing.runtime_selector import SelectionTrace, select_llm
from backend.app.runtimes.llm.base import LLMBase
from backend.app.runtimes.stt.barge_in import BargeInDetector
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.stt.stt_runtime import select_stt_runtime
from backend.app.runtimes.tts.base import TTSBase
from backend.app.runtimes.tts.tts_runtime import select_tts_runtime
from backend.app.runtimes.vad import EnergyVADRuntime
from backend.app.runtimes.wake.wake_runtime import select_wake_runtime
from backend.app.services.audio_stream import ResidentAudioStream
from backend.app.services.local_llm_sidecar import LocalLLMSidecarService
from backend.app.services.local_llm_startup import prepare_managed_local_llm
from backend.app.services.resident_voice_invocation import (
    ResidentVoiceInvocationService,
    default_utterance_segmenter,
    resident_interruption_chunks,
)
from backend.app.services.session_service import SessionService
from backend.app.services.startup_context import ReadinessMap, load_startup_context
from backend.app.services.utterance_segmenter import (
    WAKE_COMMAND_SILENCE_END_S,
    WAKE_COMMAND_TRAILING_PAD_S,
    UtteranceSegmenter,
)
from backend.app.services.wake_monitor import WakeMonitorService
from fastapi import FastAPI

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
    resident_audio_stream: ResidentAudioStream | None = None
    utterance_segmenter: UtteranceSegmenter | None = None
    resident_voice: ResidentVoiceInvocationService | None = None
    llm_trace: SelectionTrace | None = None
    local_llm_sidecar: LocalLLMSidecarService | None = None
    semantic_memory: SemanticMemory | None = None


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
        semantic=state.semantic_memory,
        barge_in_detector=BargeInDetector(vad=EnergyVADRuntime(), min_speech_s=0.2, min_speech_chunks=2),
        # Factory: resolved per playback so barge-in subscribes fresh each turn
        # and tracks the resident stream's current running state.
        interruption_audio_chunks=lambda: resident_interruption_chunks(state.resident_audio_stream),
    )


def bind_session(state: ApiState, session_manager: SessionManager) -> TurnEngine:
    state.session_manager = session_manager
    state.engine = build_engine(state, session_manager)
    return state.engine


def build_startup_state() -> ApiState:
    startup = load_startup_context()
    report = startup.report
    profile = startup.profile
    extras = startup.extras
    preflight = startup.preflight
    readiness = startup.readiness
    personality = load_default_personality()
    stt = select_stt_runtime(preflight, profile)
    stt.warmup()
    tts = select_tts_runtime(preflight, profile)
    tts.warmup()
    local_llm = prepare_managed_local_llm(profile, preflight, flags=report.flags)
    llm, llm_trace = select_llm(_load_runtime_policy(), preflight, profile, local=local_llm.runtime)
    session_manager = SessionManager()
    cache_manager = CacheManager()
    semantic_memory = SemanticMemory()
    resident_audio_stream = ResidentAudioStream()
    utterance_segmenter = default_utterance_segmenter()
    wake_utterance_segmenter = replace(
        utterance_segmenter,
        silence_end_s=WAKE_COMMAND_SILENCE_END_S,
        trailing_pad_s=WAKE_COMMAND_TRAILING_PAD_S,
    )
    engine = TurnEngine(
        stt=stt,
        tts=tts,
        llm=llm,
        personality=personality,
        session_manager=session_manager,
        cache_manager=cache_manager,
        semantic=semantic_memory,
        barge_in_detector=BargeInDetector(vad=EnergyVADRuntime(), min_speech_s=0.2, min_speech_chunks=2),
        interruption_audio_chunks=lambda: resident_interruption_chunks(resident_audio_stream),
    )
    session_service = SessionService(
        session_manager=session_manager,
        engine=engine,
        engine_factory=lambda manager: bind_session(state, manager),
        semantic_memory=semantic_memory,
    )
    resident_voice = ResidentVoiceInvocationService(
        session_service=session_service,
        engine_provider=lambda: session_service.engine(),
        resident_stream=resident_audio_stream,
        utterance_segmenter=utterance_segmenter,
    )
    wake_monitor = WakeMonitorService(
        session_service=session_service,
        runtime_factory=lambda: select_wake_runtime(preflight, profile),
        invocation_callback=resident_voice.enqueue,
        resident_stream=resident_audio_stream,
        utterance_segmenter=wake_utterance_segmenter,
    )
    resident_voice.set_invocation_hooks(
        before_invocation=wake_monitor.pause_for_voice_invocation,
        after_invocation=lambda state: wake_monitor.resume_after_voice_invocation(bool(state)),
    )
    wake_monitor.warmup()

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
        engine=engine,
        session_service=session_service,
        wake_monitor=wake_monitor,
        cache_manager=cache_manager,
        resident_audio_stream=resident_audio_stream,
        utterance_segmenter=utterance_segmenter,
        resident_voice=resident_voice,
        llm_trace=llm_trace,
        local_llm_sidecar=local_llm.sidecar,
        semantic_memory=semantic_memory,
    )
    return state


def install_state(app: FastAPI, state: ApiState) -> None:
    app.state.jarvis_state = state


def stop_managed_local_llm(state: ApiState | None) -> None:
    if state is None or state.local_llm_sidecar is None:
        return
    state.local_llm_sidecar.stop()
    state.local_llm_sidecar = None


def stop_resident_audio_stream(state: ApiState | None) -> None:
    if state is None or state.resident_audio_stream is None:
        return
    state.resident_audio_stream.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        state = getattr(app.state, "jarvis_state", None)
        stop_resident_audio_stream(state)
        stop_managed_local_llm(state)


def create_app(startup_state: ApiState | None = None) -> FastAPI:
    from backend.app.api.routes import (
        agents,
        config,
        diagnostics,
        health,
        personality,
        readiness,
        session,
        status,
        task,
    )

    app = FastAPI(title="JARVISv7 Backend API", version="0.0.1", lifespan=lifespan)
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
