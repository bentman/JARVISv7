from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal

TURN_ARTIFACT_FIELDS: tuple[str, ...] = (
    "turn_id", "session_id", "input_modality", "hardware_profile_id",
    "capability_flags_snapshot", "active_personality_profile_id", "raw_audio_path",
    "transcript", "final_prompt_text", "retrieved_memory_refs", "tools_invoked",
    "agent_trace", "reasoning_trace_metadata", "response_text", "audio_output_path",
    "interruption_events", "final_state", "failure_reason", "tts_degraded",
    "tts_degraded_reason", "phase_timestamps",
)


@dataclass(slots=True)
class TurnArtifact:
    turn_id: str
    session_id: str
    input_modality: Literal["voice", "text"]
    final_state: str
    hardware_profile_id: str = "unknown"
    capability_flags_snapshot: dict[str, Any] = field(default_factory=dict)
    active_personality_profile_id: str = "unknown"
    raw_audio_path: str | None = None
    transcript: str | None = None
    final_prompt_text: str | None = None
    retrieved_memory_refs: list[str] = field(default_factory=list)
    tools_invoked: list[str] = field(default_factory=list)
    agent_trace: dict[str, Any] | None = None
    reasoning_trace_metadata: dict[str, Any] | None = None
    response_text: str | None = None
    audio_output_path: str | None = None
    interruption_events: list[dict[str, Any]] = field(default_factory=list)
    failure_reason: str | None = None
    tts_degraded: bool = False
    tts_degraded_reason: str | None = None
    phase_timestamps: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {name: payload[name] for name in TURN_ARTIFACT_FIELDS}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TurnArtifact:
        field_names = {field_def.name for field_def in fields(cls)}
        return cls(**{name: payload[name] for name in field_names if name in payload})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> TurnArtifact:
        return cls.from_dict(json.loads(payload))