from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np

from backend.app.cognition.prompt_assembler import assemble_prompt
from backend.app.cognition.responder import sanitize_for_tts
from backend.app.conversation.states import ConversationState
from backend.app.conversation.turn_manager import TurnContext
from backend.app.personality.schema import PersonalityProfile
from backend.app.runtimes.llm.base import LLMBase
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


class TurnEngine:
    def __init__(
        self,
        *,
        stt: STTBase,
        tts: TTSBase,
        llm: LLMBase,
        personality: PersonalityProfile,
        session_id: str | None = None,
    ) -> None:
        self.stt = stt
        self.tts = tts
        self.llm = llm
        self.personality = personality
        self.session_id = session_id or uuid4().hex

    def run_text_turn(self, text: str) -> TurnResult:
        transcript = text.strip()
        context = TurnContext(session_id=self.session_id, modality="text")
        if not transcript:
            return self._fail(context, transcript=None, response_text=None, reason="text input is empty")
        return self._run_reasoning_path(context, transcript, speak_response=False)

    def run_voice_turn(self, audio: np.ndarray, sample_rate: int) -> TurnResult:
        context = TurnContext(session_id=self.session_id, modality="voice")
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
            prompt = assemble_prompt(transcript, self.personality)
            response = self.llm.generate(prompt)
            if not response.strip():
                return self._fail(context, transcript=transcript, response_text=response, reason="LLM returned empty response")
            context.advance(ConversationState.RESPONDING)
            response_text = sanitize_for_tts(response)
            if speak_response:
                return self._speak_or_degrade(context, transcript=transcript, response_text=response_text)
            context.advance(ConversationState.IDLE)
            return TurnResult(
                turn_id=context.turn_id,
                session_id=context.session_id,
                transcript=transcript,
                response_text=response_text,
                final_state=context.state,
            )
        except Exception as exc:
            return self._fail(context, transcript=transcript, response_text=None, reason=str(exc))

    def _speak_or_degrade(self, context: TurnContext, *, transcript: str, response_text: str) -> TurnResult:
        if not self.tts.is_available():
            context.advance(ConversationState.IDLE)
            return TurnResult(
                turn_id=context.turn_id,
                session_id=context.session_id,
                transcript=transcript,
                response_text=response_text,
                final_state=context.state,
                tts_degraded=True,
                tts_degraded_reason="TTS runtime is unavailable",
            )

        audio = self.tts.synthesize(response_text)
        sample_rate = self.tts.sample_rate()
        context.advance(ConversationState.SPEAKING)
        playback.play(audio, sample_rate)
        context.advance(ConversationState.IDLE)
        return TurnResult(
            turn_id=context.turn_id,
            session_id=context.session_id,
            transcript=transcript,
            response_text=response_text,
            final_state=context.state,
        )

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
        return TurnResult(
            turn_id=context.turn_id,
            session_id=context.session_id,
            transcript=transcript,
            response_text=response_text,
            final_state=context.state,
            failure_reason=reason,
        )