from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import uuid4

from backend.app.artifacts import storage
from backend.app.artifacts.session_artifact import SessionArtifact
from backend.app.artifacts.turn_artifact import TurnArtifact
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

    def create_turn_context(self, modality: Literal["voice", "text"]) -> TurnContext:
        return TurnContext(session_id=self.session_id, modality=modality)

    def get_working_context(self, policy: WritePolicy) -> list[str]:
        self._apply_policy_capacity(policy)
        if not policy.write_to_working_memory:
            return []
        return self.working_memory.as_list()

    def record_turn_artifact(self, artifact: TurnArtifact) -> Path:
        self.turn_artifacts.append(artifact)
        return storage.write_turn_artifact(artifact, self.turns_base_dir)

    def update_working_memory(self, response_text: str | None, policy: WritePolicy) -> None:
        self._apply_policy_capacity(policy)
        if policy.write_to_working_memory and response_text:
            self.working_memory.add(response_text)

    def close_session(self, final_state: ConversationState | str = ConversationState.IDLE) -> Path:
        final_state_value = final_state.value if isinstance(final_state, ConversationState) else final_state
        artifact = SessionArtifact(
            session_id=self.session_id,
            started_at=self.started_at,
            ended_at=_iso_now(),
            turn_ids=[turn.turn_id for turn in self.turn_artifacts],
            final_state=final_state_value,
        )
        return storage.write_session_artifact(artifact, self.sessions_base_dir)

    def _apply_policy_capacity(self, policy: WritePolicy) -> None:
        if self.working_memory.max_entries == policy.max_working_memory_entries:
            return
        self.working_memory.max_entries = policy.max_working_memory_entries
        if len(self.working_memory._entries) > self.working_memory.max_entries:
            self.working_memory._entries = self.working_memory._entries[-self.working_memory.max_entries :]