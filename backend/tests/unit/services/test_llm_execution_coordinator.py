from __future__ import annotations

import threading
import time

import pytest

from backend.app.services.llm_execution_coordinator import (
    LLMExecutionCoordinator,
    ShutdownDrainInProgress,
)


def test_interactive_waiter_prevents_background_admission() -> None:
    coordinator = LLMExecutionCoordinator()
    ticket = coordinator.register_interactive()
    coordinator.begin_shutdown_drain()

    assert not coordinator.try_acquire_background(
        session_inactive=True,
        policy_enabled=True,
        llm_ready=True,
    )
    ticket.release()


def test_background_is_non_preemptible_and_interactive_runs_after_release() -> None:
    coordinator = LLMExecutionCoordinator()
    coordinator.begin_shutdown_drain()
    assert coordinator.try_acquire_background(
        session_inactive=True,
        policy_enabled=True,
        llm_ready=True,
    )
    # Internal already-admitted work remains serialized but cannot preempt background.
    ticket = coordinator.register_interactive(allow_during_drain=True)
    events: list[str] = []

    thread = threading.Thread(
        target=lambda: _run_ticket(ticket, events),
        daemon=True,
    )
    thread.start()
    time.sleep(0.02)
    assert events == []

    events.append("background-finish")
    coordinator.release_background()
    thread.join(1)

    assert events == ["background-finish", "interactive-start", "interactive-finish"]


def test_interactive_tickets_are_fifo() -> None:
    coordinator = LLMExecutionCoordinator()
    first = coordinator.register_interactive()
    second = coordinator.register_interactive()
    events: list[int] = []
    first_thread = threading.Thread(
        target=lambda: _run_numbered_ticket(first, 1, events),
        daemon=True,
    )
    second_thread = threading.Thread(
        target=lambda: _run_numbered_ticket(second, 2, events),
        daemon=True,
    )
    second_thread.start()
    first_thread.start()
    first_thread.join(1)
    second_thread.join(1)

    assert events == [1, 2]


def test_shutdown_drain_rejects_new_interactive_registration() -> None:
    coordinator = LLMExecutionCoordinator()
    coordinator.begin_shutdown_drain()

    with pytest.raises(ShutdownDrainInProgress):
        coordinator.register_interactive()


def _run_ticket(ticket, events: list[str]) -> None:
    try:
        with ticket.execution():
            events.append("interactive-start")
        events.append("interactive-finish")
    finally:
        ticket.release()


def _run_numbered_ticket(ticket, number: int, events: list[int]) -> None:
    try:
        with ticket.execution():
            events.append(number)
    finally:
        ticket.release()
