from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from backend.app.artifacts import storage
from backend.app.artifacts.session_artifact import SessionArtifact
from backend.app.artifacts.session_timeline import SessionTimeline
from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.conversation.continuity import ContinuityPacket, ContinuityPacketBuilder
from backend.app.conversation.continuity_policy import ContinuityPolicyInput, decide_continuity
from backend.app.conversation.states import ConversationState
from backend.app.conversation.turn_manager import TurnContext, utc_now
from backend.app.core.paths import DATA_DIR
from backend.app.memory.working import WorkingMemory
from backend.app.memory.write_policy import WritePolicy


def _iso_now() -> str:
    return utc_now().isoformat()


@dataclass(slots=True)
class SessionManager:
    session_id: str = field(default_factory=lambda: uuid4().hex)
    turns_base_dir: Path = DATA_DIR / "turns"
    sessions_base_dir: Path = DATA_DIR / "sessions"
    started_at: str = field(default_factory=_iso_now)
    working_memory: WorkingMemory = field(default_factory=WorkingMemory)
    turn_artifacts: list[TurnArtifact] = field(default_factory=list)
    timeline: SessionTimeline | None = None
    clock: Callable[[], datetime] = utc_now

    def __post_init__(self) -> None:
        if self.timeline is None:
            self.timeline = SessionTimeline(session_id=self.session_id)
            self.timeline.append("session_started", timestamp=self.started_at, state=ConversationState.IDLE.value)

    def create_turn_context(self, modality: Literal["voice", "text"]) -> TurnContext:
        return TurnContext(session_id=self.session_id, modality=modality)

    def get_working_context(self, policy: WritePolicy) -> list[str]:
        self._apply_policy_capacity(policy)
        if not policy.write_to_working_memory:
            return []
        return self.working_memory.as_list()

    def record_turn_artifact(self, artifact: TurnArtifact) -> Path:
        self.turn_artifacts.append(artifact)
        self.record_timeline_event(
            "user_turn_committed",
            turn_id=artifact.turn_id,
            state=artifact.final_state,
            metadata={"input_modality": artifact.input_modality},
        )
        if artifact.response_text:
            self.record_timeline_event(
                "assistant_response_started",
                turn_id=artifact.turn_id,
                state=ConversationState.RESPONDING.value,
            )
        if artifact.response_text and not artifact.tts_degraded and artifact.input_modality == "voice":
            self.record_timeline_event(
                "assistant_speech_started",
                turn_id=artifact.turn_id,
                state=ConversationState.SPEAKING.value,
            )
        for event in artifact.interruption_events:
            self.record_timeline_event(
                "interruption_detected",
                turn_id=artifact.turn_id,
                state=ConversationState.INTERRUPTED.value,
                metadata=event,
            )
            self.record_timeline_event(
                "recovery",
                turn_id=artifact.turn_id,
                state=ConversationState.RECOVERING.value,
                metadata=event,
            )
        if artifact.failure_reason:
            self.record_timeline_event(
                "failure",
                turn_id=artifact.turn_id,
                state=ConversationState.FAILED.value,
                metadata={"reason": artifact.failure_reason},
            )
        self.record_timeline_event("idle", turn_id=artifact.turn_id, state=ConversationState.IDLE.value)
        return storage.write_turn_artifact(artifact, self.turns_base_dir)

    def update_working_memory(self, response_text: str | None, policy: WritePolicy) -> None:
        self._apply_policy_capacity(policy)
        if policy.write_to_working_memory and response_text:
            self.working_memory.add(response_text)

    def close_session(self, final_state: ConversationState | str = ConversationState.IDLE) -> Path:
        final_state_value = final_state.value if isinstance(final_state, ConversationState) else final_state
        self.record_timeline_event("session_closed", state=final_state_value)
        timeline_path = storage.write_session_timeline(self.timeline, self.sessions_base_dir)
        continuity_summary = self.build_continuity_packet().summary()
        artifact = SessionArtifact(
            session_id=self.session_id,
            started_at=self.started_at,
            ended_at=_iso_now(),
            turn_ids=[turn.turn_id for turn in self.turn_artifacts],
            final_state=final_state_value,
            timeline_path=str(timeline_path),
            continuity_summary=continuity_summary,
            memory_curation_candidate=bool(self.turn_artifacts),
        )
        return storage.write_session_artifact(artifact, self.sessions_base_dir)

    def record_timeline_event(
        self,
        event_type: str,
        *,
        turn_id: str | None = None,
        source: str | None = None,
        state: str | ConversationState | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        state_value = state.value if isinstance(state, ConversationState) else state
        assert self.timeline is not None
        self.timeline.append(
            event_type,
            timestamp=_iso_now(),
            turn_id=turn_id,
            source=source,
            state=state_value,
            metadata=metadata,
        )

    def build_continuity_packet(
        self,
        *,
        latest_text: str | None = None,
        include_current_session: bool = True,
    ) -> ContinuityPacket:
        last_turn = self.turn_artifacts[-1] if self.turn_artifacts else None
        policy_result = decide_continuity(
            ContinuityPolicyInput(
                active_session=True,
                same_session=include_current_session,
                latest_text=latest_text,
                last_turn_at=self._latest_turn_timestamp(last_turn),
                now=self.clock(),
                last_final_state=last_turn.final_state if last_turn else None,
                failure_reason=last_turn.failure_reason if last_turn else None,
                prior_interrupted=bool(last_turn and last_turn.interruption_events),
            )
        )
        return ContinuityPacketBuilder().build(
            session_id=self.session_id,
            policy_result=policy_result,
            turn_artifacts=self.turn_artifacts,
            working_memory=self.working_memory.as_list(),
        )

    def _latest_turn_timestamp(self, last_turn: TurnArtifact | None) -> datetime | None:
        if last_turn is not None:
            for timestamp in reversed(list(last_turn.phase_timestamps.values())):
                parsed = _parse_iso_datetime(timestamp)
                if parsed is not None:
                    return parsed
        assert self.timeline is not None
        for event in reversed(self.timeline.events):
            if last_turn is not None and event.turn_id != last_turn.turn_id:
                continue
            parsed = _parse_iso_datetime(event.timestamp)
            if parsed is not None:
                return parsed
        return None

    def _apply_policy_capacity(self, policy: WritePolicy) -> None:
        if self.working_memory.max_entries == policy.max_working_memory_entries:
            return
        self.working_memory.max_entries = policy.max_working_memory_entries
        if len(self.working_memory._entries) > self.working_memory.max_entries:
            self.working_memory._entries = self.working_memory._entries[-self.working_memory.max_entries :]


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
