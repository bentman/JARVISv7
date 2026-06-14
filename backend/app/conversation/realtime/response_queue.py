from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass(slots=True)
class RealtimeResponseQueue:
    _items: deque[str] = field(default_factory=deque)

    def enqueue(self, response_text: str | None) -> None:
        if response_text:
            self._items.append(response_text)

    def dequeue(self) -> str | None:
        if not self._items:
            return None
        return self._items.popleft()

    def __len__(self) -> int:
        return len(self._items)
