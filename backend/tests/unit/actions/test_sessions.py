from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest
from backend.app.actions.sessions import (
    SessionCallOutcomeUnknown,
    SessionHandlers,
    SessionManager,
    SessionResourceDied,
)


class _FakeResource:
    def __init__(self, resource_id: int) -> None:
        self.resource_id = resource_id
        self.closed = False
        self.terminated = False


def _handlers(opened: list[_FakeResource], terminated: list[_FakeResource], *, close_delay: float = 0.0) -> SessionHandlers[_FakeResource]:
    counter = {"n": 0}

    async def open_() -> _FakeResource:
        counter["n"] += 1
        resource = _FakeResource(counter["n"])
        opened.append(resource)
        return resource

    async def close_(resource: _FakeResource) -> None:
        if close_delay:
            await asyncio.sleep(close_delay)
        resource.closed = True

    async def terminate_(resource: _FakeResource) -> None:
        resource.terminated = True
        terminated.append(resource)

    return SessionHandlers(open=open_, close=close_, terminate=terminate_)


def test_a_second_call_reuses_the_open_resource_instead_of_reopening() -> None:
    manager = SessionManager()
    opened: list[_FakeResource] = []
    handlers = _handlers(opened, [])

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    first = manager.call("conn", handlers, work)
    second = manager.call("conn", handlers, work)

    assert first == second == 1, "the second call must reuse the same resource, not open a new one"
    assert len(opened) == 1, "only one resource should ever have been opened"
    manager.close("conn")


def test_calls_against_one_connection_are_serialized_not_interleaved() -> None:
    manager = SessionManager()
    opened: list[_FakeResource] = []
    handlers = _handlers(opened, [])
    order: list[str] = []

    async def slow_work(resource: _FakeResource) -> None:
        order.append("start")
        await asyncio.sleep(0.1)
        order.append("end")

    def run() -> None:
        manager.call("conn", handlers, slow_work)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert order == ["start", "end", "start", "end"], "a second call must wait for the first to finish, not interleave with it"
    manager.close("conn")


def test_close_ends_the_resource_and_a_later_call_opens_a_fresh_one() -> None:
    manager = SessionManager()
    opened: list[_FakeResource] = []
    terminated: list[_FakeResource] = []
    handlers = _handlers(opened, terminated)

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    manager.call("conn", handlers, work)
    assert manager.is_open("conn") is True

    manager.close("conn")
    assert manager.is_open("conn") is False
    assert opened[0].closed is True, "close must end the resource gracefully"

    second = manager.call("conn", handlers, work)
    assert second == 2, "a call after close must open a genuinely fresh resource"
    assert len(opened) == 2
    manager.close("conn")


def test_close_against_a_hung_call_drains_then_terminates_within_the_bound() -> None:
    drain_seconds = 0.2
    manager = SessionManager(drain_seconds=drain_seconds)
    opened: list[_FakeResource] = []
    terminated: list[_FakeResource] = []
    handlers = _handlers(opened, terminated)
    call_started = threading.Event()

    async def hung_work(resource: _FakeResource) -> None:
        call_started.set()
        await asyncio.sleep(10)  # never finishes within any reasonable test bound

    def run_hung_call() -> None:
        # close()'s drain-then-cancel is expected to end this call with outcome-unknown;
        # this thread only exists to make the call actually in-flight when close() runs.
        with pytest.raises(SessionCallOutcomeUnknown):
            manager.call("conn", handlers, hung_work, timeout_s=30)

    call_thread = threading.Thread(target=run_hung_call, daemon=True)
    call_thread.start()
    assert call_started.wait(timeout=2), "the hung call must actually start before we try to close it"

    started = time.monotonic()
    manager.close("conn")
    elapsed = time.monotonic() - started

    assert elapsed < drain_seconds + 1.0, (
        f"close must return within the bounded drain window, not wait on the hung call "
        f"indefinitely; took {elapsed:.2f}s"
    )
    assert terminated and terminated[0] is opened[0], "a call that does not finish draining must be terminated, not gracefully closed"
    assert opened[0].closed is False, "a terminated resource was not also gracefully closed"


def test_close_racing_an_in_flight_open_cancels_it_instead_of_leaking_the_resource() -> None:
    # A close (definition edit/delete, backend shutdown) can land while the very first
    # call for a connection is still inside handlers.open() - e.g. a slow subprocess
    # spawn. close() must not read connection.resource, find it still None, and conclude
    # there is nothing to close while that open keeps running unobserved in the
    # background: it must cancel the open and wait for it to actually stop.
    drain_seconds = 0.2
    manager = SessionManager(drain_seconds=drain_seconds)
    opened: list[_FakeResource] = []
    terminated: list[_FakeResource] = []
    open_started = threading.Event()

    async def slow_open() -> _FakeResource:
        open_started.set()
        await asyncio.sleep(10)  # never finishes within any reasonable test bound
        resource = _FakeResource(1)
        opened.append(resource)
        return resource

    async def close_(resource: _FakeResource) -> None:
        resource.closed = True

    async def terminate_(resource: _FakeResource) -> None:
        resource.terminated = True
        terminated.append(resource)

    handlers: SessionHandlers[_FakeResource] = SessionHandlers(
        open=slow_open, close=close_, terminate=terminate_,
    )

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    outcome: dict[str, Any] = {}

    def run_call() -> None:
        try:
            manager.call("conn", handlers, work, timeout_s=30)
        except SessionCallOutcomeUnknown as exc:
            outcome["error"] = exc

    call_thread = threading.Thread(target=run_call, daemon=True)
    call_thread.start()
    assert open_started.wait(timeout=2), "the open must actually start before we try to close it"

    started = time.monotonic()
    manager.close("conn")
    elapsed = time.monotonic() - started

    assert elapsed < drain_seconds + 1.0, (
        f"close must return within the bounded window, not wait on the stuck open "
        f"indefinitely; took {elapsed:.2f}s"
    )
    call_thread.join(timeout=2)
    assert isinstance(outcome.get("error"), SessionCallOutcomeUnknown), (
        "the caller waiting on the cancelled open must see outcome-unknown, not hang or see a raw CancelledError"
    )
    assert manager.is_open("conn") is False
    assert opened == [], "the open must never have finished and assigned a resource nothing then tracks"
    assert terminated == [], "an open that never produced a resource has nothing for terminate to act on"


def test_close_waits_for_a_call_that_finished_opening_and_is_now_running_work() -> None:
    # close() dispatched while open() is still running captures the open task as the
    # thing to drain. If open() then finishes during that drain, run() proceeds straight
    # into work() while still holding the connection's lock. close() must keep waiting
    # for that too - checking only whether the captured open task is done cannot tell
    # "the connection is now idle" from "a call finished opening and immediately started
    # using the resource" - so a close that only tracks task identity/completion can
    # race a queued call's work phase instead of waiting for it.
    drain_seconds = 1.0
    manager = SessionManager(drain_seconds=drain_seconds)
    opened: list[_FakeResource] = []
    terminated: list[_FakeResource] = []
    violations: list[str] = []
    open_started = threading.Event()

    async def quick_open() -> _FakeResource:
        open_started.set()
        await asyncio.sleep(0.05)
        resource = _FakeResource(1)
        opened.append(resource)
        return resource

    async def slow_work(resource: _FakeResource) -> int:
        # Checked repeatedly across the whole work window, not just once, so the
        # detection does not depend on exactly when close()'s continuation happens to be
        # scheduled relative to work()'s - only on whether close/terminate ever ran
        # during any part of work's use of the resource.
        for _ in range(15):
            await asyncio.sleep(0.02)
            if resource.closed or resource.terminated:
                violations.append("resource was closed/terminated while work was still using it")
                break
        return resource.resource_id

    async def close_(resource: _FakeResource) -> None:
        resource.closed = True

    async def terminate_(resource: _FakeResource) -> None:
        resource.terminated = True
        terminated.append(resource)

    handlers: SessionHandlers[_FakeResource] = SessionHandlers(
        open=quick_open, close=close_, terminate=terminate_,
    )
    result: dict[str, Any] = {}

    def run_call() -> None:
        result["value"] = manager.call("conn", handlers, slow_work, timeout_s=5)

    thread = threading.Thread(target=run_call)
    thread.start()
    assert open_started.wait(timeout=2), "open must actually start before we try to close it"
    manager.close("conn")  # dispatched while open() is still in its 0.05s sleep
    thread.join(timeout=5)

    assert violations == [], violations
    assert result.get("value") == 1, "the in-flight call should still complete normally since it finished within the drain window"


def test_close_terminates_within_the_bound_even_when_the_call_resists_cancellation() -> None:
    # A task can catch its own CancelledError and keep running instead of stopping.
    # close() must still reach terminate() within a bound in that case - waiting for the
    # task's actual cooperation would make the bound meaningless.
    drain_seconds = 0.2
    manager = SessionManager(drain_seconds=drain_seconds)
    opened: list[_FakeResource] = []
    terminated: list[_FakeResource] = []
    handlers = _handlers(opened, terminated)
    call_started = threading.Event()

    async def stubborn_work(resource: _FakeResource) -> None:
        call_started.set()
        for _ in range(1000):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                continue  # swallow and keep going - resists cancellation

    # stubborn_work never actually finishes even once cancelled, so run()'s own await
    # of it never resolves either; timeout_s here only bounds how long this thread waits
    # for manager.call() to give up on its own, not anything this test is verifying.
    outcome: dict[str, Any] = {}

    def run_call() -> None:
        try:
            manager.call("conn", handlers, stubborn_work, timeout_s=2)
        except SessionCallOutcomeUnknown as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=run_call, daemon=True)
    thread.start()
    assert call_started.wait(timeout=2)

    started = time.monotonic()
    manager.close("conn")
    elapsed = time.monotonic() - started

    assert elapsed < drain_seconds * 4, (
        f"close must reach terminate within a bound regardless of the task's own "
        f"cooperation with cancellation; took {elapsed:.2f}s"
    )
    assert terminated and terminated[0] is opened[0]

    thread.join(timeout=3)
    assert not thread.is_alive()
    assert isinstance(outcome.get("error"), SessionCallOutcomeUnknown)


def test_close_awaits_terminate_to_completion_instead_of_firing_and_forgetting() -> None:
    # terminate() is async precisely so a family whose real kill needs to await
    # something (MCP's SDK-driven stdio shutdown in particular, which is a genuine
    # SIGTERM-then-SIGKILL escalation, not a instant call) has that await actually
    # honored by close() - not scheduled and left to keep running after close() has
    # already returned, which is what a fire-and-forget `asyncio.ensure_future(...)`
    # without awaiting it would do instead.
    drain_seconds = 0.1
    manager = SessionManager(drain_seconds=drain_seconds)
    opened: list[_FakeResource] = []
    terminated: list[_FakeResource] = []
    call_started = threading.Event()
    terminate_finished = threading.Event()

    async def open_() -> _FakeResource:
        resource = _FakeResource(1)
        opened.append(resource)
        return resource

    async def stubborn_work(resource: _FakeResource) -> None:
        call_started.set()
        for _ in range(1000):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                continue  # resists cancellation, forcing _force_close's terminate path

    async def close_(resource: _FakeResource) -> None:
        resource.closed = True

    async def slow_terminate(resource: _FakeResource) -> None:
        await asyncio.sleep(0.3)  # meaningfully slower than drain_seconds
        resource.terminated = True
        terminated.append(resource)
        terminate_finished.set()

    handlers: SessionHandlers[_FakeResource] = SessionHandlers(
        open=open_, close=close_, terminate=slow_terminate,
    )

    def run_call() -> None:
        with pytest.raises(SessionCallOutcomeUnknown):
            manager.call("conn", handlers, stubborn_work, timeout_s=5)

    thread = threading.Thread(target=run_call, daemon=True)
    thread.start()
    assert call_started.wait(timeout=2)

    manager.close("conn")

    assert terminate_finished.is_set(), (
        "close() must not return until terminate() has actually completed, not merely been scheduled"
    )
    assert terminated and terminated[0] is opened[0]


def test_close_terminates_within_the_bound_even_when_graceful_close_resists_cancellation() -> None:
    # The same cancellation-resistance risk applies to the graceful close() handler
    # itself, not only to a stuck work()/open() call - a handlers.close() that catches
    # and swallows CancelledError must not be able to block close() from ever reaching
    # terminate() as its fallback.
    drain_seconds = 0.2
    manager = SessionManager(drain_seconds=drain_seconds)
    opened: list[_FakeResource] = []
    terminated: list[_FakeResource] = []
    close_started = threading.Event()

    async def open_() -> _FakeResource:
        resource = _FakeResource(1)
        opened.append(resource)
        return resource

    async def stubborn_close(resource: _FakeResource) -> None:
        close_started.set()
        for _ in range(1000):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                continue  # swallow and keep going - resists cancellation

    async def terminate_(resource: _FakeResource) -> None:
        resource.terminated = True
        terminated.append(resource)

    handlers: SessionHandlers[_FakeResource] = SessionHandlers(
        open=open_, close=stubborn_close, terminate=terminate_,
    )

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    manager.call("conn", handlers, work)

    started = time.monotonic()
    manager.close("conn")
    elapsed = time.monotonic() - started

    assert elapsed < drain_seconds * 4, (
        f"close must reach terminate within a bound even when handlers.close() itself "
        f"resists cancellation; took {elapsed:.2f}s"
    )
    assert terminated and terminated[0] is opened[0]


def test_close_waits_the_full_no_separate_terminate_bound_when_close_and_terminate_are_the_same_function() -> None:
    # When a family declares no independently-more-forceful terminate
    # (handlers.close is handlers.terminate - true for MCP, whose own close() already is
    # the SDK's full graceful-then-kill escalation with nothing lower-level beneath it
    # this mechanism can reach), calling the same operation a second time cannot help:
    # it is either a no-op (the resource's own state was already consumed) or, if made
    # joinable, corrupts anyio's task-bound cancel-scope bookkeeping (confirmed by direct
    # reproduction against a real MCP connection, not assumed). The fix is to wait longer
    # for the single attempt - up to a fixed ceiling well past drain_seconds, not scaled
    # by it - rather than declaring it timed out and racing a second, identical attempt
    # against it.
    from backend.app.actions import sessions as sessions_module

    drain_seconds = 0.1
    manager = SessionManager(drain_seconds=drain_seconds)
    opened: list[_FakeResource] = []
    call_count = {"n": 0}

    async def open_() -> _FakeResource:
        resource = _FakeResource(1)
        opened.append(resource)
        return resource

    async def close_and_terminate(resource: _FakeResource) -> None:
        call_count["n"] += 1
        # Longer than drain_seconds but comfortably within _NO_SEPARATE_TERMINATE_SECONDS -
        # proves close() actually waits past drain_seconds for this single attempt
        # rather than abandoning it and calling the same function again.
        await asyncio.sleep(drain_seconds * 3)
        resource.closed = True
        resource.terminated = True

    handlers: SessionHandlers[_FakeResource] = SessionHandlers(
        open=open_, close=close_and_terminate, terminate=close_and_terminate,
    )

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    manager.call("conn", handlers, work)

    started = time.monotonic()
    manager.close("conn")
    elapsed = time.monotonic() - started

    assert elapsed >= drain_seconds * 3 * 0.9, (
        f"close() must actually wait for the single close/terminate attempt to finish, "
        f"not give up at drain_seconds and move on; took only {elapsed:.2f}s"
    )
    assert elapsed < sessions_module._NO_SEPARATE_TERMINATE_SECONDS, (
        f"close() must not wait past the fixed ceiling either; took {elapsed:.2f}s"
    )
    assert call_count["n"] == 1, (
        f"the same close/terminate function must be called exactly once, not called a "
        f"second time while the first attempt was still genuinely in progress; called {call_count['n']} times"
    )
    assert opened[0].closed is True and opened[0].terminated is True


def test_close_cancels_a_graceful_close_that_times_out_instead_of_abandoning_it() -> None:
    # A graceful close() that does not finish within the drain window must actually be
    # cancelled, not just outrun and left running unreferenced while close() moves on to
    # terminate() - an abandoned pending task is a real leak (and, at interpreter/loop
    # shutdown, surfaces as asyncio's own "Task was destroyed but it is pending" warning)
    # distinct from whether terminate() itself is reached in time.
    drain_seconds = 0.1
    manager = SessionManager(drain_seconds=drain_seconds)
    opened: list[_FakeResource] = []
    terminated: list[_FakeResource] = []
    close_cancelled = threading.Event()

    async def open_() -> _FakeResource:
        resource = _FakeResource(1)
        opened.append(resource)
        return resource

    async def slow_but_cooperative_close(resource: _FakeResource) -> None:
        # Slow enough to miss the first settle's bound, but - unlike the "resists
        # cancellation" tests above - actually stops once cancelled instead of
        # swallowing it, so a real cancel()+settle should catch its completion.
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            close_cancelled.set()
            raise

    async def terminate_(resource: _FakeResource) -> None:
        resource.terminated = True
        terminated.append(resource)

    handlers: SessionHandlers[_FakeResource] = SessionHandlers(
        open=open_, close=slow_but_cooperative_close, terminate=terminate_,
    )

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    manager.call("conn", handlers, work)
    manager.close("conn")

    assert close_cancelled.is_set(), (
        "the timed-out graceful close must actually be cancelled, not left dangling and unreferenced"
    )
    assert terminated and terminated[0] is opened[0]


def test_a_call_queued_behind_close_fails_instead_of_reusing_the_closed_connection() -> None:
    # A call that already holds a reference to the connection object (fetched before
    # close() popped it from the registry) and is waiting on its lock when close() runs
    # must not, once it finally gets the lock, silently reuse or reopen under that now-
    # closed connection - it must see that the connection was closed and fail clearly, so
    # the next independent call is the one that gets a genuinely fresh connection.
    #
    # The first call here never finishes on its own, so close()'s drain window elapses
    # and it is force-cancelled - that is expected, correct behavior for a call still
    # running past the drain bound, not what this test is checking. What this test
    # checks is the *second*, queued call: once the first call's cancellation lets it
    # through to the lock, it must see the connection is closed, not reuse it.
    manager = SessionManager(drain_seconds=0.1)
    opened: list[_FakeResource] = []
    terminated: list[_FakeResource] = []
    handlers = _handlers(opened, terminated)
    first_call_started = threading.Event()

    async def blocking_first_call(resource: _FakeResource) -> None:
        first_call_started.set()
        await asyncio.sleep(10)  # outlives close()'s drain window; gets force-cancelled

    async def quick_second_call(resource: _FakeResource) -> int:
        return resource.resource_id

    first_outcome: dict[str, Any] = {}

    def run_first() -> None:
        try:
            manager.call("conn", handlers, blocking_first_call, timeout_s=5)
        except SessionCallOutcomeUnknown as exc:
            first_outcome["error"] = exc

    first_thread = threading.Thread(target=run_first)
    first_thread.start()
    assert first_call_started.wait(timeout=2)

    # Queue a second call against the same connection while the first still holds the
    # lock, so it is waiting for that same lock when close() marks the connection closed.
    second_outcome: dict[str, Any] = {}

    def run_second() -> None:
        try:
            second_outcome["value"] = manager.call("conn", handlers, quick_second_call, timeout_s=5)
        except SessionResourceDied as exc:
            second_outcome["error"] = exc

    second_thread = threading.Thread(target=run_second)
    second_thread.start()
    time.sleep(0.02)  # let the second call actually queue on the lock before closing
    manager.close("conn")

    first_thread.join(timeout=3)
    second_thread.join(timeout=3)

    assert isinstance(first_outcome.get("error"), SessionCallOutcomeUnknown), (
        "the first call outlives the drain window and must be force-cancelled, not silently succeed"
    )
    assert isinstance(second_outcome.get("error"), SessionResourceDied), (
        "the queued second call must see the connection was closed once it gets the lock, "
        "not silently reuse or reopen under the now-evicted connection"
    )


def test_shutdown_joins_the_background_thread() -> None:
    manager = SessionManager(drain_seconds=0.1)
    opened: list[_FakeResource] = []
    handlers = _handlers(opened, [])

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    manager.call("conn", handlers, work)
    thread = manager._thread
    assert thread is not None and thread.is_alive()

    manager.shutdown(timeout=3)

    assert not thread.is_alive(), "shutdown must actually join the background thread, not just ask it to stop"
    assert manager.is_open("conn") is False


def test_a_resource_reported_dead_is_evicted_and_recreated_on_the_next_call() -> None:
    manager = SessionManager()
    opened: list[_FakeResource] = []
    terminated: list[_FakeResource] = []
    handlers = _handlers(opened, terminated)

    async def dying_work(resource: _FakeResource) -> None:
        raise SessionResourceDied("the server exited unexpectedly")

    with pytest.raises(SessionResourceDied):
        manager.call("conn", handlers, dying_work)
    assert manager.is_open("conn") is False, "a resource reported dead must be evicted"
    assert terminated == [opened[0]], (
        "the dying resource's own terminate() must still run - dropping the reference "
        "without it leaves whatever internal bookkeeping the resource holds (a task "
        "group, open file descriptors) to be torn down later from an arbitrary context"
    )

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    second = manager.call("conn", handlers, work)
    assert second == 2, "the next call must open a fresh resource under the same connection id"
    manager.close("conn")


def test_a_call_that_times_out_reports_outcome_unknown_not_a_generic_failure() -> None:
    manager = SessionManager()
    opened: list[_FakeResource] = []
    handlers = _handlers(opened, [])

    async def slow_work(resource: _FakeResource) -> None:
        await asyncio.sleep(5)

    with pytest.raises(SessionCallOutcomeUnknown):
        manager.call("conn", handlers, slow_work, timeout_s=0.05)
    manager.close("conn")


def test_cancel_call_stops_the_call_without_closing_the_connection() -> None:
    manager = SessionManager()
    opened: list[_FakeResource] = []
    handlers = _handlers(opened, [])
    call_started = threading.Event()
    result: dict[str, Any] = {}

    async def slow_work(resource: _FakeResource) -> str:
        call_started.set()
        await asyncio.sleep(5)
        return "finished"

    def run() -> None:
        try:
            manager.call("conn", handlers, slow_work, timeout_s=10)
        except SessionCallOutcomeUnknown as exc:
            result["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    assert call_started.wait(timeout=2)

    cancelled = manager.cancel_call("conn")
    thread.join(timeout=2)

    assert cancelled is True
    assert isinstance(result.get("error"), SessionCallOutcomeUnknown), "a cancelled call must report outcome-unknown"
    assert manager.is_open("conn") is True, "cancelling one call must not close the connection"
    assert len(opened) == 1, "the resource opened for the cancelled call must still be the one reused next"

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    reused = manager.call("conn", handlers, work)
    assert reused == 1, "a call after cancelling the previous one must reuse the same resource"
    manager.close("conn")


def test_close_all_ends_every_open_connection() -> None:
    manager = SessionManager()
    opened: list[_FakeResource] = []
    handlers = _handlers(opened, [])

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    manager.call("conn-a", handlers, work)
    manager.call("conn-b", handlers, work)
    assert manager.is_open("conn-a") and manager.is_open("conn-b")

    manager.close_all()

    assert manager.is_open("conn-a") is False
    assert manager.is_open("conn-b") is False
    assert all(resource.closed for resource in opened), "every connection's resource must be closed"


def test_close_prefix_ends_only_matching_connections() -> None:
    # A family whose connection id is namespaced by more than a definition's own
    # identity (ACP: agent + host conversation) needs a definition edit/delete to close
    # every connection under that definition, not just one exact id it would otherwise
    # have to guess - and it must not touch a differently-prefixed connection.
    manager = SessionManager()
    opened: list[_FakeResource] = []
    handlers = _handlers(opened, [])

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    manager.call("acp:agent-a:conv-1", handlers, work)
    manager.call("acp:agent-a:conv-2", handlers, work)
    manager.call("acp:agent-b:conv-1", handlers, work)

    manager.close_prefix("acp:agent-a:")

    assert manager.is_open("acp:agent-a:conv-1") is False
    assert manager.is_open("acp:agent-a:conv-2") is False
    assert manager.is_open("acp:agent-b:conv-1") is True, "a differently-prefixed connection must be untouched"
    manager.close_all()


def test_close_reports_confirmed_on_an_ordinary_graceful_close() -> None:
    manager = SessionManager()
    opened: list[_FakeResource] = []
    handlers = _handlers(opened, [])

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    manager.call("conn", handlers, work)

    assert manager.close("conn") is True


def test_close_reports_unconfirmed_when_a_close_is_terminate_family_never_settles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # close()/close_prefix() used to return None unconditionally - every caller
    # upstream (Disconnect, Disable) treated that as success even when the underlying
    # resource never actually finished tearing down. A `close is terminate` family
    # (MCP) that exceeds even the generous _NO_SEPARATE_TERMINATE_SECONDS ceiling must
    # report that teardown could not be confirmed, not silently succeed.
    from backend.app.actions import sessions as sessions_module

    monkeypatch.setattr(sessions_module, "_NO_SEPARATE_TERMINATE_SECONDS", 0.2)
    manager = SessionManager(drain_seconds=0.05)

    async def open_() -> _FakeResource:
        return _FakeResource(1)

    async def hang(_resource: _FakeResource) -> None:
        await asyncio.sleep(10)

    handlers: SessionHandlers[_FakeResource] = SessionHandlers(open=open_, close=hang, terminate=hang)

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    manager.call("conn", handlers, work)

    assert manager.close("conn") is False
    manager.shutdown()


def test_close_reports_unconfirmed_when_a_close_is_terminate_family_raises_an_unrecognized_error() -> None:
    # Only anyio's own specific, confirmed-benign cancel-scope RuntimeError is treated
    # as "the resource died anyway" for a `close is terminate` family - a probe (an
    # unrelated NameError from a test's own missing import) reproduced this branch
    # treating *any* exception the same way, silently reporting success for a failure
    # that had nothing to do with the one case actually confirmed safe.
    manager = SessionManager(drain_seconds=0.05)

    async def open_() -> _FakeResource:
        return _FakeResource(1)

    async def broken(_resource: _FakeResource) -> None:
        raise RuntimeError("something unrelated broke")

    handlers: SessionHandlers[_FakeResource] = SessionHandlers(open=open_, close=broken, terminate=broken)

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    manager.call("conn", handlers, work)

    assert manager.close("conn") is False
    manager.shutdown()


def test_close_reports_unconfirmed_when_terminate_itself_raises() -> None:
    # The separate close/terminate family's fallback path (ACP): if the graceful close
    # never settles and the forceful terminate() it falls back to also fails, teardown
    # is genuinely unconfirmed, not a success with a swallowed exception.
    manager = SessionManager(drain_seconds=0.05)

    async def open_() -> _FakeResource:
        return _FakeResource(1)

    async def close_(_resource: _FakeResource) -> None:
        await asyncio.sleep(10)

    async def terminate_(_resource: _FakeResource) -> None:
        raise RuntimeError("kill failed")

    handlers: SessionHandlers[_FakeResource] = SessionHandlers(
        open=open_, close=close_, terminate=terminate_
    )

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    manager.call("conn", handlers, work)

    assert manager.close("conn") is False
    manager.shutdown()


def test_a_second_close_attempt_after_a_close_is_terminate_family_fails_stays_unconfirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # close() used to pop the connection from the registry unconditionally, before
    # knowing whether teardown actually succeeded - a probe reproduced this making a
    # *second* close attempt falsely report success (nothing left registered to fail
    # against) while the resource was still alive, and is_open falsely report the
    # connection as already gone in the meantime. Neither must happen: the connection
    # stays registered, unconfirmed, until teardown is actually confirmed.
    from backend.app.actions import sessions as sessions_module

    monkeypatch.setattr(sessions_module, "_NO_SEPARATE_TERMINATE_SECONDS", 0.2)
    manager = SessionManager(drain_seconds=0.05)
    close_calls = {"n": 0}

    async def open_() -> _FakeResource:
        return _FakeResource(1)

    async def hang(_resource: _FakeResource) -> None:
        close_calls["n"] += 1
        await asyncio.sleep(10)

    handlers: SessionHandlers[_FakeResource] = SessionHandlers(open=open_, close=hang, terminate=hang)

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    manager.call("conn", handlers, work)

    first_confirmed = manager.close("conn")
    assert first_confirmed is False
    assert manager.is_open("conn") is True, (
        "a connection whose teardown could not be confirmed must not be reported as closed"
    )

    second_confirmed = manager.close("conn")
    assert second_confirmed is False, (
        "a second close attempt must not falsely report success just because there is "
        "nothing new left to confirm"
    )
    assert manager.is_open("conn") is True
    # A no-op retry for this family (no independently-more-forceful path exists) must
    # not even re-invoke the handler a second time - confirmed directly, not merely
    # inferred from the returned outcome.
    assert close_calls["n"] == 1

    manager.shutdown()


def test_a_second_close_attempt_against_a_separate_close_terminate_family_retries_and_can_succeed() -> None:
    # Unlike the close-is-terminate family above, a family with a genuine, independent
    # forceful path (ACP's PID-based terminate()) can make real progress on a retry -
    # a second close() attempt escalates straight to terminate() again, and confirms
    # once it actually succeeds.
    manager = SessionManager(drain_seconds=0.05)
    terminate_calls = {"n": 0}

    async def open_() -> _FakeResource:
        return _FakeResource(1)

    async def close_(_resource: _FakeResource) -> None:
        await asyncio.sleep(10)  # never settles, forcing escalation to terminate()

    async def terminate_retriable(_resource: _FakeResource) -> None:
        terminate_calls["n"] += 1
        if terminate_calls["n"] == 1:
            raise RuntimeError("kill failed the first time")

    handlers: SessionHandlers[_FakeResource] = SessionHandlers(
        open=open_, close=close_, terminate=terminate_retriable
    )

    async def work(resource: _FakeResource) -> int:
        return resource.resource_id

    manager.call("conn", handlers, work)

    first_confirmed = manager.close("conn")
    assert first_confirmed is False
    assert manager.is_open("conn") is True

    second_confirmed = manager.close("conn")
    assert second_confirmed is True, (
        "a family with a genuine forceful path must be able to retry and succeed on a "
        "second attempt"
    )
    assert manager.is_open("conn") is False
    assert terminate_calls["n"] == 2

    manager.shutdown()
