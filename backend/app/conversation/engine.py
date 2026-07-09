from __future__ import annotations

import re
import time
import wave
from dataclasses import dataclass, field
from typing import Any, Iterable
from uuid import uuid4

import numpy as np

from backend.app.cognition.prompt_assembler import assemble_prompt_envelope
from backend.app.cognition.prompt_renderer import render_flat_prompt
from backend.app.cognition.responder import bound_single_turn_response, sanitize_for_tts
from backend.app.cognition.style_guard import apply_personality_style_guard
from backend.app.cognition.executor import ToolExecutor, ToolResult
from dataclasses import dataclass, field
from typing import Any, Iterable
from uuid import uuid4

import numpy as np

from backend.app.cognition.prompt_assembler import assemble_prompt_envelope
from backend.app.cognition.prompt_renderer import render_flat_prompt
from backend.app.cognition.responder import bound_single_turn_response, sanitize_for_tts
from backend.app.cognition.style_guard import apply_personality_style_guard
from backend.app.cognition.executor import ToolExecutor, ToolResult
from backend.app.cache.manager import CacheManager
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.conversation.turn_manager import PhaseObserver, TurnContext
from backend.app.memory.write_policy import WritePolicy
from backend.app.memory.episodic import EpisodicMemory
from backend.app.memory.semantic import SemanticMemory
from backend.app.memory.retrieval import RetrievalManager, RetrievedFact
from backend.app.personality.policy import compile_personality_policy
from backend.app.personality.schema import PersonalityProfile
from backend.app.runtimes.llm.base import LLMBase
from backend.app.runtimes.stt.barge_in import BargeInDetector
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.tts import playback
from backend.app.runtimes.tts.base import TTSBase


@dataclass(frozen=True, slots=True)
class TurnResult:
    turn_id: str
    session_id: str
    transcript: str | None
    response_text: str | None
    final_state: ConversationState
    failure_reason: str | None = None
    tts_degraded: bool = False
    tts_degraded_reason: str | None = None
    tts_output_device: str | None = None
    interrupted: bool = False
    interruption_events: list[dict[str, object]] = field(default_factory=list)
    tool_calls: list[dict[str, object]] = field(default_factory=list)
    tool_results: list[dict[str, object]] = field(default_factory=list)
    raw_audio_path: str | None = None
    active_personality_profile_id: str = "unknown"
    profile_epoch: int = 0
    phase_durations_ms: dict[str, float] = field(default_factory=dict)
    failure_phase: str | None = None


class TurnEngine:
    def __init__(
        self,
        *,
        stt: STTBase,
        tts: TTSBase,
        llm: LLMBase,
        personality: PersonalityProfile,
        session_id: str | None = None,
        session_manager: SessionManager | None = None,
        write_policy: WritePolicy | None = None,
        barge_in_detector: BargeInDetector | None = None,
        interruption_audio_chunks: Iterable[np.ndarray] | None = None,
        playback_api: Any | None = None,
        executor: ToolExecutor | None = None,
        tool_registry: Any | None = None,
        episodic: EpisodicMemory | None = None,
        cache_manager: CacheManager | None = None,
        semantic: SemanticMemory | None = None,
    ) -> None:
        self.stt = stt
        self.tts = tts
        self.llm = llm
        self.personality = personality
        self.session_manager = session_manager
        self.write_policy = write_policy or WritePolicy()
        self.session_id = session_manager.session_id if session_manager is not None else session_id or uuid4().hex
        self.barge_in_detector = barge_in_detector
        self.interruption_audio_chunks = interruption_audio_chunks
        self.playback_api = playback_api or playback
        self.executor = executor or ToolExecutor()
        self.tool_registry = tool_registry
        self.episodic = episodic
        self.cache_manager = cache_manager
        self.semantic = semantic
        self.retrieval = RetrievalManager()
        self.phase_observer: PhaseObserver | None = None

    def run_text_turn(self, text: str, *, tool_name: str | None = None, tool_input: dict[str, object] | None = None) -> TurnResult:
        transcript = text.strip()
        context = self._create_context("text")
        if not transcript:
            return self._fail(context, transcript=None, response_text=None, reason="text input is empty")
        return self._run_reasoning_path(
            context,
            transcript,
            speak_response=False,
            tool_name=tool_name,
            tool_input=tool_input,
        )

    def run_voice_turn(
        self,
        audio: np.ndarray,
        sample_rate: int,
        *,
        tool_name: str | None = None,
        tool_input: dict[str, object] | None = None,
    ) -> TurnResult:
        context = self._create_context("voice")
        voice_turn_started_at = time.perf_counter()
        phase_durations_ms: dict[str, float] = {}
        raw_audio_path = self._persist_voice_audio(context, audio, sample_rate)
        try:
            context.advance(ConversationState.LISTENING)
            context.advance(ConversationState.TRANSCRIBING)
            stt_started_at = time.perf_counter()
            try:
                transcript = self.stt.transcribe(np.asarray(audio, dtype=np.float32), sample_rate)
            finally:
                phase_durations_ms["stt_ms"] = _elapsed_ms(stt_started_at)
            if not transcript.strip():
                return self._fail(
                    context,
                    transcript=transcript,
                    response_text=None,
                    reason="STT returned empty transcript",
                    raw_audio_path=raw_audio_path,
                    phase_durations_ms=_voice_phase_durations(phase_durations_ms, voice_turn_started_at),
                    failure_phase="stt",
                )
            return self._run_reasoning_path(
                context,
                transcript,
                speak_response=True,
                tool_name=tool_name,
                tool_input=tool_input,
                raw_audio_path=raw_audio_path,
                phase_durations_ms=phase_durations_ms,
                voice_turn_started_at=voice_turn_started_at,
            )
        except Exception as exc:
            return self._fail(
                context,
                transcript=None,
                response_text=None,
                reason=str(exc),
                raw_audio_path=raw_audio_path,
                phase_durations_ms=_voice_phase_durations(phase_durations_ms, voice_turn_started_at),
                failure_phase=_failure_phase_for_state(context.state),
            )

    def _run_reasoning_path(
        self,
        context: TurnContext,
        transcript: str,
        *,
        speak_response: bool,
        tool_name: str | None = None,
        tool_input: dict[str, object] | None = None,
        raw_audio_path: str | None = None,
        phase_durations_ms: dict[str, float] | None = None,
        voice_turn_started_at: float | None = None,
    ) -> TurnResult:
        phase_durations_ms = phase_durations_ms if phase_durations_ms is not None else {}
        try:
            context.advance(ConversationState.REASONING)
            continuity_packet = self.session_manager.build_continuity_packet(latest_text=transcript) if self.session_manager else None
            session_continuity = None
            if continuity_packet is not None and not continuity_packet.is_empty():
                session_continuity = continuity_packet.to_prompt_text()
            suppress_working_memory = bool(
                continuity_packet
                and any("suppressed prior assistant wording and working memory" in item for item in continuity_packet.excluded_context)
            )
            working_memory = (
                []
                if suppress_working_memory
                else self.session_manager.get_working_context(self.write_policy)
                if self.session_manager
                else None
            )
            retrieved_context: list[RetrievedFact] = []
            if self.episodic is not None or self.semantic is not None:
                try:
                    retrieved_context = self.retrieval.retrieve(
                        query=transcript,
                        n=3,
                        cache_manager=self.cache_manager,
                        episodic=self.episodic,
                        semantic=self.semantic,
                    )
                except Exception:
                    retrieved_context = []
            tool_results: list[ToolResult] = []
            tool_context: str | None = None
            if tool_name is not None:
                context.advance(ConversationState.ACTING)
                normalized_input = dict(tool_input or {})
                tool_result = self._execute_tool(tool_name, normalized_input)
                tool_results.append(tool_result)
                tool_context = self._format_tool_result_for_prompt(tool_result)

            prompt_envelope = assemble_prompt_envelope(
                transcript,
                self.personality,
                working_memory=working_memory,
                session_continuity=session_continuity,
                retrieved_context=retrieved_context,
                tool_context=tool_context,
            )

            prompt = render_flat_prompt(prompt_envelope)
            llm_started_at = time.perf_counter()
            try:
                response = bound_single_turn_response(self.llm.generate_envelope(prompt_envelope))
            finally:
                if voice_turn_started_at is not None:
                    phase_durations_ms["llm_ms"] = _elapsed_ms(llm_started_at)
            if not response.strip():
                return self._fail(
                    context,
                    transcript=transcript,
                    response_text=response,
                    reason="LLM returned empty response",
                    raw_audio_path=raw_audio_path,
                    phase_durations_ms=_voice_phase_durations(phase_durations_ms, voice_turn_started_at),
                    failure_phase="llm" if voice_turn_started_at is not None else _failure_phase_for_state(context.state),
                )
            context.advance(ConversationState.RESPONDING)
            response = apply_personality_style_guard(
                response,
                compile_personality_policy(self.personality),
                modality="voice" if speak_response else "text",
            )
            response_text = sanitize_for_tts(response)
            if speak_response:
                return self._speak_or_degrade(
                    context,
                    transcript=transcript,
                    response_text=response_text,
                    final_prompt_text=prompt,
                    tool_results=tool_results,
                    retrieved_memory_refs=[fact.turn_id for fact in retrieved_context],
                    raw_audio_path=raw_audio_path,
                    phase_durations_ms=phase_durations_ms,
                    voice_turn_started_at=voice_turn_started_at,
                )
            context.advance(ConversationState.IDLE)
            result = TurnResult(
                turn_id=context.turn_id,
                session_id=context.session_id,
                transcript=transcript,
                response_text=response_text,
                final_state=context.state,
                tool_calls=self._to_tool_calls(tool_results),
                tool_results=self._to_tool_results(tool_results),
                raw_audio_path=raw_audio_path,
                active_personality_profile_id=self.personality.profile_id,
                profile_epoch=self.session_manager.profile_epoch if self.session_manager else 0,
                phase_durations_ms=_voice_phase_durations(phase_durations_ms, voice_turn_started_at),
            )
            self._record_artifact(
                context,
                result,
                final_prompt_text=prompt,
                retrieved_memory_refs=[fact.turn_id for fact in retrieved_context],
            )
            return result
        except Exception as exc:
            return self._fail(
                context,
                transcript=transcript,
                response_text=None,
                reason=str(exc),
                raw_audio_path=raw_audio_path,
                phase_durations_ms=_voice_phase_durations(phase_durations_ms, voice_turn_started_at),
                failure_phase=_failure_phase_for_state(context.state),
            )

    def _speak_or_degrade(
        self,
        context: TurnContext,
        *,
        transcript: str,
        response_text: str,
        final_prompt_text: str,
        tool_results: list[ToolResult] | None = None,
        retrieved_memory_refs: list[str] | None = None,
        raw_audio_path: str | None = None,
        phase_durations_ms: dict[str, float] | None = None,
        voice_turn_started_at: float | None = None,
    ) -> TurnResult:
        phase_durations_ms = phase_durations_ms if phase_durations_ms is not None else {}
        if not self.tts.is_available():
            context.advance(ConversationState.IDLE)
            result = TurnResult(
                turn_id=context.turn_id,
                session_id=context.session_id,
                transcript=transcript,
                response_text=response_text,
                final_state=context.state,
                tts_degraded=True,
                tts_degraded_reason="TTS runtime is unavailable",
                tool_calls=self._to_tool_calls(tool_results or []),
                tool_results=self._to_tool_results(tool_results or []),
                raw_audio_path=raw_audio_path,
                active_personality_profile_id=self.personality.profile_id,
                profile_epoch=self.session_manager.profile_epoch if self.session_manager else 0,
                phase_durations_ms=_voice_phase_durations(phase_durations_ms, voice_turn_started_at),
            )
            self._record_artifact(
                context,
                result,
                final_prompt_text=final_prompt_text,
                retrieved_memory_refs=retrieved_memory_refs,
            )
            return result

        tts_started_at = time.perf_counter()
        try:
            audio = self.tts.synthesize(response_text)
            sample_rate = self.tts.sample_rate()
        finally:
            if voice_turn_started_at is not None:
                phase_durations_ms["tts_synth_ms"] = _elapsed_ms(tts_started_at)
        context.advance(ConversationState.SPEAKING)
        if self.barge_in_detector is not None and self.interruption_audio_chunks is not None:
            return self._play_with_interruption_monitor(
                context,
                transcript=transcript,
                response_text=response_text,
                final_prompt_text=final_prompt_text,
                retrieved_memory_refs=retrieved_memory_refs,
                audio=audio,
                sample_rate=sample_rate,
                raw_audio_path=raw_audio_path,
                phase_durations_ms=phase_durations_ms,
                voice_turn_started_at=voice_turn_started_at,
            )
        playback_started_at = time.perf_counter()
        try:
            self.playback_api.play(audio, sample_rate)
        finally:
            if voice_turn_started_at is not None:
                phase_durations_ms["playback_ms"] = _elapsed_ms(playback_started_at)
        tts_output_device = getattr(self.playback_api, "last_output_device", lambda: None)()
        context.advance(ConversationState.IDLE)
        result = TurnResult(
            turn_id=context.turn_id,
            session_id=context.session_id,
            transcript=transcript,
            response_text=response_text,
            final_state=context.state,
            tts_output_device=tts_output_device,
            raw_audio_path=raw_audio_path,
            active_personality_profile_id=self.personality.profile_id,
            profile_epoch=self.session_manager.profile_epoch if self.session_manager else 0,
            phase_durations_ms=_voice_phase_durations(phase_durations_ms, voice_turn_started_at),
        )
        self._record_artifact(
            context,
            result,
            final_prompt_text=final_prompt_text,
            retrieved_memory_refs=retrieved_memory_refs,
        )
        return result

    def _play_with_interruption_monitor(
        self,
        context: TurnContext,
        *,
        transcript: str,
        response_text: str,
        final_prompt_text: str,
        audio: np.ndarray,
        sample_rate: int,
        tool_results: list[ToolResult] | None = None,
        retrieved_memory_refs: list[str] | None = None,
        raw_audio_path: str | None = None,
        phase_durations_ms: dict[str, float] | None = None,
        voice_turn_started_at: float | None = None,
    ) -> TurnResult:
        phase_durations_ms = phase_durations_ms if phase_durations_ms is not None else {}
        assert self.barge_in_detector is not None
        self.barge_in_detector.reset()
        playback_started_at = time.perf_counter()
        self.playback_api.start(audio, sample_rate)
        chunks = iter(self.interruption_audio_chunks or [])
        while self._playback_is_playing():
            try:
                chunk = next(chunks)
            except StopIteration:
                break
            if self.barge_in_detector.detect(chunk):
                self.playback_api.stop()
                event: dict[str, object] = {
                    "type": "barge_in",
                    "timestamp": timestamp_now(),
                    "recovery_state": ConversationState.RECOVERING.value,
                }
                interruption_events: list[dict[str, object]] = [event]
                context.advance(ConversationState.INTERRUPTED)
                context.advance(ConversationState.RECOVERING)
                context.advance(ConversationState.IDLE)
                if voice_turn_started_at is not None:
                    phase_durations_ms["playback_ms"] = _elapsed_ms(playback_started_at)
                result = TurnResult(
                    turn_id=context.turn_id,
                    session_id=context.session_id,
                    transcript=transcript,
                    response_text=response_text,
                    final_state=context.state,
                    interrupted=True,
                    interruption_events=interruption_events,
                    tool_calls=self._to_tool_calls(tool_results or []),
                    tool_results=self._to_tool_results(tool_results or []),
                    raw_audio_path=raw_audio_path,
                    active_personality_profile_id=self.personality.profile_id,
                    profile_epoch=self.session_manager.profile_epoch if self.session_manager else 0,
                    phase_durations_ms=_voice_phase_durations(phase_durations_ms, voice_turn_started_at),
                )
                self._record_artifact(
                    context,
                    result,
                    final_prompt_text=final_prompt_text,
                    retrieved_memory_refs=retrieved_memory_refs,
                )
                return result

        context.advance(ConversationState.IDLE)
        if voice_turn_started_at is not None:
            phase_durations_ms["playback_ms"] = _elapsed_ms(playback_started_at)
        result = TurnResult(
            turn_id=context.turn_id,
            session_id=context.session_id,
            transcript=transcript,
            response_text=response_text,
            final_state=context.state,
            tool_calls=self._to_tool_calls(tool_results or []),
            tool_results=self._to_tool_results(tool_results or []),
            raw_audio_path=raw_audio_path,
            active_personality_profile_id=self.personality.profile_id,
            profile_epoch=self.session_manager.profile_epoch if self.session_manager else 0,
            phase_durations_ms=_voice_phase_durations(phase_durations_ms, voice_turn_started_at),
        )
        self._record_artifact(
            context,
            result,
            final_prompt_text=final_prompt_text,
            retrieved_memory_refs=retrieved_memory_refs,
        )
        return result

    def _playback_is_playing(self) -> bool:
        is_playing = getattr(self.playback_api, "is_playing", None)
        if not callable(is_playing):
            return False
        return bool(is_playing())

    def _fail(
        self,
        context: TurnContext,
        *,
        transcript: str | None,
        response_text: str | None,
        reason: str,
        raw_audio_path: str | None = None,
        phase_durations_ms: dict[str, float] | None = None,
        failure_phase: str | None = None,
    ) -> TurnResult:
        if context.state != ConversationState.FAILED:
            context.advance(ConversationState.FAILED)
        result = TurnResult(
            turn_id=context.turn_id,
            session_id=context.session_id,
            transcript=transcript,
            response_text=response_text,
            final_state=context.state,
            failure_reason=reason,
            raw_audio_path=raw_audio_path,
            active_personality_profile_id=self.personality.profile_id,
            profile_epoch=self.session_manager.profile_epoch if self.session_manager else 0,
            phase_durations_ms=phase_durations_ms or {},
            failure_phase=failure_phase,
        )
        self._record_artifact(context, result, final_prompt_text=None)
        return result

    def _create_context(self, modality: str) -> TurnContext:
        if self.session_manager is not None:
            if modality not in {"voice", "text"}:
                raise ValueError("modality must be voice or text")
            return self.session_manager.create_turn_context(modality, phase_observer=self.phase_observer)  # type: ignore[arg-type]
        if modality == "voice":
            return TurnContext(session_id=self.session_id, modality="voice", phase_observer=self.phase_observer)
        if modality == "text":
            return TurnContext(session_id=self.session_id, modality="text", phase_observer=self.phase_observer)
        raise ValueError("modality must be voice or text")

    def _record_artifact(
        self,
        context: TurnContext,
        result: TurnResult,
        *,
        final_prompt_text: str | None,
        retrieved_memory_refs: list[str] | None = None,
    ) -> None:
        if self.session_manager is None:
            return
        artifact = TurnArtifact(
            turn_id=result.turn_id,
            session_id=result.session_id,
            input_modality=context.modality,
            active_personality_profile_id=self.personality.profile_id,
            profile_epoch=self.session_manager.profile_epoch,
            transcript=result.transcript,
            final_prompt_text=final_prompt_text,
            retrieved_memory_refs=list(retrieved_memory_refs or []),
            raw_audio_path=result.raw_audio_path,
            response_text=result.response_text,
            final_state=result.final_state.value,
            failure_reason=result.failure_reason,
            tts_degraded=result.tts_degraded,
            tts_degraded_reason=result.tts_degraded_reason,
            tts_output_device=result.tts_output_device,
            runtime_context=self._runtime_context(context, result),
            interruption_events=result.interruption_events,
            tools_invoked=[str(call["tool_name"]) for call in result.tool_calls if isinstance(call.get("tool_name"), str)],
            agent_trace={"tool_calls": result.tool_calls, "tool_results": result.tool_results} if result.tool_calls else None,
            phase_timestamps={state: timestamp.isoformat() for state, timestamp in context.phase_timestamps.items()},
            phase_durations_ms=dict(result.phase_durations_ms),
            failure_phase=result.failure_phase,
        )
        self.session_manager.record_turn_artifact(artifact)
        if self.episodic is not None:
            try:
                self.episodic.write_entry(artifact, self.write_policy)
            except Exception:
                pass
        if result.failure_reason is None:
            self.session_manager.update_working_memory(result.response_text, self.write_policy)

    def _runtime_context(self, context: TurnContext, result: TurnResult) -> dict[str, str]:
        phases = set(context.phase_timestamps)
        runtime_context: dict[str, str] = {}
        if context.modality == "voice" and "TRANSCRIBING" in phases:
            runtime_context["stt"] = _runtime_device_label(self.stt)
        if "REASONING" in phases:
            runtime_context["llm"] = self.llm.runtime_name()
        if (
            context.modality == "voice"
            and (
                "SPEAKING" in phases
                or result.tts_degraded
                or result.tts_output_device is not None
            )
        ):
            runtime_context["tts"] = _runtime_device_label(self.tts)
        return runtime_context

    def _persist_voice_audio(self, context: TurnContext, audio: np.ndarray, sample_rate: int) -> str | None:
        if self.session_manager is None:
            return None
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return None
        session_dir = self.session_manager.turns_base_dir / context.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        audio_path = session_dir / f"{context.turn_id}.wav"
        clipped = np.clip(samples, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype("<i2")
        with wave.open(str(audio_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(int(sample_rate))
            wav_file.writeframes(pcm16.tobytes())
        return str(audio_path)

    def _execute_tool(self, tool_name: str, tool_input: dict[str, object]) -> ToolResult:
        if self.tool_registry is None:
            return ToolResult(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output="",
                error="tool registry is not configured",
                success=False,
            )
        return self.executor.execute(tool_name, tool_input, self.tool_registry)

    def _format_tool_result_for_prompt(self, result: ToolResult) -> str:
        if result.success:
            return f"tool={result.tool_name}\ninput={result.tool_input}\noutput={result.tool_output}"
        return f"tool={result.tool_name}\ninput={result.tool_input}\nerror={result.error or 'unknown error'}"

    def _to_tool_calls(self, results: list[ToolResult]) -> list[dict[str, object]]:
        return [{"tool_name": r.tool_name, "tool_input": r.tool_input} for r in results]

    def _to_tool_results(self, results: list[ToolResult]) -> list[dict[str, object]]:
        return [
            {
                "tool_name": r.tool_name,
                "tool_input": r.tool_input,
                "tool_output": r.tool_output,
                "error": r.error,
                "success": r.success,
            }
            for r in results
        ]


def timestamp_now() -> str:
    from backend.app.conversation.turn_manager import utc_now

    return utc_now().isoformat()


def _runtime_device_label(runtime: object) -> str:
    runtime_name = getattr(runtime, "runtime_name", None)
    if callable(runtime_name):
        label = str(runtime_name())
    else:
        class_name = runtime.__class__.__name__.lstrip("_")
        for suffix in ("Runtime",):
            if class_name.endswith(suffix):
                class_name = class_name[: -len(suffix)]
                break
        first_pass = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", class_name)
        label = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", first_pass).lower()
    device = getattr(runtime, "device", None)
    return f"{label}/{device or 'unknown'}"


def _elapsed_ms(started_at: float) -> float:
    return round(max(0.0, (time.perf_counter() - started_at) * 1000.0), 3)


def _voice_phase_durations(phase_durations_ms: dict[str, float], voice_turn_started_at: float | None) -> dict[str, float]:
    if voice_turn_started_at is None:
        return {}
    durations = dict(phase_durations_ms)
    durations["total_voice_turn_ms"] = _elapsed_ms(voice_turn_started_at)
    return durations


def _failure_phase_for_state(state: ConversationState) -> str:
    if state == ConversationState.LISTENING:
        return "capture"
    if state == ConversationState.TRANSCRIBING:
        return "stt"
    if state in {ConversationState.REASONING, ConversationState.ACTING}:
        return "llm"
    if state == ConversationState.RESPONDING:
        return "tts"
    if state == ConversationState.SPEAKING:
        return "playback"
    return "turn-state"
