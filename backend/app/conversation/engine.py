from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable
from uuid import uuid4

import numpy as np

from backend.app.cognition.prompt_assembler import assemble_prompt
from backend.app.cognition.responder import sanitize_for_tts
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.conversation.turn_manager import TurnContext
from backend.app.memory.write_policy import WritePolicy
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
    interrupted: bool = False
    interruption_events: list[dict[str, object]] = field(default_factory=list)


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

    def run_text_turn(self, text: str) -> TurnResult:
        transcript = text.strip()
        context = self._create_context("text")
        if not transcript:
            return self._fail(context, transcript=None, response_text=None, reason="text input is empty")
        return self._run_reasoning_path(context, transcript, speak_response=False)

    def run_voice_turn(self, audio: np.ndarray, sample_rate: int) -> TurnResult:
        context = self._create_context("voice")
        try:
            context.advance(ConversationState.LISTENING)
            context.advance(ConversationState.TRANSCRIBING)
            transcript = self.stt.transcribe(np.asarray(audio, dtype=np.float32), sample_rate)
            if not transcript.strip():
                return self._fail(context, transcript=transcript, response_text=None, reason="STT returned empty transcript")
            return self._run_reasoning_path(context, transcript, speak_response=True)
        except Exception as exc:
            return self._fail(context, transcript=None, response_text=None, reason=str(exc))

    def enter_stub_state(self, state: ConversationState) -> None:
        if state == ConversationState.SPEAKING:
            return
        if state in {ConversationState.ACTING, ConversationState.INTERRUPTED}:
            raise NotImplementedError(f"{state.value} behavior pending C.2 / C.5")
        raise ValueError(f"state is not stubbed in C.1: {state.value}")

    def _run_reasoning_path(self, context: TurnContext, transcript: str, *, speak_response: bool) -> TurnResult:
        try:
            context.advance(ConversationState.REASONING)
            working_memory = self.session_manager.get_working_context(self.write_policy) if self.session_manager else None
            prompt = assemble_prompt(transcript, self.personality, working_memory=working_memory)
            response = self.llm.generate(prompt)
            if not response.strip():
                return self._fail(context, transcript=transcript, response_text=response, reason="LLM returned empty response")
            context.advance(ConversationState.RESPONDING)
            response_text = sanitize_for_tts(response)
            if speak_response:
                return self._speak_or_degrade(
                    context,
                    transcript=transcript,
                    response_text=response_text,
                    final_prompt_text=prompt,
                )
            context.advance(ConversationState.IDLE)
            result = TurnResult(
                turn_id=context.turn_id,
                session_id=context.session_id,
                transcript=transcript,
                response_text=response_text,
                final_state=context.state,
            )
            self._record_artifact(context, result, final_prompt_text=prompt)
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
            )
            self._record_artifact(context, result, final_prompt_text=final_prompt_text)
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
                audio=audio,
                sample_rate=sample_rate,
            )
        self.playback_api.play(audio, sample_rate)
        context.advance(ConversationState.IDLE)
        result = TurnResult(
            turn_id=context.turn_id,
            session_id=context.session_id,
            transcript=transcript,
            response_text=response_text,
            final_state=context.state,
        )
        self._record_artifact(context, result, final_prompt_text=final_prompt_text)
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
                )
                self._record_artifact(context, result, final_prompt_text=final_prompt_text)
                return result

        context.advance(ConversationState.IDLE)
        result = TurnResult(
            turn_id=context.turn_id,
            session_id=context.session_id,
            transcript=transcript,
            response_text=response_text,
            final_state=context.state,
        )
        self._record_artifact(context, result, final_prompt_text=final_prompt_text)
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

    def _record_artifact(self, context: TurnContext, result: TurnResult, *, final_prompt_text: str | None) -> None:
        if self.session_manager is None:
            return
        artifact = TurnArtifact(
            turn_id=result.turn_id,
            session_id=result.session_id,
            input_modality=context.modality,
            active_personality_profile_id=self.personality.profile_id,
            transcript=result.transcript,
            final_prompt_text=final_prompt_text,
            response_text=result.response_text,
            final_state=result.final_state.value,
            failure_reason=result.failure_reason,
            tts_degraded=result.tts_degraded,
            tts_degraded_reason=result.tts_degraded_reason,
            interruption_events=result.interruption_events,
            phase_timestamps={state: timestamp.isoformat() for state, timestamp in context.phase_timestamps.items()},
        )
        self.session_manager.record_turn_artifact(artifact)
        if result.failure_reason is None:
            self.session_manager.update_working_memory(result.response_text, self.write_policy)


def timestamp_now() -> str:
    from backend.app.conversation.turn_manager import utc_now

    return utc_now().isoformat()