from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WritePolicy:
    write_to_working_memory: bool = True
    max_working_memory_entries: int = 10