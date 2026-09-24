from __future__ import annotations

import logging
import re
import threading
import time
import wave
from collections.abc import Callable, Iterable, Iterator
from contextlib import ExitStack, contextmanager, nullcontext, suppress
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import uuid4

import numpy as np
from backend.app.actions.boundaries import ActionCancelledError
from backend.app.actions.catalog import SEARCH_PRIVATE_WEB, SEARCH_PUBLIC_WEB
from backend.app.actions.contracts import (
    ActionCancellationRecord,
    ApprovalAuditRecord,
    AuthorizationContext,
    AuthorizationDecision,
    DelegatedRunRecord,
    ExecutionResultRecord,
    ExecutionStatus,
    ModelActionProposal,
)
from backend.app.agents.invocation import AgentInvocationResult
from backend.app.agents.router import AgentRouter, ends_handoff
from backend.app.agents.schema import AgentProfile
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.cache.manager import CacheManager
from backend.app.cognition.prompt_assembler import assemble_prompt_envelope
from backend.app.cognition.prompt_envelope import PromptEnvelope, PromptSegment
from backend.app.cognition.prompt_renderer import render_flat_prompt
from backend.app.cognition.responder import bound_single_turn_response, sanitize_for_tts
from backend.app.cognition.search_policy import (
    CANCEL_REPLY,
    CONFIRM_REPLY,
    SearchIntentResolver,
    SearchPlan,
    ground_search_prompt,
    grounded_response,
    search_speech,
)
from backend.app.cognition.style_guard import apply_personality_style_guard
from backend.app.cognition.tool_policy import (
    MAX_TURN_TOOL_CALLS,
    ground_tool_prompt,
    tool_offer_budget,
)
from backend.app.conversation.session_manager import SessionManager
from backend.app.conversation.states import ConversationState
from backend.app.conversation.turn_manager import PhaseObserver, TurnContext
from backend.app.memory.episodic import EpisodicMemory
from backend.app.memory.retrieval import RetrievalManager, RetrievedFact
from backend.app.memory.semantic import SemanticMemory
from backend.app.memory.write_policy import WritePolicy
from backend.app.personality.policy import compile_personality_policy
from backend.app.personality.schema import PersonalityProfile
from backend.app.runtimes.internetsearch.page_reader import SearchCancelledError
from backend.app.runtimes.llm.base import LLMBase, ToolCallResult, ToolDefinition
from backend.app.runtimes.stt.barge_in import BargeInDetector
from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.tts import playback
from backend.app.runtimes.tts.base import TTSBase
from backend.app.services.capability_service import CapabilityService, utc_now_iso
from backend.app.services.llm_execution_coordinator import (
    InteractiveTicket,
    LLMExecutionCoordinator,
)
from backend.app.services.search_service import SearchService

logger = logging.getLogger(__name__)


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
    raw_audio_path: str | None = None
    active_personality_profile_id: str = "unknown"
    profile_epoch: int = 0
    phase_durations_ms: dict[str, float] = field(default_factory=dict)
    failure_phase: str | None = None
    search: dict[str, object] | None = None


AGENT_CAPABILITY_PREFIX = "agent-invoke-"


def _extension_delegated_run(run: dict[str, Any], capability_id: str) -> DelegatedRunRecord:
    """An extension run, attributed to the agent profile when an agent delegated it."""
    agent = capability_id.startswith(AGENT_CAPABILITY_PREFIX)
    result = run.get("result")
    return DelegatedRunRecord(
        run_id=run["run_id"],
        kind="agent" if agent else "extension",
        target_id=capability_id.removeprefix(AGENT_CAPABILITY_PREFIX) if agent else run["extension_id"],
        runtime=run["extension_id"].split(":", 1)[0],
        status=run["status"],
        session_id=run["session_id"],
        turn_id=run["turn_id"],
        mode="direct" if agent else None,
        output=result if isinstance(result, dict) else {},
        error=run.get("error"),
    )


def _turn_tools_invoked(context: TurnContext) -> list[str]:
    """Search providers and capabilities actually run during the turn, in order."""
    providers: list[str] = []
    if context.search_operation is not None:
        providers = [
            attempt.provider
            for attempt in context.search_operation.evidence.attempts
            if attempt.status not in {"disabled", "misconfigured"}
        ]
    return list(dict.fromkeys([*providers, *context.tools_invoked]))


@dataclass(slots=True)
class PendingToolApproval:
    """A tool the assistant offered to run, waiting on the user's next reply."""

    proposal: ModelActionProposal
    approval_id: str
    definition_claim: dict[str, Any]
    extension_id: str
    operation_name: str
    # Set when the pending action delegates the turn to an agent (router_selected, handoff).
    mode: str | None = None


@dataclass(slots=True)
class PendingAgentTool:
    """A capability an agent chose that waits on the user's approval before the agent resumes."""

    approval: PendingToolApproval
    profile_id: str
    display_name: str
    mode: str
    envelope: PromptEnvelope


# Which memory layers an agent's memory scope lets it read: (working, episodic, semantic).
_AGENT_MEMORY_LAYERS = {
    "none": (False, False, False),
    "working": (True, False, False),
    "episodic": (True, True, False),
    "semantic": (True, False, True),
    "full": (True, True, True),
}


@dataclass(frozen=True, slots=True)
class ActiveHandoff:
    """An agent that answers this session's turns until the handoff ends."""

    profile_id: str
    display_name: str
    approval_id: str | None
    started_turn_id: str


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
        interruption_audio_chunks: Callable[[], Iterable[np.ndarray] | None] | Iterable[np.ndarray] | None = None,
        playback_api: Any | None = None,
        episodic: EpisodicMemory | None = None,
        cache_manager: CacheManager | None = None,
        semantic: SemanticMemory | None = None,
        llm_coordinator: LLMExecutionCoordinator | None = None,
        search_service: SearchService | None = None,
        search_secret_values: tuple[str, ...] = (),
        capability_service: CapabilityService | None = None,
        extension_runtime: Any | None = None,
        agent_registry: Any | None = None,
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
        self.episodic = episodic
        self.cache_manager = cache_manager
        self.semantic = semantic
        self.llm_coordinator = llm_coordinator
        self.retrieval = RetrievalManager()
        self.phase_observer: PhaseObserver | None = None
        self.search_service = search_service
        self.capability_service = capability_service
        self.extension_runtime = extension_runtime
        self.agent_registry = agent_registry
        self._extension_operation = None
        self._agent_operation = None
        self._active_context: TurnContext | None = None
        self._delegation_mode: str | None = None
        self._pending_agent_tool: PendingAgentTool | None = None
        self._handoff: ActiveHandoff | None = None
        self._pending_tool: PendingToolApproval | None = None
        self._last_tool_result: tuple[str, Any] | None = None
        self.search_intent = SearchIntentResolver(llm, secret_values=search_secret_values)
        self._turn_lock = threading.Lock()
        self._admission_lock = threading.Lock()
        self._idle = threading.Event()
        self._idle.set()
        self._closing = False

    @contextmanager
    def _admit_turn(self) -> Iterator[None]:
        with self._admission_lock:
            if self._closing:
                raise RuntimeError("session is closing")
            if not self._turn_lock.acquire(blocking=False):
                raise RuntimeError("a conversation turn is already active")
            self._idle.clear()
        try:
            yield
        finally:
            self._active_context = None
            self._idle.set()
            self._turn_lock.release()

    def cancel_search(self, session_id: str, turn_id: str) -> bool:
        cancelled = bool(self.search_service and self.search_service.cancel(session_id, turn_id))
        if cancelled:
            self.search_intent.clear()
        return cancelled

    def prepare_close(self, timeout: float = 10.0) -> None:
        with self._admission_lock:
            self._closing = True
        self.search_intent.clear()
        for operation in (self._extension_operation, self._agent_operation):
            if operation is not None:
                operation.cancel.set()
        if self.search_service:
            self.search_service.cancel_and_wait(timeout=0)
        if not self._idle.wait(timeout):
            raise RuntimeError("active turn is cancelling; retry session close after it stops")

    def run_text_turn(self, text: str) -> TurnResult:
        with self._admit_turn():
            return self._run_text_turn(text)

    def run_extension(self, work: Callable, arguments: dict[str, Any], operation: Any) -> dict[str, Any]:
        with self._admit_turn():
            context = self._create_context("text")
            operation.session_id, operation.turn_id = context.session_id, context.turn_id
            self._extension_operation = operation
            result: dict[str, Any] = {}
            failure = None
            try:
                result = work()
                return result
            except Exception:
                failure = "Extension execution failed or was cancelled."
                raise
            finally:
                self._extension_operation = None
                if self.session_manager is not None:
                    runs = self.extension_runtime.runs.list() if self.extension_runtime else []
                    self.session_manager.record_turn_artifact(TurnArtifact(
                        turn_id=context.turn_id, session_id=context.session_id, input_modality="text",
                        final_state="FAILED" if failure else "IDLE", transcript=arguments.get("prompt"),
                        active_personality_profile_id=self.personality.profile_id,
                        profile_epoch=self.session_manager.profile_epoch, failure_reason=failure,
                        delegated_runs=[
                            _extension_delegated_run(run, operation.capability_id).to_dict()
                            for run in runs if run["turn_id"] == context.turn_id
                        ],
                        tools_invoked=[operation.capability_id],
                    ))

    def in_turn_mode(self, turn_id: str) -> str | None:
        """The mode the active turn is delegating in, when `turn_id` is that turn."""
        context = self._active_context
        if context is None or context.turn_id != turn_id:
            return None
        return self._delegation_mode

    def active_handoff(self) -> ActiveHandoff | None:
        return self._handoff

    def end_handoff(self) -> bool:
        ended, self._handoff = self._handoff is not None, None
        return ended

    def run_agent(
        self, profile: AgentProfile, prompt: str, *, mode: str = "direct", operation: Any = None
    ) -> AgentInvocationResult:
        """Run an internal-runtime agent.

        `direct` is admitted as its own turn; every other mode runs inside the turn that
        delegated it, which already holds the turn lock.
        """
        if mode != "direct":
            context = self._active_context
            if operation is None or context is None or context.turn_id != operation.turn_id:
                raise RuntimeError(f"a {mode} agent call must run inside the turn that delegated it")
            return self._delegate_agent(context, profile, prompt, mode, operation)
        with self._admit_turn():
            context = self._create_context("text")
            result: AgentInvocationResult | None = None
            try:
                result = self._delegate_agent(context, profile, prompt, mode, operation)
                return result
            finally:
                if self.session_manager is not None:
                    failure = result.error if result else "Agent run was cancelled."
                    self.session_manager.record_turn_artifact(TurnArtifact(
                        turn_id=context.turn_id,
                        session_id=context.session_id,
                        input_modality="text",
                        final_state="FAILED" if failure else "IDLE",
                        transcript=prompt,
                        active_personality_profile_id=self.personality.profile_id,
                        profile_epoch=self.session_manager.profile_epoch,
                        failure_reason=failure,
                        runtime_context=dict(context.runtime_context),
                        tools_invoked=list(context.tools_invoked),
                        action_proposals=list(context.action_evidence.proposals),
                        authorization_decisions=list(context.action_evidence.authorization_decisions),
                        approval_records=list(context.action_evidence.approvals),
                        action_execution_results=list(context.action_evidence.executions),
                        action_cancellations=list(context.action_evidence.cancellations),
                        delegated_runs=list(context.action_evidence.delegated_runs),
                    ))

    def _delegate_agent(
        self, context: TurnContext, profile: AgentProfile, prompt: str, mode: str, operation: Any
    ) -> AgentInvocationResult:
        self._agent_operation = operation
        status: str = "failure"
        output: dict[str, Any] = {}
        failure: str | None = None
        try:
            if operation is not None:
                operation.check()
            envelope = self._agent_envelope(context, profile, prompt)
            outcome, text = self._agent_answer(context, profile, mode, envelope)
            if operation is not None:
                operation.check()
            if outcome == "success":
                status, output = "success", {"response": bound_single_turn_response(text)}
            elif outcome == "awaiting_approval":
                status, output = "awaiting_approval", {"response": text}
            else:
                failure = text
        except ActionCancelledError:
            status = "cancelled"
            raise
        except Exception as exc:
            failure = str(exc) or type(exc).__name__
        finally:
            self._agent_operation = None
            context.action_evidence.record(DelegatedRunRecord(
                run_id=operation.proposal_id if operation is not None else uuid4().hex,
                kind="agent",
                target_id=profile.profile_id,
                runtime="internal",
                status=status,
                session_id=context.session_id,
                turn_id=context.turn_id,
                mode=mode,
                output=output,
                error=failure,
            ))
        return AgentInvocationResult(
            agent_id=profile.profile_id,
            status=status,
            output=output,
            turn_id=context.turn_id,
            session_id=context.session_id,
            error=failure,
        )

    def _agent_envelope(
        self, context: TurnContext, profile: AgentProfile, prompt: str
    ) -> PromptEnvelope:
        """The agent's prompt, with only the memory layers its scope allows.

        Agents read memory; they never write it. What a turn teaches is retained only through
        the host turn's own write path, so retention stays under the operator's policy.
        """
        read_working, read_episodic, read_semantic = _AGENT_MEMORY_LAYERS[profile.memory_scope]
        working_memory = (
            self.session_manager.get_working_context(self.write_policy)
            if read_working and self.session_manager is not None
            else None
        )
        episodic = self.episodic if read_episodic else None
        semantic = self.semantic if read_semantic else None
        retrieved: list[RetrievedFact] = []
        if episodic is not None or semantic is not None:
            try:
                retrieved = self.retrieval.retrieve(
                    query=prompt, n=3, cache_manager=self.cache_manager,
                    episodic=episodic, semantic=semantic,
                )
            except Exception:
                logger.warning("agent memory retrieval failed; continuing without retrieved memory")
        if profile.memory_scope != "none":
            context.runtime_context["agent_memory"] = {
                "profile_id": profile.profile_id,
                "scope": profile.memory_scope,
                "retrieved": [fact.to_artifact_evidence() for fact in retrieved],
            }
        return assemble_prompt_envelope(
            prompt, self.personality, working_memory=working_memory, retrieved_context=retrieved,
        ).with_segment(PromptSegment(
            authority="application",
            content_type="instruction",
            trusted=True,
            text=f"Agent: {profile.display_name}\n{profile.instructions}",
        ))

    def _agent_tools(
        self, profile: AgentProfile, envelope: PromptEnvelope
    ) -> tuple[tuple[Any, ...], dict[str, dict[str, Any]]]:
        """The capabilities this agent may use: its allowed IDs among the model-facing ones."""
        if not profile.capability_ids or self.extension_runtime is None:
            return (), {}
        allowed = set(profile.capability_ids)
        try:
            entries = [
                entry for entry in self.extension_runtime.tool_catalog()
                if entry["capability_id"] in allowed
            ]
        except Exception:
            return (), {}
        tools = self._offerable_tools(entries, envelope)
        return tools, {entry["capability_id"]: entry for entry in entries}

    def _agent_answer(
        self, context: TurnContext, profile: AgentProfile, mode: str, envelope: PromptEnvelope
    ) -> tuple[str, str]:
        """Answer as the agent: (`success`, answer), (`awaiting_approval`, ask), or (`failure`, why)."""
        tools, entries = self._agent_tools(profile, envelope)
        if not tools:
            return "success", self.llm.generate_envelope(envelope)
        try:
            result = self.llm.generate_with_tools(envelope, tools)
        except Exception as exc:
            context.runtime_context["agent_tool_selection_error"] = str(exc)[:300]
            return "success", self.llm.generate_envelope(envelope)
        if not isinstance(result, ToolCallResult):
            return "success", ""
        if result.call is None:
            return "success", result.text
        entry = entries.get(result.call.name)
        if entry is None:
            return "failure", f"{profile.display_name} chose a capability it is not allowed to use."
        return self._agent_tool_call(context, profile, mode, envelope, result.call, entry)

    def _agent_tool_call(
        self, context: TurnContext, profile: AgentProfile, mode: str,
        envelope: PromptEnvelope, call: Any, entry: dict[str, Any],
    ) -> tuple[str, str]:
        assert self.capability_service is not None
        label = f"{entry['extension_id']} {entry['name']}".strip()
        descriptor = self.capability_service.descriptor(call.name)
        proposal = ModelActionProposal(
            proposal_id=uuid4().hex,
            capability_id=call.name,
            arguments=dict(call.arguments),
            proposed_by=f"agent:{profile.profile_id}",
            reason=f"{profile.display_name} selected this capability",
        )
        pending = PendingToolApproval(
            proposal=proposal,
            approval_id="",
            definition_claim=dict(descriptor.metadata_claims.get("definition", {})) if descriptor else {},
            extension_id=entry["extension_id"],
            operation_name=entry["name"],
            mode=mode,
        )
        decision = self.capability_service.authorize_turn(
            proposal,
            AuthorizationContext(session_id=context.session_id, turn_id=context.turn_id, caller="agent"),
        )
        context.action_evidence.record(proposal)
        if decision.outcome == "approval_required":
            if mode == "direct":
                context.action_evidence.record(decision)
                return "failure", (
                    f"{profile.display_name} needs your approval to run {label}, which the "
                    "Agents panel cannot give. Ask JARVIS for it in a conversation instead."
                )
            pending.approval_id = decision.approval_id or uuid4().hex
            context.action_evidence.record(replace(decision, approval_id=pending.approval_id))
            self._pending_agent_tool = PendingAgentTool(
                pending, profile.profile_id, profile.display_name, mode, envelope
            )
            return "awaiting_approval", f"{profile.display_name} wants to run {label}. Reply yes to confirm."
        context.action_evidence.record(decision)
        if decision.outcome != "allowed":
            return "failure", f"{profile.display_name} cannot use {label}. {decision.reason}"
        return self._finish_agent_tool(context, pending, envelope, approved=False)

    def _finish_agent_tool(
        self, context: TurnContext, pending: PendingToolApproval, envelope: PromptEnvelope,
        *, approved: bool,
    ) -> tuple[str, str]:
        """Run an agent's authorized capability and let the agent answer from its result."""
        assert self.capability_service is not None
        decision, record = self.capability_service.execute_authorized(
            pending.proposal,
            AuthorizationContext(
                session_id=context.session_id,
                turn_id=context.turn_id,
                caller="agent",
                operator_approved=approved,
                approval_id=pending.approval_id or None,
            ),
            definition_claim=pending.definition_claim,
            interactive_input_allowed=False,
        )
        if approved and decision is not None:
            context.action_evidence.record(decision)
        context.action_evidence.record(record)
        context.tools_invoked.append(pending.proposal.capability_id)
        if record.status != "success":
            return "failure", self._tool_failure_text(record)
        grounded = ground_tool_prompt(
            envelope, tool_name=pending.proposal.capability_id, result=record.result, llm=self.llm
        )
        if grounded is None:
            return "failure", "That action returned more than the agent can reason over in one run."
        return "success", self.llm.generate_envelope(grounded)

    def _resolve_pending_agent_tool(self, context: TurnContext, transcript: str) -> str | None:
        """Settle an agent's capability approval and let the paused agent finish."""
        pending, self._pending_agent_tool = self._pending_agent_tool, None
        if pending is None or self.capability_service is None:
            return None
        approval = pending.approval
        text = transcript.strip()
        if CONFIRM_REPLY.fullmatch(text) or CANCEL_REPLY.fullmatch(text):
            confirmed = bool(CONFIRM_REPLY.fullmatch(text))
            context.action_evidence.record(ApprovalAuditRecord(
                approval_id=approval.approval_id,
                proposal_id=approval.proposal.proposal_id,
                capability_id=approval.proposal.capability_id,
                outcome="approved" if confirmed else "denied",
                decided_by="user",
                decided_at=utc_now_iso(),
                reason=(
                    "the user confirmed the agent's proposed action" if confirmed
                    else "the user declined the agent's proposed action"
                ),
            ))
            if not confirmed:
                return "Cancelled."
            outcome, reply = self._finish_agent_tool(context, approval, pending.envelope, approved=True)
            succeeded = outcome == "success"
            response = bound_single_turn_response(reply) if succeeded else ""
            context.action_evidence.record(DelegatedRunRecord(
                run_id=uuid4().hex,
                kind="agent",
                target_id=pending.profile_id,
                runtime="internal",
                status="success" if succeeded else "failure",
                session_id=context.session_id,
                turn_id=context.turn_id,
                mode=pending.mode,
                output={"response": response} if succeeded else {},
                error=None if succeeded else reply,
            ))
            return response if succeeded else f"{pending.display_name} could not finish. {reply}"
        context.action_evidence.record(ActionCancellationRecord(
            proposal_id=approval.proposal.proposal_id,
            capability_id=approval.proposal.capability_id,
            cancelled_by="turn_boundary",
            cancelled_at=utc_now_iso(),
            reason="approval was not confirmed on the next turn",
        ))
        return None

    def _emit_hook(self, event: str, context: TurnContext) -> None:
        if self.extension_runtime is None:
            return
        records = self.extension_runtime.hooks.emit(event, {"session_id": context.session_id, "turn_id": context.turn_id})
        if records:
            context.runtime_context.setdefault("hooks", []).extend(records)

    def _run_text_turn(self, text: str) -> TurnResult:
        ticket = self.llm_coordinator.register_interactive() if self.llm_coordinator else None
        try:
            transcript = text.strip()
            context = self._create_context("text")
            if not transcript:
                return self._fail(context, transcript=None, response_text=None, reason="text input is empty")
            return self._run_reasoning_path(
                context,
                transcript,
                speak_response=False,
                interactive_ticket=ticket,
            )
        finally:
            if ticket is not None:
                ticket.release()

    def run_voice_turn(
        self,
        audio: np.ndarray,
        sample_rate: int,
        *,
        turn_runtime_context: dict[str, object] | None = None,
        interactive_ticket: InteractiveTicket | None = None,
    ) -> TurnResult:
        with self._admit_turn():
            return self._run_voice_turn(audio, sample_rate, turn_runtime_context=turn_runtime_context, interactive_ticket=interactive_ticket)

    def _run_voice_turn(
        self,
        audio: np.ndarray,
        sample_rate: int,
        *,
        turn_runtime_context: dict[str, object] | None = None,
        interactive_ticket: InteractiveTicket | None = None,
    ) -> TurnResult:
        ticket = interactive_ticket
        if ticket is None and self.llm_coordinator is not None:
            ticket = self.llm_coordinator.register_interactive()
        context = self._create_context("voice")
        voice_turn_started_at = time.perf_counter()
        phase_durations_ms: dict[str, float] = {}
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if turn_runtime_context is not None:
            context.runtime_context.update(turn_runtime_context)
            context.runtime_context["stt_input"] = {
                "sample_count": int(samples.size),
                "sample_rate": int(sample_rate),
                "duration_s": int(samples.size) / float(sample_rate) if sample_rate else 0.0,
            }
        raw_audio_path = None
        try:
            context.advance(ConversationState.LISTENING)
            context.advance(ConversationState.TRANSCRIBING)
            stt_started_at = time.perf_counter()
            try:
                transcript = self.stt.transcribe(samples, sample_rate)
            except Exception:
                with suppress(Exception):
                    raw_audio_path = self._persist_voice_audio(context, samples, sample_rate)
                raise
            finally:
                phase_durations_ms["stt_ms"] = _elapsed_ms(stt_started_at)
            raw_audio_path = self._persist_voice_audio(context, samples, sample_rate)
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
                raw_audio_path=raw_audio_path,
                phase_durations_ms=phase_durations_ms,
                voice_turn_started_at=voice_turn_started_at,
                interactive_ticket=ticket,
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
        finally:
            if ticket is not None and interactive_ticket is None:
                ticket.release()

    def _run_reasoning_path(
        self,
        context: TurnContext,
        transcript: str,
        *,
        speak_response: bool,
        raw_audio_path: str | None = None,
        phase_durations_ms: dict[str, float] | None = None,
        voice_turn_started_at: float | None = None,
        interactive_ticket: InteractiveTicket | None = None,
    ) -> TurnResult:
        with ExitStack() as stack:
            # A handed-off conversation belongs to the agent, so no search is opened for it.
            if self._handoff is None and self.search_service and self.search_intent.is_candidate(transcript):
                context.search_operation = stack.enter_context(self.search_service.operation(context.session_id, context.turn_id))
            if interactive_ticket is not None:
                stack.enter_context(interactive_ticket.execution())
            try:
                result = self._reasoning_body(
                    context, transcript, speak_response=speak_response, raw_audio_path=raw_audio_path,
                    phase_durations_ms=phase_durations_ms, voice_turn_started_at=voice_turn_started_at,
                )
            except SearchCancelledError:
                result = self._cancelled_result(context, transcript, raw_audio_path, phase_durations_ms or {}, voice_turn_started_at)
            if context.search_operation:
                result = replace(result, search=context.search_operation.snapshot())
            return result

    def _reasoning_body(
        self,
        context: TurnContext,
        transcript: str,
        *,
        speak_response: bool,
        raw_audio_path: str | None = None,
        phase_durations_ms: dict[str, float] | None = None,
        voice_turn_started_at: float | None = None,
    ) -> TurnResult:
        phase_durations_ms = phase_durations_ms if phase_durations_ms is not None else {}
        self._emit_hook("transcript_committed", context)
        try:
            context.advance(ConversationState.REASONING)
            continuity_packet = (
                self.session_manager.build_continuity_packet(
                    latest_text=transcript,
                    write_policy=self.write_policy,
                )
                if self.session_manager
                else None
            )
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
                    logger.warning("memory retrieval failed; continuing without retrieved memory")
                    retrieved_context = []
            retrieved_memory_refs = [fact.turn_id for fact in retrieved_context]
            retrieved_memory_evidence = [
                fact.to_artifact_evidence() for fact in retrieved_context
            ]
            policy = compile_personality_policy(self.personality)
            prompt_envelope = assemble_prompt_envelope(
                transcript,
                self.personality,
                working_memory=working_memory,
                session_continuity=session_continuity,
                retrieved_context=retrieved_context,
                policy=policy,
            )

            llm_started_at = time.perf_counter()
            self._emit_hook("prompt_assembled", context)
            try:
                response, prompt_envelope = self._generate_response(context, transcript, prompt_envelope, continuity_packet)
                prompt = render_flat_prompt(prompt_envelope)
            finally:
                if voice_turn_started_at is not None:
                    search_ms = context.search_operation.evidence.retrieval_ms if context.search_operation else 0
                    phase_durations_ms["llm_ms"] = max(0.0, _elapsed_ms(llm_started_at) - search_ms)
                    if context.search_operation:
                        phase_durations_ms["search_ms"] = search_ms
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
            self._emit_hook("response_ready", context)
            stored_response = apply_personality_style_guard(
                response,
                policy,
                modality="voice" if speak_response else "text",
            )
            if context.search_operation and context.search_operation.evidence.outcome in {"confirmation_required", "clarification_required"}:
                stored_response = response
            if context.search_operation and context.search_operation.evidence.queries:
                stored_response = grounded_response(stored_response, context.search_operation.evidence)
            self._check_search(context)
            if speak_response:
                voice_text = sanitize_for_tts(search_speech(stored_response) if context.search_operation else stored_response)
                return self._speak_or_degrade(
                    context,
                    transcript=transcript,
                    response_text=stored_response,
                    voice_text=voice_text,
                    final_prompt_text=prompt,
                    retrieved_memory_refs=retrieved_memory_refs,
                    retrieved_memory_evidence=retrieved_memory_evidence,
                    raw_audio_path=raw_audio_path,
                    phase_durations_ms=phase_durations_ms,
                    voice_turn_started_at=voice_turn_started_at,
                )
            context.advance(ConversationState.IDLE)
            result = TurnResult(
                turn_id=context.turn_id,
                session_id=context.session_id,
                transcript=transcript,
                response_text=stored_response,
                final_state=context.state,
                raw_audio_path=raw_audio_path,
                active_personality_profile_id=self.personality.profile_id,
                profile_epoch=self.session_manager.profile_epoch if self.session_manager else 0,
                phase_durations_ms=_voice_phase_durations(phase_durations_ms, voice_turn_started_at),
            )
            self._record_artifact(
                context,
                result,
                final_prompt_text=prompt,
                retrieved_memory_refs=retrieved_memory_refs,
                retrieved_memory_evidence=retrieved_memory_evidence,
            )
            return result
        except SearchCancelledError:
            return self._cancelled_result(context, transcript, raw_audio_path, phase_durations_ms, voice_turn_started_at)
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

    def _record_search_cancellation(self, context: TurnContext) -> None:
        if self.capability_service is None or not context.action_evidence.proposals:
            return
        latest = context.action_evidence.proposals[-1]
        context.action_evidence.record(
            ActionCancellationRecord(
                proposal_id=str(latest["proposal_id"]),
                capability_id=str(latest["capability_id"]),
                cancelled_by="operator",
                cancelled_at=utc_now_iso(),
                reason="the operator cancelled the search",
            )
        )

    def _cancelled_result(self, context: TurnContext, transcript: str, raw_audio_path: str | None,
                          phase_durations_ms: dict[str, float], voice_turn_started_at: float | None) -> TurnResult:
        self._record_search_cancellation(context)
        self.search_intent.clear()
        if context.search_operation:
            context.search_operation.evidence.outcome = "cancelled"
            context.search_operation.evidence.stage = "cancelled"
        if context.state == ConversationState.FAILED:
            context.advance(ConversationState.IDLE)
        elif context.state != ConversationState.IDLE:
            context.advance(ConversationState.INTERRUPTED)
            context.advance(ConversationState.RECOVERING)
            context.advance(ConversationState.IDLE)
        result = TurnResult(
            turn_id=context.turn_id, session_id=context.session_id, transcript=transcript,
            response_text="Search cancelled.", final_state=context.state, raw_audio_path=raw_audio_path,
            active_personality_profile_id=self.personality.profile_id,
            profile_epoch=self.session_manager.profile_epoch if self.session_manager else 0,
            phase_durations_ms=_voice_phase_durations(phase_durations_ms, voice_turn_started_at),
        )
        self._record_artifact(context, result, final_prompt_text=None)
        return result

    def _generate_response(self, context: TurnContext, transcript: str, envelope: PromptEnvelope, continuity: Any) -> tuple[str, PromptEnvelope]:
        settled = self._resolve_pending_tool(context, transcript)
        if settled is not None:
            grounded = self._ground_last_tool(context, envelope)
            if grounded is not None:
                return bound_single_turn_response(self.llm.generate_envelope(grounded)), grounded
            return settled, envelope
        resumed = self._resolve_pending_agent_tool(context, transcript)
        if resumed is not None:
            return resumed, envelope
        operation = context.search_operation
        if operation is None:
            routed = self._route_agent_turn(context, transcript, envelope)
            if routed is not None:
                return routed, envelope
            response, grounded = self._respond_with_tools(context, envelope)
            return bound_single_turn_response(response), grounded
        operation.check()
        prior_topic = ""
        if continuity is not None and continuity.policy_decision in {"start_new_session", "ignore_stale_context", "summarize_and_close"}:
            self.search_intent.clear()
        if continuity is not None and continuity.recent_turn_ids:
            prior_topic = continuity.last_user_request or ""
            if self.session_manager and self.session_manager.turn_artifacts:
                prior = self.session_manager.turn_artifacts[-1]
                if prior.search and prior.search.get("topic"):
                    prior_topic = str(prior.search["topic"])
        plan = self.search_intent.resolve(transcript, context=prior_topic)
        operation.check()
        self._record_search_approval(context)
        if plan.action == "clarify":
            if self.search_intent.pending is not None:
                decision = self._propose_search(context, self.search_intent.pending)
                self.search_intent.pending_action_ref = (
                    (decision.proposal_id, decision.approval_id or "", decision.capability_id)
                    if decision and decision.approval_id
                    else None
                )
                operation.evidence.outcome = "confirmation_required"
            else:
                operation.evidence.outcome = "clarification_required"
            return plan.message, envelope
        if plan.action == "none":
            operation.evidence.outcome = "not_requested"
            return bound_single_turn_response(self.llm.generate_envelope(envelope)), envelope
        assert self.search_service is not None
        decision = self._propose_search(context, plan)
        if decision is not None and decision.outcome != "allowed":
            operation.evidence.outcome = "unavailable"
            return decision.reason, envelope
        context.advance(ConversationState.ACTING)
        retrieval_started = time.perf_counter()
        started_at = utc_now_iso()
        try:
            evidence = self.search_service.retrieve(operation, mode=plan.action, topic=plan.topic, queries=plan.queries)
        finally:
            operation.evidence.retrieval_ms = _elapsed_ms(retrieval_started)
            self._record_search_execution(context, operation.evidence, started_at)
        context.advance(ConversationState.REASONING)
        if not evidence.sources:
            return grounded_response("", evidence), envelope
        grounded = ground_search_prompt(envelope, evidence, self.llm)
        operation.check()
        if grounded is None:
            return grounded_response("", evidence), envelope
        response = bound_single_turn_response(self.llm.generate_envelope(grounded))
        operation.check()
        return response, grounded

    def _respond_with_tools(
        self, context: TurnContext, envelope: PromptEnvelope
    ) -> tuple[str, PromptEnvelope]:
        """Answer, offering eligible capabilities when the runtime can call tools."""
        tools = self._tool_definitions(envelope)
        if not tools:
            return self.llm.generate_envelope(envelope), envelope
        context.runtime_context["tools_offered"] = [tool.name for tool in tools]
        try:
            result = self.llm.generate_with_tools(envelope, tools)
        except Exception as exc:
            # Selection is best-effort: a provider that cannot offer tools must not
            # cost the user their answer, but the turn records why nothing was selectable.
            context.runtime_context["tool_selection_error"] = str(exc)[:300]
            return self.llm.generate_envelope(envelope), envelope
        if not isinstance(result, ToolCallResult) or result.call is None:
            return result.text if isinstance(result, ToolCallResult) else "", envelope
        response = self._run_selected_tool(context, envelope, result.call)
        if response is not None:
            return response, envelope
        grounded = self._ground_last_tool(context, envelope)
        if grounded is None:
            return "That action returned more than I can reason over in one turn.", envelope
        return self.llm.generate_envelope(grounded), grounded

    def _run_selected_tool(
        self, context: TurnContext, envelope: PromptEnvelope, call: Any
    ) -> str | None:
        """Propose, authorize, and run one selected capability.

        Returns a response string when the turn is finished early (approval requested,
        denial, or failure), or None when a result is ready to ground.
        """
        assert self.capability_service is not None
        if len(context.tools_invoked) >= MAX_TURN_TOOL_CALLS:
            return None
        descriptor = self.capability_service.descriptor(call.name)
        if descriptor is None:
            # The model named something the registry does not offer; say so rather than
            # answering as though an action had run.
            return "I tried to use a capability that is not available."
        proposal = ModelActionProposal(
            proposal_id=uuid4().hex,
            capability_id=call.name,
            arguments=dict(call.arguments),
            proposed_by="model",
            reason="the assistant selected this capability for the request",
        )
        decision = self.capability_service.authorize_turn(
            proposal,
            AuthorizationContext(
                session_id=context.session_id,
                turn_id=context.turn_id,
                caller="conversation-turn",
            ),
        )
        context.action_evidence.record(proposal)
        if decision.outcome == "approval_required":
            approval_id = decision.approval_id or uuid4().hex
            context.action_evidence.record(AuthorizationDecision(
                proposal_id=decision.proposal_id,
                capability_id=decision.capability_id,
                outcome=decision.outcome,
                reason=decision.reason,
                approval_required=True,
                approval_id=approval_id,
            ))
            catalog = self._tool_catalog()
            entry = next(
                (item for item in catalog if item["capability_id"] == call.name),
                {"extension_id": call.name, "name": ""},
            )
            self._pending_tool = PendingToolApproval(
                proposal=proposal,
                approval_id=approval_id,
                definition_claim=dict(descriptor.metadata_claims.get("definition", {})),
                extension_id=entry["extension_id"],
                operation_name=entry["name"],
            )
            return (
                f"May I run {entry['extension_id']} {entry['name']}? Reply yes to confirm."
            ).replace("  ", " ")
        context.action_evidence.record(decision)
        if decision.outcome != "allowed":
            return f"I cannot run that action. {decision.reason}"
        pending = PendingToolApproval(
            proposal=proposal,
            approval_id="",
            definition_claim=dict(descriptor.metadata_claims.get("definition", {})),
            extension_id=call.name,
            operation_name="",
        )
        return self._execute_tool(context, pending)

    def _execute_tool(
        self, context: TurnContext, pending: PendingToolApproval, *, approved: bool = False
    ) -> str | None:
        """Run one authorized capability inside the turn.

        Returns failure text when the turn must explain itself, or None when a result is
        ready to ground into the answer.
        """
        assert self.capability_service is not None
        context.advance(ConversationState.ACTING)
        self._delegation_mode = pending.mode or "as_tool"
        try:
            decision, record = self.capability_service.execute_authorized(
                pending.proposal,
                AuthorizationContext(
                    session_id=context.session_id,
                    turn_id=context.turn_id,
                    caller="conversation-turn",
                    operator_approved=approved,
                    approval_id=pending.approval_id or None,
                ),
                definition_claim=pending.definition_claim,
                interactive_input_allowed=False,
            )
        finally:
            self._delegation_mode = None
            context.advance(ConversationState.REASONING)
        if approved and decision is not None:
            context.action_evidence.record(decision)
        context.action_evidence.record(record)
        context.tools_invoked.append(pending.proposal.capability_id)
        if record.status != "success":
            return self._tool_failure_text(record)
        if self._pending_agent_tool is not None:
            # A delegated agent paused for approval; its question is this turn's answer.
            output = record.result.get("output") if isinstance(record.result, dict) else None
            return str(output.get("response", "")) if isinstance(output, dict) else ""
        self._last_tool_result = (pending.proposal.capability_id, record.result)
        return None

    def _ground_last_tool(
        self, context: TurnContext, envelope: PromptEnvelope
    ) -> PromptEnvelope | None:
        last = getattr(self, "_last_tool_result", None)
        if last is None:
            return None
        self._last_tool_result = None
        name, result = last
        return ground_tool_prompt(envelope, tool_name=name, result=result, llm=self.llm)

    def _tool_definitions(self, envelope: PromptEnvelope) -> tuple[Any, ...]:
        """Offer only capabilities the ladder could actually allow right now."""
        if self.capability_service is None:
            return ()
        if not self.llm.supports_tool_calling():
            return ()
        try:
            catalog = self._tool_catalog()
        except Exception:
            return ()
        return self._offerable_tools(catalog, envelope)

    def _offerable_tools(
        self, catalog: list[dict[str, Any]], envelope: PromptEnvelope
    ) -> tuple[Any, ...]:
        if not catalog or self.capability_service is None or not self.llm.supports_tool_calling():
            return ()
        views = {view.capability_id: view for view in self.capability_service.catalog().capabilities}
        offers = []
        for entry in catalog:
            view = views.get(entry["capability_id"])
            if view is None or not getattr(view, "executable", True):
                continue
            if view.availability != "available" or view.readiness == "unavailable":
                continue
            if view.authorization_rule == "deny":
                continue
            offers.append(ToolDefinition(
                name=entry["capability_id"],
                description=entry.get("description")
                or f"{entry['extension_id']} operation '{entry['name']}'",
                input_schema=entry["input_schema"] or {"type": "object"},
            ))
        return tool_offer_budget(envelope, tuple(offers), self.llm)

    def _tool_catalog(self) -> list[dict[str, Any]]:
        """Extension operations plus agents that declare the as_tool mode.

        Only internal-runtime agents are offered: an ACP-runtime agent executes through
        run_extension, which needs the turn lock the proposing turn already holds.
        """
        catalog = list(self.extension_runtime.tool_catalog()) if self.extension_runtime else []
        registry = self.agent_registry
        for profile in registry.profiles() if registry is not None else ():
            if "as_tool" not in profile.invocation_modes or profile.runtime_kind != "internal":
                continue
            if registry.unavailable_reason(profile):
                continue
            catalog.append({
                "capability_id": f"{AGENT_CAPABILITY_PREFIX}{profile.profile_id}",
                "extension_id": f"agent:{profile.profile_id}",
                "name": profile.display_name,
                "description": f"Delegate to the {profile.display_name} agent: {profile.purpose}",
                "input_schema": {
                    "type": "object",
                    "properties": {"prompt": {"type": "string", "minLength": 1, "maxLength": 4000}},
                    "required": ["prompt"],
                    "additionalProperties": False,
                },
            })
        return catalog

    def _resolve_pending_tool(self, context: TurnContext, transcript: str) -> str | None:
        """Settle a tool approval the previous turn asked for.

        Returns a response when the reply settled the approval, otherwise None so the
        turn continues normally.
        """
        pending, self._pending_tool = self._pending_tool, None
        if pending is None or self.capability_service is None:
            return None
        text = transcript.strip()
        if CONFIRM_REPLY.fullmatch(text):
            context.action_evidence.record(ApprovalAuditRecord(
                approval_id=pending.approval_id,
                proposal_id=pending.proposal.proposal_id,
                capability_id=pending.proposal.capability_id,
                outcome="approved",
                decided_by="user",
                decided_at=utc_now_iso(),
                reason="the user confirmed the proposed action",
            ))
            if pending.mode == "handoff":
                return self._start_handoff(context, pending.proposal, pending.approval_id)
            failure = self._execute_tool(context, pending, approved=True)
            if pending.mode is not None:
                return failure or self._agent_reply()
            return failure or ""
        if CANCEL_REPLY.fullmatch(text):
            context.action_evidence.record(ApprovalAuditRecord(
                approval_id=pending.approval_id,
                proposal_id=pending.proposal.proposal_id,
                capability_id=pending.proposal.capability_id,
                outcome="denied",
                decided_by="user",
                decided_at=utc_now_iso(),
                reason="the user declined the proposed action",
            ))
            return "Cancelled."
        context.action_evidence.record(ActionCancellationRecord(
            proposal_id=pending.proposal.proposal_id,
            capability_id=pending.proposal.capability_id,
            cancelled_by="turn_boundary",
            cancelled_at=utc_now_iso(),
            reason="approval was not confirmed on the next turn",
        ))
        return None

    def _route_agent_turn(
        self, context: TurnContext, transcript: str, envelope: PromptEnvelope
    ) -> str | None:
        """Hand the turn to an agent when a handoff is active or the user addressed one.

        Returns the turn's response, or None when the assistant answers as usual.
        """
        if self.agent_registry is None or self.capability_service is None:
            return None
        router = AgentRouter(self.agent_registry)
        if self._handoff is not None:
            if ends_handoff(transcript):
                return self._finish_handoff(context, "the user returned to JARVIS", "Back to JARVIS.")
            return self._handoff_turn(context, router, transcript, envelope)
        request = router.handoff_request(transcript)
        if request is not None:
            return self._request_handoff(context, request, transcript)
        route = router.route(transcript)
        if route is None:
            return None
        if route.reason:
            self._note_route(context, "unavailable", route.profile, route.reason)
            return None
        proposal = self._agent_proposal(
            route.profile, route.task, "router", f"the user addressed {route.profile.display_name}"
        )
        return self._delegate_in_turn(
            context, proposal, route.profile, "router_selected",
            ask=f"May I hand this to {route.profile.display_name}? Reply yes to confirm.",
        )

    def _agent_proposal(
        self, profile: AgentProfile, prompt: str, proposed_by: str, reason: str
    ) -> ModelActionProposal:
        return ModelActionProposal(
            proposal_id=uuid4().hex,
            capability_id=f"{AGENT_CAPABILITY_PREFIX}{profile.profile_id}",
            arguments={"prompt": prompt},
            proposed_by=proposed_by,
            reason=reason,
        )

    def _authorize_agent(
        self, context: TurnContext, proposal: ModelActionProposal, approval_id: str | None
    ) -> AuthorizationDecision:
        assert self.capability_service is not None
        context.action_evidence.record(proposal)
        return self.capability_service.authorize_turn(
            proposal,
            AuthorizationContext(
                session_id=context.session_id,
                turn_id=context.turn_id,
                caller="conversation-turn",
                operator_approved=approval_id is not None,
                approval_id=approval_id,
            ),
        )

    def _park_agent_approval(
        self, context: TurnContext, decision: AuthorizationDecision,
        proposal: ModelActionProposal, profile: AgentProfile, mode: str,
    ) -> None:
        approval_id = decision.approval_id or uuid4().hex
        context.action_evidence.record(replace(decision, approval_id=approval_id))
        self._pending_tool = PendingToolApproval(
            proposal=proposal,
            approval_id=approval_id,
            definition_claim={},
            extension_id=f"agent:{profile.profile_id}",
            operation_name=profile.display_name,
            mode=mode,
        )

    def _delegate_in_turn(
        self,
        context: TurnContext,
        proposal: ModelActionProposal,
        profile: AgentProfile,
        mode: str,
        *,
        ask: str | None = None,
        approval_id: str | None = None,
    ) -> str | None:
        """Authorize and run an agent that answers this turn.

        A routed request falls back to the assistant when the agent cannot answer; a
        handed-off turn reports the failure, since the user is talking to the agent.
        """
        decision = self._authorize_agent(context, proposal, approval_id)
        if decision.outcome == "approval_required" and ask is not None:
            self._park_agent_approval(context, decision, proposal, profile, mode)
            self._note_route(context, "awaiting_approval", profile, decision.reason)
            return ask
        # An approved call's decision is recorded when execution re-authorizes it.
        if approval_id is None or decision.outcome != "allowed":
            context.action_evidence.record(decision)
        if decision.outcome != "allowed":
            self._note_route(context, "denied", profile, decision.reason)
            return None
        failure = self._execute_tool(
            context,
            PendingToolApproval(
                proposal=proposal,
                approval_id=approval_id or "",
                definition_claim={},
                extension_id=f"agent:{profile.profile_id}",
                operation_name=profile.display_name,
                mode=mode,
            ),
            approved=approval_id is not None,
        )
        if failure is not None and self._pending_agent_tool is not None:
            self._note_route(context, "awaiting_approval", profile, "the agent asked to use a capability")
            return failure
        if failure is not None:
            self._last_tool_result = None
            self._note_route(context, "failed", profile, failure)
            return None if mode == "router_selected" else failure
        self._note_route(context, "selected", profile, "")
        return self._agent_reply()

    def _agent_reply(self) -> str:
        last, self._last_tool_result = self._last_tool_result, None
        result = last[1] if last is not None else {}
        output = result.get("output") if isinstance(result, dict) else None
        return str(output.get("response", "")) if isinstance(output, dict) else ""

    def _request_handoff(self, context: TurnContext, request: Any, transcript: str) -> str:
        profile = request.profile
        if request.reason:
            self._note_handoff(context, "refused", profile.profile_id, request.reason)
            return f"I can't hand you over to {profile.display_name}. {request.reason}"
        proposal = self._agent_proposal(
            profile, transcript, "user",
            f"the user asked to hand the conversation to {profile.display_name}",
        )
        decision = self._authorize_agent(context, proposal, None)
        if decision.outcome == "approval_required":
            self._park_agent_approval(context, decision, proposal, profile, "handoff")
            self._note_handoff(context, "awaiting_approval", profile.profile_id, decision.reason)
            return f"May I hand you over to {profile.display_name}? Reply yes to confirm."
        context.action_evidence.record(decision)
        if decision.outcome != "allowed":
            self._note_handoff(context, "refused", profile.profile_id, decision.reason)
            return f"I can't hand you over to {profile.display_name}. {decision.reason}"
        return self._start_handoff(context, proposal, None)

    def _start_handoff(
        self, context: TurnContext, proposal: ModelActionProposal, approval_id: str | None
    ) -> str:
        profile_id = proposal.capability_id.removeprefix(AGENT_CAPABILITY_PREFIX)
        profile = self.agent_registry.get(profile_id) if self.agent_registry else None
        if profile is None:
            self._note_handoff(context, "refused", profile_id, "agent profile no longer exists")
            return "That agent is no longer available."
        self._handoff = ActiveHandoff(profile_id, profile.display_name, approval_id, context.turn_id)
        self._note_handoff(context, "started", profile_id, "")
        return f"You're now talking to {profile.display_name}. Say 'back to JARVIS' to return."

    def _handoff_turn(
        self, context: TurnContext, router: AgentRouter, transcript: str, envelope: PromptEnvelope
    ) -> str:
        assert self._handoff is not None
        handoff = self._handoff
        profile = self.agent_registry.get(handoff.profile_id)
        reason = (
            "its profile no longer exists" if profile is None
            else router.ineligible_reason(profile, "handoff")
        )
        if not reason:
            proposal = self._agent_proposal(
                profile, transcript, "user",
                f"the conversation is handed off to {profile.display_name}",
            )
            response = self._delegate_in_turn(
                context, proposal, profile, "handoff", approval_id=handoff.approval_id
            )
            if response is not None:
                return response
            reason = "it is no longer authorized to answer"
        notice = self._finish_handoff(
            context, reason,
            f"{handoff.display_name} is no longer available ({reason}), so you're back with JARVIS.",
        )
        answer, _ = self._respond_with_tools(context, envelope)
        return f"{notice} {bound_single_turn_response(answer)}".strip()

    def _finish_handoff(self, context: TurnContext, reason: str, message: str) -> str:
        if self._handoff is not None:
            self._note_handoff(context, "ended", self._handoff.profile_id, reason)
        self._handoff = None
        return message

    @staticmethod
    def _note_route(context: TurnContext, outcome: str, profile: AgentProfile, reason: str) -> None:
        context.runtime_context["agent_route"] = {
            "outcome": outcome, "profile_id": profile.profile_id, "reason": reason,
        }

    @staticmethod
    def _note_handoff(context: TurnContext, event: str, profile_id: str, reason: str) -> None:
        context.runtime_context.setdefault("agent_handoff", []).append(
            {"event": event, "profile_id": profile_id, "reason": reason}
        )

    @staticmethod
    def _tool_failure_text(record: ExecutionResultRecord) -> str:
        if record.status == "cancelled":
            return "That action was cancelled before it finished."
        return f"I could not complete that action. {record.error or ''}".strip()

    def _propose_search(self, context: TurnContext, plan: SearchPlan) -> AuthorizationDecision | None:
        if self.capability_service is None:
            return None
        capability_id = SEARCH_PRIVATE_WEB if plan.private else SEARCH_PUBLIC_WEB
        proposal = ModelActionProposal(
            proposal_id=uuid4().hex,
            capability_id=capability_id,
            arguments={"mode": plan.action, "topic": plan.topic, "queries": list(plan.queries)},
            proposed_by="model",
            reason=plan.message or "the user requested a web search",
        )
        approved = self.search_intent.resolved_approval is not None and (
            self.search_intent.resolved_approval[1] == "approved"
        )
        decision = self.capability_service.authorize_turn(
            proposal,
            AuthorizationContext(
                session_id=context.session_id,
                turn_id=context.turn_id,
                caller="conversation-turn",
                operator_approved=approved,
            ),
        )
        if decision.outcome == "approval_required" and not decision.approval_id:
            # The approval record minted on the resuming turn must carry this same id.
            decision = AuthorizationDecision(
                proposal_id=decision.proposal_id,
                capability_id=decision.capability_id,
                outcome=decision.outcome,
                reason=decision.reason,
                approval_required=True,
                approval_id=uuid4().hex,
            )
        context.action_evidence.record(proposal)
        context.action_evidence.record(decision)
        return decision

    def _record_search_approval(self, context: TurnContext) -> None:
        resolved = self.search_intent.resolved_approval
        if self.capability_service is None or resolved is None:
            return
        (proposal_id, approval_id, capability_id), outcome = resolved
        if outcome == "expired":
            context.action_evidence.record(
                ActionCancellationRecord(
                    proposal_id=proposal_id,
                    capability_id=capability_id,
                    cancelled_by="turn_boundary",
                    cancelled_at=utc_now_iso(),
                    reason="approval was not confirmed on the next turn",
                )
            )
            return
        context.action_evidence.record(
            ApprovalAuditRecord(
                approval_id=approval_id,
                proposal_id=proposal_id,
                capability_id=capability_id,
                outcome=outcome,
                decided_by="user",
                decided_at=utc_now_iso(),
                reason="the user answered the outbound search confirmation",
            )
        )

    def _record_search_execution(self, context: TurnContext, evidence: Any, started_at: str) -> None:
        if self.capability_service is None:
            return
        proposals = context.action_evidence.proposals
        if not proposals:
            return
        latest = proposals[-1]
        cancelled = evidence.outcome == "cancelled" or evidence.cancel_requested
        status: ExecutionStatus = (
            "cancelled" if cancelled else "success" if evidence.sources else "failure"
        )
        context.action_evidence.record(
            ExecutionResultRecord(
                proposal_id=str(latest["proposal_id"]),
                capability_id=str(latest["capability_id"]),
                status=status,
                result={
                    "outcome": evidence.outcome,
                    "mode": evidence.mode,
                    "source_count": len(evidence.sources),
                    "attempt_count": len(evidence.attempts),
                    "limitations": list(evidence.limitations),
                },
                started_at=started_at,
                completed_at=utc_now_iso(),
                error=None if status != "failure" else "the search returned no usable sources",
                artifacts={"retrieval_ms": evidence.retrieval_ms},
            )
        )

    @staticmethod
    def _check_search(context: TurnContext) -> None:
        if context.search_operation:
            context.search_operation.check()

    def _speak_or_degrade(
        self,
        context: TurnContext,
        *,
        transcript: str,
        response_text: str,
        final_prompt_text: str,
        voice_text: str | None = None,
        retrieved_memory_refs: list[str] | None = None,
        retrieved_memory_evidence: list[dict[str, object]] | None = None,
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
                retrieved_memory_evidence=retrieved_memory_evidence,
            )
            return result

        use_streaming = getattr(self.tts, "supports_streaming", False) and hasattr(self.playback_api, "IterablePlayer")
        if use_streaming:
            sample_rate = self.tts.sample_rate()
            return self._speak_streaming(
                context,
                text_to_synthesize=voice_text if voice_text is not None else response_text,
                sample_rate=sample_rate,
                transcript=transcript,
                response_text=response_text,
                final_prompt_text=final_prompt_text,
                retrieved_memory_refs=retrieved_memory_refs,
                retrieved_memory_evidence=retrieved_memory_evidence,
                raw_audio_path=raw_audio_path,
                phase_durations_ms=phase_durations_ms,
                voice_turn_started_at=voice_turn_started_at,
            )

        audio, sample_rate = self._synthesize_voice(
            stored_response=response_text,
            voice_text=voice_text,
            phase_durations_ms=phase_durations_ms,
            voice_turn_started_at=voice_turn_started_at,
        )

        return self._play_voice(
            context,
            audio=audio,
            sample_rate=sample_rate,
            transcript=transcript,
            response_text=response_text,
            final_prompt_text=final_prompt_text,
            retrieved_memory_refs=retrieved_memory_refs,
            retrieved_memory_evidence=retrieved_memory_evidence,
            raw_audio_path=raw_audio_path,
            phase_durations_ms=phase_durations_ms,
            voice_turn_started_at=voice_turn_started_at,
        )

    def _synthesize_voice(
        self,
        *,
        stored_response: str,
        voice_text: str | None = None,
        phase_durations_ms: dict[str, float] | None = None,
        voice_turn_started_at: float | None = None,
    ) -> tuple[np.ndarray, int]:
        tts_started_at = time.perf_counter()
        try:
            text_to_synthesize = voice_text if voice_text is not None else stored_response
            audio = self.tts.synthesize(text_to_synthesize)
            sample_rate = self.tts.sample_rate()
            return audio, sample_rate
        finally:
            if voice_turn_started_at is not None and phase_durations_ms is not None:
                phase_durations_ms["tts_synth_ms"] = _elapsed_ms(tts_started_at)

    def _play_voice(
        self,
        context: TurnContext,
        *,
        audio: np.ndarray,
        sample_rate: int,
        transcript: str,
        response_text: str,
        final_prompt_text: str,
        retrieved_memory_refs: list[str] | None = None,
        retrieved_memory_evidence: list[dict[str, object]] | None = None,
        raw_audio_path: str | None = None,
        phase_durations_ms: dict[str, float] | None = None,
        voice_turn_started_at: float | None = None,
    ) -> TurnResult:
        self._check_search(context)
        context.advance(ConversationState.SPEAKING)
        if self.barge_in_detector is not None and self.interruption_audio_chunks is not None:
            interruption_chunks = self._resolve_interruption_audio_chunks()
            if interruption_chunks is not None:
                try:
                    return self._play_with_interruption_monitor(
                        context,
                        transcript=transcript,
                        response_text=response_text,
                        final_prompt_text=final_prompt_text,
                        audio=audio,
                        sample_rate=sample_rate,
                        interruption_chunks=interruption_chunks,
                        retrieved_memory_refs=retrieved_memory_refs,
                        retrieved_memory_evidence=retrieved_memory_evidence,
                        raw_audio_path=raw_audio_path,
                        phase_durations_ms=phase_durations_ms,
                        voice_turn_started_at=voice_turn_started_at,
                    )
                finally:
                    self._close_interruption_audio_chunks(interruption_chunks)
        playback_started_at = time.perf_counter()
        try:
            self.playback_api.play(audio, sample_rate)
        finally:
            if voice_turn_started_at is not None and phase_durations_ms is not None:
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
            phase_durations_ms=_voice_phase_durations(phase_durations_ms or {}, voice_turn_started_at),
        )
        self._record_artifact(
            context,
            result,
            final_prompt_text=final_prompt_text,
            retrieved_memory_refs=retrieved_memory_refs,
            retrieved_memory_evidence=retrieved_memory_evidence,
        )
        return result

    def _speak_streaming(
        self,
        context: TurnContext,
        *,
        text_to_synthesize: str,
        sample_rate: int,
        transcript: str,
        response_text: str,
        final_prompt_text: str,
        retrieved_memory_refs: list[str] | None = None,
        retrieved_memory_evidence: list[dict[str, object]] | None = None,
        raw_audio_path: str | None = None,
        phase_durations_ms: dict[str, float] | None = None,
        voice_turn_started_at: float | None = None,
    ) -> TurnResult:
        phase_durations_ms = phase_durations_ms if phase_durations_ms is not None else {}
        tts_started_at = time.perf_counter()

        player = None
        thread = None
        stop_event = threading.Event()
        error_container: list[Exception] = []
        vad_iter: Iterator[np.ndarray] | None = None

        try:
            self._check_search(context)
            if self.barge_in_detector is not None and self.interruption_audio_chunks is not None:
                vad_iter = self._resolve_interruption_audio_chunks()
            player = self.playback_api.IterablePlayer(sample_rate)
            player.start()

            def synthesis_worker() -> None:
                try:
                    for chunk, _rate in self.tts.synthesize_stream(text_to_synthesize):
                        self._check_search(context)
                        if stop_event.is_set():
                            break
                        player.put(chunk)
                    player.put(None)
                except Exception as exc:
                    error_container.append(exc)
                    player.put(None)

            thread = threading.Thread(target=synthesis_worker, name="tts-synthesis-stream", daemon=True)
            thread.start()

            context.advance(ConversationState.SPEAKING)
            playback_started_at = time.perf_counter()

            interrupted = False
            interruption_events = []

            if self.barge_in_detector is not None and vad_iter is not None:
                self.barge_in_detector.reset()
                while player.is_playing() or thread.is_alive():
                    self._check_search(context)
                    try:
                        if error_container:
                            raise error_container[0]
                        chunk = next(vad_iter)
                    except StopIteration:
                        break
                    if self.barge_in_detector.detect(chunk):
                        stop_event.set()
                        player.stop()
                        interrupted = True
                        event: dict[str, object] = {
                            "type": "barge_in",
                            "timestamp": timestamp_now(),
                            "recovery_state": ConversationState.RECOVERING.value,
                        }
                        interruption_events.append(event)
                        context.advance(ConversationState.INTERRUPTED)
                        context.advance(ConversationState.RECOVERING)
                        break
            else:
                while player.is_playing() or thread.is_alive():
                    self._check_search(context)
                    if error_container:
                        raise error_container[0]
                    time.sleep(0.01)

            if not interrupted:
                player.wait()

            if error_container:
                raise error_container[0]

        except Exception as exc:
            stop_event.set()
            if thread is not None:
                thread.join(timeout=0.5)
            if player is not None:
                with suppress(Exception):
                    player.stop()
            if isinstance(exc, SearchCancelledError):
                raise
            f_phase = "playback"
            if error_container and exc is error_container[0]:
                f_phase = "tts"
            context.advance(ConversationState.IDLE)
            return self._fail(
                context,
                transcript=transcript,
                response_text=response_text,
                reason=str(exc),
                raw_audio_path=raw_audio_path,
                phase_durations_ms=_voice_phase_durations(phase_durations_ms, voice_turn_started_at),
                failure_phase=f_phase,
            )

        finally:
            stop_event.set()
            self._close_interruption_audio_chunks(vad_iter)
            if thread is not None:
                thread.join(timeout=0.5)

        if voice_turn_started_at is not None:
            phase_durations_ms["tts_synth_ms"] = _elapsed_ms(tts_started_at)
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
            interrupted=interrupted,
            interruption_events=interruption_events,
        )

        self._record_artifact(
            context,
            result,
            final_prompt_text=final_prompt_text,
            retrieved_memory_refs=retrieved_memory_refs,
            retrieved_memory_evidence=retrieved_memory_evidence,
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
        interruption_chunks: Iterator[np.ndarray],
        retrieved_memory_refs: list[str] | None = None,
        retrieved_memory_evidence: list[dict[str, object]] | None = None,
        raw_audio_path: str | None = None,
        phase_durations_ms: dict[str, float] | None = None,
        voice_turn_started_at: float | None = None,
    ) -> TurnResult:
        phase_durations_ms = phase_durations_ms if phase_durations_ms is not None else {}
        assert self.barge_in_detector is not None
        self.barge_in_detector.reset()
        playback_started_at = time.perf_counter()
        self.playback_api.start(audio, sample_rate)
        while self._playback_is_playing():
            try:
                chunk = next(interruption_chunks)
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
                    retrieved_memory_evidence=retrieved_memory_evidence,
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
            retrieved_memory_evidence=retrieved_memory_evidence,
        )
        return result

    def _resolve_interruption_audio_chunks(self) -> Iterator[np.ndarray] | None:
        source = self.interruption_audio_chunks
        if source is None:
            return None
        resolved = source() if callable(source) else source
        if resolved is None:
            return None
        return iter(resolved)

    @staticmethod
    def _close_interruption_audio_chunks(chunks: Iterator[np.ndarray] | None) -> None:
        close = getattr(chunks, "close", None)
        if callable(close):
            close()

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
        context = self._new_context(modality)
        self._active_context = context
        return context

    def _new_context(self, modality: str) -> TurnContext:
        if self.session_manager is not None:
            if modality not in {"voice", "text"}:
                raise ValueError("modality must be voice or text")
            context = self.session_manager.create_turn_context(modality, phase_observer=self.phase_observer)  # type: ignore[arg-type]
            self._emit_hook("turn_admitted", context)
            return context
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
        retrieved_memory_evidence: list[dict[str, object]] | None = None,
    ) -> None:
        operation = context.search_operation
        with operation.lock if operation else nullcontext():
            if operation and operation.evidence.outcome != "cancelled":
                operation.check()
                if result.failure_reason:
                    operation.evidence.outcome = "failed"
                operation.evidence.stage = "complete"
            self._persist_artifact(context, result, final_prompt_text=final_prompt_text,
                retrieved_memory_refs=retrieved_memory_refs, retrieved_memory_evidence=retrieved_memory_evidence)

    def _persist_artifact(
        self, context: TurnContext, result: TurnResult, *, final_prompt_text: str | None,
        retrieved_memory_refs: list[str] | None = None,
        retrieved_memory_evidence: list[dict[str, object]] | None = None,
    ) -> None:
        if self.session_manager is None:
            return
        search = context.search_operation.snapshot() if context.search_operation else None
        artifact = TurnArtifact(
            turn_id=result.turn_id,
            session_id=result.session_id,
            input_modality=context.modality,
            active_personality_profile_id=self.personality.profile_id,
            profile_epoch=self.session_manager.profile_epoch,
            transcript=result.transcript,
            final_prompt_text=final_prompt_text,
            retrieved_memory_refs=list(retrieved_memory_refs or []),
            retrieved_memory_evidence=[
                dict(record) for record in (retrieved_memory_evidence or [])
            ],
            raw_audio_path=result.raw_audio_path,
            response_text=result.response_text,
            final_state=result.final_state.value,
            failure_reason=result.failure_reason,
            tts_degraded=result.tts_degraded,
            tts_degraded_reason=result.tts_degraded_reason,
            tts_output_device=result.tts_output_device,
            runtime_context=self._runtime_context(context, result),
            interruption_events=result.interruption_events,
            phase_timestamps={state: timestamp.isoformat() for state, timestamp in context.phase_timestamps.items()},
            phase_durations_ms=dict(result.phase_durations_ms),
            failure_phase=result.failure_phase,
            search=search,
            tools_invoked=_turn_tools_invoked(context),
            action_proposals=list(context.action_evidence.proposals),
            authorization_decisions=list(context.action_evidence.authorization_decisions),
            approval_records=list(context.action_evidence.approvals),
            action_execution_results=list(context.action_evidence.executions),
            action_cancellations=list(context.action_evidence.cancellations),
            delegated_runs=list(context.action_evidence.delegated_runs),
        )
        self.session_manager.record_turn_artifact(artifact)
        self._emit_hook("turn_persisted", context)
        if self.episodic is not None:
            try:
                self.episodic.write_entry(artifact, self.write_policy)
            except Exception:
                logger.warning("episodic memory write failed; continuing without episodic storage")
        if result.failure_reason is None and not (search and search.get("outcome") == "cancelled"):
            self.session_manager.update_working_memory(result.response_text, self.write_policy)

    def _runtime_context(self, context: TurnContext, result: TurnResult) -> dict[str, object]:
        phases = set(context.phase_timestamps)
        runtime_context = dict(context.runtime_context)
        if context.modality == "voice" and "TRANSCRIBING" in phases:
            runtime_context["stt"] = _runtime_device_label(self.stt)
        if "REASONING" in phases:
            runtime_context["llm"] = self.llm.runtime_name()
            provider_evidence = getattr(self.llm, "evidence", None)
            if callable(provider_evidence):
                runtime_context["llm_provider"] = provider_evidence()
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
        samples = audio.reshape(-1)
        if samples.size == 0:
            return None
        session_dir = self.session_manager.turns_base_dir / context.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        audio_path = session_dir / f"{context.turn_id}.wav"
        pcm_source = np.empty_like(samples, dtype=np.float32)
        np.clip(samples, -1.0, 1.0, out=pcm_source)
        np.multiply(pcm_source, 32767.0, out=pcm_source)
        pcm16 = pcm_source.astype("<i2")
        with wave.open(str(audio_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(int(sample_rate))
            wav_file.writeframes(pcm16.tobytes())
        return str(audio_path)


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
