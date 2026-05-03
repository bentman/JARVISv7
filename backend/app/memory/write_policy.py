from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WritePolicy:
    write_to_working_memory: bool = True
    max_working_memory_entries: int = 10
    write_to_episodic_memory: bool = True
    episodic_min_response_length: int = 10
    episodic_skip_failed_turns: bool = True
    episodic_retention_sessions: int = 20