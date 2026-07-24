from __future__ import annotations

import threading
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator


class ShutdownDrainInProgress(RuntimeError):
    """Interactive work cannot be admitted after shutdown drain begins."""


@dataclass(slots=True)
class InteractiveTicket:
    _coordinator: "LLMExecutionCoordinator"
    sequence: int
    _released: bool = False
    _owned: bool = False

    @contextmanager
    def execution(self) -> Iterator[None]:
        self._coordinator._acquire_interactive(self)
        try:
            yield
        finally:
            self._coordinator._release_interactive_owner(self)

    def release(self) -> None:
        if self._released:
            return
        self._coordinator._release_ticket(self)
        self._released = True


class LLMExecutionCoordinator:
    """Serialize one LLM slot while giving registered interactive work admission priority."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._next_sequence = 0
        self._interactive_waiters: deque[int] = deque()
        self._interactive_active = False
        self._background_active = False
        self._shutdown_drain_active = False
        self._stopping = False

    def register_interactive(
        self,
        *,
        allow_during_drain: bool = False,
    ) -> InteractiveTicket:
        with self._condition:
            if self._stopping or (
                self._shutdown_drain_active and not allow_during_drain
            ):
                raise ShutdownDrainInProgress("shutdown drain is in progress")
            self._next_sequence += 1
            ticket = InteractiveTicket(self, self._next_sequence)
            self._interactive_waiters.append(ticket.sequence)
            self._condition.notify_all()
            return ticket

    def begin_shutdown_drain(self) -> None:
        with self._condition:
            self._shutdown_drain_active = True
            self._condition.notify_all()

    def mark_stopping(self) -> None:
        with self._condition:
            self._stopping = True
            self._condition.notify_all()

    @property
    def shutdown_drain_active(self) -> bool:
        with self._condition:
            return self._shutdown_drain_active

    @property
    def stopping(self) -> bool:
        with self._condition:
            return self._stopping

    def try_acquire_background(
        self,
        *,
        session_inactive: bool,
        policy_enabled: bool,
        llm_ready: bool,
    ) -> bool:
        with self._condition:
            if (
                not self._shutdown_drain_active
                or self._stopping
                or not session_inactive
                or not policy_enabled
                or not llm_ready
                or self._interactive_active
                or self._interactive_waiters
                or self._background_active
            ):
                return False
            self._background_active = True
            return True

    def release_background(self) -> None:
        with self._condition:
            if self._background_active:
                self._background_active = False
                self._condition.notify_all()

    def snapshot(self) -> dict[str, object]:
        with self._condition:
            return {
                "interactive_waiters": len(self._interactive_waiters),
                "interactive_active": self._interactive_active,
                "background_active": self._background_active,
                "shutdown_drain_active": self._shutdown_drain_active,
                "stopping": self._stopping,
            }

    def _acquire_interactive(self, ticket: InteractiveTicket) -> None:
        with self._condition:
            if ticket._released:
                raise RuntimeError("interactive ticket was already released")
            while True:
                is_head = bool(
                    self._interactive_waiters
                    and self._interactive_waiters[0] == ticket.sequence
                )
                if is_head and not self._interactive_active and not self._background_active:
                    self._interactive_waiters.popleft()
                    self._interactive_active = True
                    ticket._owned = True
                    return
                self._condition.wait()

    def _release_interactive_owner(self, ticket: InteractiveTicket) -> None:
        with self._condition:
            if ticket._owned:
                ticket._owned = False
                self._interactive_active = False
                self._condition.notify_all()

    def _release_ticket(self, ticket: InteractiveTicket) -> None:
        with self._condition:
            if ticket._owned:
                ticket._owned = False
                self._interactive_active = False
            try:
                self._interactive_waiters.remove(ticket.sequence)
            except ValueError:
                pass
            self._condition.notify_all()
