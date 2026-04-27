from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class WorkingMemory:
    max_entries: int = 10
    _entries: list[str] = field(default_factory=list)

    def add(self, text: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        self._entries.append(cleaned)
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries :]

    def as_list(self) -> list[str]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()