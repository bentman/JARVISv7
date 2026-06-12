from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable
from uuid import uuid4

import numpy as np

from backend.app.cognition.prompt_assembler import assemble_prompt_envelope
from backend.app.cognition.prompt_envelope import PromptSegment
from backend.app.cognition.prompt_renderer import render_flat_prompt
from backend.app.cognition.responder import bound_single_turn_response, sanitize_for_tts
from backend.app.cognition.style_guard import apply_personality_style_guard
from backend.app.cognition.executor import ToolExecutor, ToolResult
from backend.app.cache.manager import CacheManager
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.conversation.turn_manager import TurnContext
from backend.app.memory.write_policy import WritePolicy
from backend.app.memory.episodic import EpisodicMemory
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
        self.retrieval = RetrievalManager()

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
        try:
            context.advance(ConversationState.LISTENING)
            context.advance(ConversationState.TRANSCRIBING)
            transcript = self.stt.transcribe(np.asarray(audio, dtype=np.float32), sample_rate)
            if not transcript.strip():
                return self._fail(context, transcript=transcript, response_text=None, reason="STT returned empty transcript")
            return self._run_reasoning_path(
                context,
                transcript,
                speak_response=True,
                tool_name=tool_name,
                tool_input=tool_input,
            )
        except Exception as exc:
            return self._fail(context, transcript=None, response_text=None, reason=str(exc))

    def enter_stub_state(self, state: ConversationState) -> None:
        if state == ConversationState.SPEAKING:
            return
        if state in {ConversationState.ACTING, ConversationState.INTERRUPTED}:
            raise NotImplementedError(f"{state.value} behavior pending C.2 / C.5")
        raise ValueError(f"state is not stubbed in C.1: {state.value}")

    def _run_reasoning_path(
        self,
        context: TurnContext,
        transcript: str,
        *,
        speak_response: bool,
        tool_name: str | None = None,
        tool_input: dict[str, object] | None = None,
    ) -> TurnResult:
        try:
            context.advance(ConversationState.REASONING)
            working_memory = self.session_manager.get_working_context(self.write_policy) if self.session_manager else None
            retrieved_context: list[RetrievedFact] = []
            if self.episodic is not None:
                try:
                    retrieved_context = self.retrieval.retrieve(
                        query=transcript,
                        n=3,
                        cache_manager=self.cache_manager,
                        episodic=self.episodic,
                    )
                except Exception:
                    retrieved_context = []
            prompt_envelope = assemble_prompt_envelope(
                transcript,
                self.personality,
                working_memory=working_memory,
                retrieved_context=retrieved_context,
            )

            tool_results: list[ToolResult] = []
            if tool_name is not None:
                context.advance(ConversationState.ACTING)
                normalized_input = dict(tool_input or {})
                tool_result = self._execute_tool(tool_name, normalized_input)
                tool_results.append(tool_result)
                tool_context = self._format_tool_result_for_prompt(tool_result)
                prompt_envelope = prompt_envelope.with_segment(
                    PromptSegment(
                        authority="tool",
                        content_type="tool_result",
                        trusted=False,
                        text=f"Tool execution context:\n{tool_context}",
                    )
                )

            prompt = render_flat_prompt(prompt_envelope)
            response = bound_single_turn_response(self.llm.generate_envelope(prompt_envelope))
            if not response.strip():
                return self._fail(context, transcript=transcript, response_text=response, reason="LLM returned empty response")
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
            )
            self._record_artifact(
                context,
                result,
                final_prompt_text=prompt,
                retrieved_memory_refs=[fact.turn_id for fact in retrieved_context],
            )
            return result
        except Exception as exc:
            return self._fail(context, transcript=transcript, response_text=None, reason=str(exc))

    def _speak_or_degrade(
        self,
        context: TurnContext,
        *,
        transcript: str,
        response_text: str,
        final_prompt_text: str,
        tool_results: list[ToolResult] | None = None,
        retrieved_memory_refs: list[str] | None = None,
    ) -> TurnResult:
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
            )
            self._record_artifact(
                context,
                result,
                final_prompt_text=final_prompt_text,
                retrieved_memory_refs=retrieved_memory_refs,
            )
            return result

        audio = self.tts.synthesize(response_text)
        sample_rate = self.tts.sample_rate()
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
            )
        self.playback_api.play(audio, sample_rate)
        tts_output_device = getattr(self.playback_api, "last_output_device", lambda: None)()
        context.advance(ConversationState.IDLE)
        result = TurnResult(
            turn_id=context.turn_id,
            session_id=context.session_id,
            transcript=transcript,
            response_text=response_text,
            final_state=context.state,
            tts_output_device=tts_output_device,
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
    ) -> TurnResult:
        assert self.barge_in_detector is not None
        self.barge_in_detector.reset()
        self.playback_api.start(audio, sample_rate)
        for chunk in self.interruption_audio_chunks or []:
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
                )
                self._record_artifact(
                    context,
                    result,
                    final_prompt_text=final_prompt_text,
                    retrieved_memory_refs=retrieved_memory_refs,
                )
                return result

        context.advance(ConversationState.IDLE)
        result = TurnResult(
            turn_id=context.turn_id,
            session_id=context.session_id,
            transcript=transcript,
            response_text=response_text,
            final_state=context.state,
            tool_calls=self._to_tool_calls(tool_results or []),
            tool_results=self._to_tool_results(tool_results or []),
        )
        self._record_artifact(
            context,
            result,
            final_prompt_text=final_prompt_text,
            retrieved_memory_refs=retrieved_memory_refs,
        )
        return result

    def _fail(
        self,
        context: TurnContext,
        *,
        transcript: str | None,
        response_text: str | None,
        reason: str,
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
        )
        self._record_artifact(context, result, final_prompt_text=None)
        return result

    def _create_context(self, modality: str) -> TurnContext:
        if self.session_manager is not None:
            if modality not in {"voice", "text"}:
                raise ValueError("modality must be voice or text")
            return self.session_manager.create_turn_context(modality)  # type: ignore[arg-type]
        if modality == "voice":
            return TurnContext(session_id=self.session_id, modality="voice")
        if modality == "text":
            return TurnContext(session_id=self.session_id, modality="text")
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
            transcript=result.transcript,
            final_prompt_text=final_prompt_text,
            retrieved_memory_refs=list(retrieved_memory_refs or []),
            response_text=result.response_text,
            final_state=result.final_state.value,
            failure_reason=result.failure_reason,
            tts_degraded=result.tts_degraded,
            tts_degraded_reason=result.tts_degraded_reason,
            tts_output_device=result.tts_output_device,
            interruption_events=result.interruption_events,
            tools_invoked=[str(call["tool_name"]) for call in result.tool_calls if isinstance(call.get("tool_name"), str)],
            agent_trace={"tool_calls": result.tool_calls, "tool_results": result.tool_results} if result.tool_calls else None,
            phase_timestamps={state: timestamp.isoformat() for state, timestamp in context.phase_timestamps.items()},
        )
        self.session_manager.record_turn_artifact(artifact)
        if self.episodic is not None:
            try:
                self.episodic.write_entry(artifact, self.write_policy)
            except Exception:
                pass
        if result.failure_reason is None:
            self.session_manager.update_working_memory(result.response_text, self.write_policy)

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
