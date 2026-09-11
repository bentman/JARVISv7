"""Shared session-lifecycle mechanism for capabilities whose external counterpart is
itself a session - a still-running subprocess, a resumable remote conversation - so
MCP and ACP do not each manage their own process lifetime. See ADR 0005's Follow-up
for the researched shape this implements and why: a background loop owns a long-lived
resource, a call dispatches into that loop instead of starting its own, and closing has
a bounded drain-then-terminate escape rather than an indefinite wait.

This module only owns connection identity - is a resource alive, here is a fresh one
under the same connection id - never session identity. Whether a protocol's own
resume/reconnect concept actually restores prior state is decided by the protocol
adapter that calls this module, not by this module.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

R = TypeVar("R")
T = TypeVar("T")

DEFAULT_DRAIN_SECONDS = 1.0

# How long to wait for a single close/terminate attempt when a family declares no
# independently-more-forceful terminate (handlers.close is handlers.terminate) - fixed
# rather than scaled by drain_seconds, since it reflects a real close's own worst-case
# duration (confirmed against the MCP SDK's own documented ~6s stdio shutdown ceiling:
# a 2s wait for graceful exit, then a kill, then up to 2s to confirm it), not the
# mechanism's own coordination steps.
_NO_SEPARATE_TERMINATE_SECONDS = 10.0


class SessionResourceDiedError(Exception):
    """An opener or call raises this to tell the manager its resource is unusable.

    The manager evicts the resource so the next call opens a fresh one under the same
    connection id. Raising this says nothing about whether the operation that raised it
    executed on the far side before the resource died - see `SessionCallOutcomeUnknownError`.
    """


class SessionCallOutcomeUnknownError(Exception):
    """A call's resource died, was cancelled, or was terminated while it was in flight.

    Whether the far side already executed the call before that happened is unknown - it
    is not reported as a failure, because assuming failure could cause a caller to retry
    something that already ran. Deciding whether to resend the request is an
    effect-dependent judgment for the protocol adapter, not this mechanism.
    """


@dataclass(frozen=True, slots=True)
class SessionHandlers(Generic[R]):
    """Family-specific behavior a protocol adapter supplies once per connection.

    `open` creates the long-lived resource. `close` asks it to end gracefully.
    `terminate` forcibly ends it and must be safe to call on an already-dead resource.
    It is async, not because the mechanism bounds it further, but because a real kill
    can itself require awaiting something - the MCP SDK's own stdio shutdown escalates
    through SIGTERM then SIGKILL (or a Windows Job Object hard-kill) inside a shielded
    async sequence with its own internal timeouts; ACP's process-tree kill is
    synchronous today but still awaited so it does not block the shared loop while it
    runs. The mechanism awaits `terminate` to completion rather than imposing its own
    `drain_seconds` bound on top: `terminate` is the last resort once graceful attempts
    already gave up, so bounding it again would just leave the resource in the same
    undetermined state the mechanism exists to avoid - each family's own implementation
    is responsible for guaranteeing its own bound, the way both current ones already do.
    `on_notification`, if given, receives anything the resource delivers unsolicited,
    with no call currently waiting on a response, so a protocol adapter can observe
    progress or session-update messages instead of them being silently dropped.
    """

    open: Callable[[], Awaitable[R]]
    close: Callable[[R], Awaitable[None]]
    terminate: Callable[[R], Awaitable[None]]
    on_notification: Callable[[Any], None] | None = None

    # `open` must clean up any partially-constructed resource itself if it raises or is
    # cancelled (a close racing an in-flight open cancels it and does not otherwise learn
    # what state it left behind) - `close`/`terminate` are only ever called against a
    # resource `open` finished returning.


class _Connection(Generic[R]):
    __slots__ = ("closed", "current_task", "handlers", "lock", "resource", "teardown_attempted")

    def __init__(self, handlers: SessionHandlers[R]) -> None:
        self.handlers = handlers
        self.resource: R | None = None
        self.lock = asyncio.Lock()
        self.current_task: asyncio.Task[Any] | None = None
        # Set once this specific connection object has been closed, so a call that was
        # already queued on `lock` when close() ran fails clearly instead of silently
        # reusing a connection whose teardown has already started - regardless of
        # whether that teardown is confirmed yet. The manager's own registry only drops
        # this object once teardown is confirmed (see `close`'s docstring); until then
        # it stays registered under its connection id specifically so a second attempt
        # can find and retry it, rather than a fresh open silently starting a duplicate
        # resource alongside one that may still be alive.
        self.closed = False
        # Whether a teardown attempt has already run against this resource - a second
        # `close`/`terminate` call for a family with no independently-more-forceful path
        # (MCP: `close is terminate`) would otherwise look like a clean success (no
        # exception) without confirming anything new, since the resource's own close()
        # already consumed its one-shot internal state on the first attempt.
        self.teardown_attempted = False


class SessionManager:
    """Host-owned background event loop that keeps long-lived connections open across
    separate calls instead of each call opening and closing its own.

    One shared loop backs every connection a given manager instance owns. Sharing the
    loop does not make two calls against the *same* resource safe to interleave - MCP
    stdio in particular is one channel with no per-request stream - so each connection
    carries its own lock and calls against it are serialized through that lock, not
    through the loop.
    """

    def __init__(self, *, drain_seconds: float = DEFAULT_DRAIN_SECONDS) -> None:
        self._drain_seconds = drain_seconds
        self._connections: dict[str, _Connection[Any]] = {}
        self._registry_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._registry_lock:
            if self._loop is not None:
                return self._loop
            ready = threading.Event()
            holder: dict[str, asyncio.AbstractEventLoop] = {}

            def run() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                holder["loop"] = loop
                ready.set()
                loop.run_forever()
                loop.close()

            thread = threading.Thread(target=run, name="session-manager-loop", daemon=True)
            thread.start()
            ready.wait()
            self._loop = holder["loop"]
            self._thread = thread
            return self._loop

    def _connection(self, connection_id: str, handlers: SessionHandlers[R]) -> _Connection[R]:
        with self._registry_lock:
            existing = self._connections.get(connection_id)
            if existing is not None:
                return existing
            created: _Connection[R] = _Connection(handlers)
            self._connections[connection_id] = created
            return created

    def is_open(self, connection_id: str) -> bool:
        with self._registry_lock:
            connection = self._connections.get(connection_id)
            return connection is not None and connection.resource is not None

    def call(
        self,
        connection_id: str,
        handlers: SessionHandlers[R],
        work: Callable[[R], Awaitable[T]],
        *,
        timeout_s: float | None = None,
    ) -> T:
        """Dispatch `work` against the connection's resource on the shared loop.

        Opens the resource first if this connection has none yet. Evicts the resource
        if `work` raises `SessionResourceDiedError`, so the next call reopens a fresh one
        under the same `connection_id`. A timeout or an external cancellation while the
        call is in flight raises `SessionCallOutcomeUnknownError` rather than a generic
        failure, since the resource may have already executed the call.
        """
        loop = self._ensure_loop()
        connection = self._connection(connection_id, handlers)

        async def run() -> T:
            async with connection.lock:
                if connection.closed:
                    # This call queued for the lock before close() ran and only now got
                    # it - the connection is gone. Failing here, rather than silently
                    # reopening under this now-evicted object, is what close() marking
                    # `closed` under the same lock is for; the next call for this
                    # connection_id will look up the registry fresh and get a new object.
                    raise SessionResourceDiedError(f"connection {connection_id!r} was closed")
                if connection.resource is None:
                    # Tracked as current_task like the work task below, so a close racing
                    # this open sees it and can cancel/await it instead of finding
                    # resource is None and concluding there is nothing to close - see
                    # _close's handling of an in-flight task.
                    open_task = asyncio.ensure_future(handlers.open())
                    connection.current_task = open_task
                    try:
                        connection.resource = await open_task
                    except asyncio.CancelledError:
                        raise SessionCallOutcomeUnknownError(
                            f"open for connection {connection_id!r} was cancelled before it completed"
                        ) from None
                    finally:
                        if connection.current_task is open_task:
                            connection.current_task = None
                task = asyncio.ensure_future(work(connection.resource))
                connection.current_task = task
                try:
                    return await task
                except SessionResourceDiedError:
                    # The resource itself is what reported this, so its own bookkeeping
                    # (an SDK-internal task group, open file descriptors) may still need
                    # tearing down even though the remote process is already gone -
                    # dropping the reference without that leaves it to be garbage
                    # collected from whatever task happens to do it, at an arbitrary
                    # later time, which anyio in particular treats as a violation
                    # (a cancel scope exited from a different task than opened it).
                    # Best-effort: terminate() failing here must not replace the
                    # SessionResourceDiedError about to be re-raised.
                    dead_resource, connection.resource = connection.resource, None
                    if dead_resource is not None:
                        with contextlib.suppress(Exception):
                            await connection.handlers.terminate(dead_resource)
                    raise
                except asyncio.CancelledError:
                    raise SessionCallOutcomeUnknownError(
                        f"call against connection {connection_id!r} was cancelled before it completed"
                    ) from None
                finally:
                    if connection.current_task is task:
                        connection.current_task = None

        future = asyncio.run_coroutine_threadsafe(run(), loop)
        try:
            return future.result(timeout=timeout_s)
        except TimeoutError:
            future.cancel()
            raise SessionCallOutcomeUnknownError(
                f"call against connection {connection_id!r} did not finish before its timeout"
            ) from None

    def cancel_call(self, connection_id: str) -> bool:
        """Cancel the in-flight call against one connection without closing it.

        Distinct from `close`: the connection's resource stays open for the next call.
        Returns whether a call was actually in flight to cancel.
        """
        with self._registry_lock:
            connection = self._connections.get(connection_id)
        if connection is None or connection.current_task is None:
            return False
        loop = self._ensure_loop()
        loop.call_soon_threadsafe(_cancel_task, connection.current_task)
        return True

    def close(self, connection_id: str) -> bool:
        """End a connection deliberately.

        Drains a call already in flight for a bounded time; if it has not finished by
        then, cancels it and terminates the resource rather than waiting on it
        indefinitely. If there was no in-flight call, or it finished within the drain
        window, closes the resource gracefully instead - itself bounded, falling back
        to termination if the graceful close does not return in time either. Safe to
        call on a connection that was never opened or is already confirmed closed
        (both return `True` - there is nothing left to fail at tearing down).

        Returns whether teardown is actually confirmed rather than merely attempted -
        see `_close`'s own docstring. A caller that reports its own success/failure
        based on this action (Disconnect, Disable) must check the return value instead
        of assuming a bounded wait that gave up still means the resource is gone.

        The connection stays registered under `connection_id` - not evicted - until
        teardown is confirmed: a probe reproduced popping it unconditionally here
        making a *second* call falsely report success (nothing left registered to fail
        against) while the resource was still alive, and making `is_open` falsely
        report the connection as gone in the meantime. A caller that wants another
        attempt calls `close` again against the same, still-registered connection,
        which retries - or, for a family with no independently-more-forceful path
        beyond the one attempt already made (see `_close`), reports unconfirmed again
        without pretending a second no-op call confirmed anything new.
        """
        with self._registry_lock:
            connection = self._connections.get(connection_id)
        if connection is None:
            return True
        return self._close_and_evict_if_confirmed(connection_id, connection)

    def close_prefix(self, prefix: str) -> bool:
        """End every open connection whose id starts with `prefix`.

        For a family whose connection id is namespaced by more than just the
        definition's own identity - ACP connections are namespaced by host
        conversation too, so two conversations never share one agent's session - a
        definition edit or delete needs to close every connection under that
        definition, not just the one exact id it would otherwise guess at.

        Returns whether every matching connection's teardown was confirmed - see
        `close`'s own docstring, including its registration guarantee for an
        unconfirmed connection.
        """
        with self._registry_lock:
            matching = [(cid, conn) for cid, conn in self._connections.items() if cid.startswith(prefix)]
        confirmed = True
        for connection_id, connection in matching:
            if not self._close_and_evict_if_confirmed(connection_id, connection):
                confirmed = False
        return confirmed

    def close_all(self) -> None:
        """End every open connection - backend shutdown, not a single family's edit/delete.

        Leaves the background loop and its thread running - a caller that also wants
        those stopped (tests, a full process teardown) should call `shutdown()` instead.
        An unconfirmed connection stays registered - see `close`'s own docstring - not
        dropped just because a shutdown pass was made over it.
        """
        with self._registry_lock:
            connections = list(self._connections.items())
        for connection_id, connection in connections:
            self._close_and_evict_if_confirmed(connection_id, connection)

    def _close_and_evict_if_confirmed(self, connection_id: str, connection: _Connection[Any]) -> bool:
        confirmed = self._drain_and_close(connection_id, connection)
        if confirmed:
            with self._registry_lock:
                # Matched by identity, not just the key: a concurrent close could have
                # already evicted this exact object and a fresh open replaced it under
                # the same id, and this attempt must not delete that newer connection.
                if self._connections.get(connection_id) is connection:
                    del self._connections[connection_id]
        return confirmed

    def shutdown(self, *, timeout: float = 5.0) -> None:
        """Close every tracked connection, then stop and join the background loop thread.

        `close_all()` alone does not do this: the loop thread is a daemon, so it never
        blocks process exit, but it keeps running - real for a caller (a test, a service
        that creates and discards managers) that wants a clean, complete stop rather than
        relying on daemon-thread behavior at interpreter exit. `close_all()` only closes
        connections this manager is tracking; it does not enumerate or await arbitrary
        other tasks that might be scheduled on the loop outside of that tracking. Bounded
        by `timeout`: if the thread does not stop within it, `shutdown()` returns anyway
        rather than blocking indefinitely on a loop that is not responding to `stop()`.
        """
        self.close_all()
        with self._registry_lock:
            loop, self._loop = self._loop, None
            thread, self._thread = self._thread, None
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=timeout)

    def _drain_and_close(self, connection_id: str, connection: _Connection[Any]) -> bool:
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(self._close(connection_id, connection), loop)
        try:
            # terminate() is awaited to completion rather than bounded by drain_seconds
            # (see SessionHandlers.terminate), so this outer bound has to cover a
            # family's own worst case, not just the mechanism's own coordination steps -
            # MCP's SDK-driven stdio shutdown escalates through its own ~6s of internal
            # timeouts (SIGTERM wait, SIGKILL, reap) before terminate() can return. This
            # is a safety net against something unrelated hanging, not the mechanism's
            # real responsiveness bound.
            return future.result(timeout=self._drain_seconds * 3 + 15)
        except BaseException:
            # `_close` itself already reports `False` for every failure path it knows
            # about - reaching here means something outside that contract went wrong
            # (this outer safety-net timeout itself, or an unexpected exception `_close`
            # did not catch). Either way, the connection is gone from the registry
            # regardless, but teardown of the underlying resource is not confirmed - a
            # probe reproduced this exact branch previously being swallowed and treated
            # as success by every caller upstream.
            return False

    async def _close(self, connection_id: str, connection: _Connection[R]) -> bool:
        # Coordinates through connection.lock - the same lock call()'s run() holds for
        # its whole open+work sequence - rather than by inspecting current_task/resource
        # directly. Checking those without the lock cannot tell "no call is running" from
        # "a call finished opening and is about to start work": the lock can, because
        # run() does not release it until the entire open+work sequence is done. Bounded
        # by drain_seconds; if the lock is not free by then, _force_close cancels
        # whatever is running and terminates unconditionally.
        #
        # Returns whether teardown is actually confirmed, not merely attempted - a
        # probe reproduced this mechanism returning as if it had succeeded while the
        # resource was still alive, because every path below used to discard the
        # outcome once it stopped waiting rather than reporting it. `False` means the
        # resource may still be running; callers that need a guarantee before reporting
        # their own success (Disconnect, Disable) must check it instead of assuming.
        try:
            await asyncio.wait_for(connection.lock.acquire(), timeout=self._drain_seconds)
        except BaseException:
            return await self._force_close(connection)
        try:
            connection.closed = True
            resource = connection.resource
            if resource is None:
                return True
            if connection.handlers.close is connection.handlers.terminate:
                # No independently-more-forceful path exists for this family (true for
                # MCP: its close() already is the SDK's own full graceful-then-SIGKILL
                # escalation, and there is no lower-level kill beneath it this mechanism
                # can reach - McpSdkPeer does not expose the subprocess handle).
                if connection.teardown_attempted:
                    # A second call while the first attempt already ran cannot help -
                    # confirmed directly: it is either a no-op (the resource's own
                    # internal state was already consumed by the first call, so the
                    # second sees nothing left to close and would look like a clean
                    # success without confirming anything new) or, if made joinable via
                    # asyncio.shield so a second call waits on the same underlying work,
                    # corrupts anyio's own task-bound cancel-scope bookkeeping
                    # (`RuntimeError: Attempted to exit cancel scope in a different task
                    # than it was entered in`), also confirmed directly. A probe
                    # reproduced this exact no-op reporting success on a second call
                    # before this check existed. Reported as still unconfirmed instead
                    # of retried - the resource stays retained, not dropped, since
                    # nothing here has established it is actually gone.
                    return False
                connection.teardown_attempted = True
                close_task = asyncio.ensure_future(connection.handlers.close(resource))
                # Waiting longer for the one attempt - up to a fixed ceiling well past
                # what a real close realistically needs, not scaled by drain_seconds -
                # is the only thing that can help, since a second call cannot.
                if not await self._settle(close_task, timeout=_NO_SEPARATE_TERMINATE_SECONDS):
                    close_task.cancel()
                    await self._settle(close_task)
                    # Exceeding a ceiling already comfortably past the SDK's own ~6s
                    # worst-case escalation is itself the signal something is genuinely
                    # wrong - cancelling our own wrapper task afterward does not confirm
                    # the underlying resource died, only that we stopped waiting for it.
                    return False
                if _task_failed(close_task):
                    # Confirmed directly for MCP: closing a stdio connection from a
                    # different task than opened it can raise anyio's own
                    # `RuntimeError: Attempted to exit cancel scope in a different task
                    # than it was entered in` - but only *after* the SDK's own kill
                    # logic already ran, tearing down its internal task-group
                    # bookkeeping from the wrong task, not because the kill itself
                    # failed. Only that specific, recognized exception is treated as a
                    # confirmed kill anyway - retrieving it (not re-raising) is what this
                    # family's own close() contract can offer instead of a hard,
                    # PID-verified guarantee it has no way to provide (McpSdkPeer does
                    # not expose the subprocess handle a genuine kill confirmation would
                    # need). Any other exception is not something this mechanism has ever
                    # confirmed still means the resource died, so it is reported as
                    # unconfirmed rather than silently assumed benign the same way.
                    if _is_confirmed_kill_cancel_scope_error(close_task.exception()):
                        connection.resource = None
                        return True
                    return False
                connection.resource = None
                return True
            # A separate close/terminate family (ACP): a retry can meaningfully
            # escalate straight to the forceful, PID-based terminate() a second time,
            # skipping the graceful close() a first attempt already tried.
            if connection.teardown_attempted:
                confirmed = await self._run_terminate(connection.handlers.terminate, resource)
                if confirmed:
                    connection.resource = None
                return confirmed
            connection.teardown_attempted = True
            close_task = asyncio.ensure_future(connection.handlers.close(resource))
            if not await self._settle(close_task):
                # The graceful close did not finish within the bound - cancel it and
                # give it a further bounded chance to actually stop, the same way
                # _force_close already does for a work/open task. Terminating without
                # ever cancelling this task would abandon it, still pending and
                # unreferenced, to be garbage-collected mid-run rather than stopped.
                close_task.cancel()
                await self._settle(close_task)
                confirmed = await self._run_terminate(connection.handlers.terminate, resource)
            elif _task_failed(close_task):
                confirmed = await self._run_terminate(connection.handlers.terminate, resource)
            else:
                confirmed = True
            if confirmed:
                connection.resource = None
            return confirmed
        finally:
            connection.lock.release()

    @staticmethod
    async def _run_terminate(
        terminate: Callable[[Any], Awaitable[None]], resource: Any
    ) -> bool:
        try:
            await terminate(resource)
        except Exception:
            return False
        return True

    async def _force_close(self, connection: _Connection[R]) -> bool:
        # Marked closed before anything else, under no lock: this path only runs once
        # the lock could not be acquired within drain_seconds, so whatever call is still
        # running already has its own reference to the resource and is unaffected by
        # this connection's own copy - marking `closed` only stops a call still queued
        # on the lock from later acquiring it and reusing this connection.
        connection.closed = True
        task = connection.current_task
        if task is not None and not task.done():
            task.cancel()
            await self._settle(task)
        resource = connection.resource
        if resource is None:
            return True
        connection.teardown_attempted = True
        confirmed = await self._run_terminate(connection.handlers.terminate, resource)
        if confirmed:
            # Only dropped once teardown is actually confirmed - retaining it on
            # failure is what lets a later close() attempt retry against the same
            # resource instead of losing track of it (see `close`'s own docstring).
            connection.resource = None
        return confirmed

    async def _settle(self, task: asyncio.Task[Any], *, timeout: float | None = None) -> bool:
        """Waits up to `timeout` (default `drain_seconds`) for `task`, returning whether
        it actually finished.

        Never hangs past that bound, unlike `asyncio.wait_for(task, ...)` - a task can
        catch and swallow its own `CancelledError` and keep running, and `wait_for` keeps
        awaiting such a task's real completion underneath its own deadline instead of
        giving up on it once that deadline passes. `asyncio.wait` does not have this
        failure mode: it reports what is done versus still pending at the timeout mark
        regardless of whether the pending task ever completes.
        """
        done, _pending = await asyncio.wait([task], timeout=self._drain_seconds if timeout is None else timeout)
        return task in done


def _cancel_task(task: asyncio.Task[Any]) -> None:
    if not task.done():
        task.cancel()


def _task_failed(task: asyncio.Task[Any]) -> bool:
    """Whether a *done* task ended in an exception or was itself cancelled.

    `Task.exception()` raises `CancelledError` rather than returning it for a cancelled
    task, so a plain `task.exception() is not None` is not safe to call unconditionally.
    """
    if task.cancelled():
        return True
    return task.exception() is not None


def _is_confirmed_kill_cancel_scope_error(exc: BaseException | None) -> bool:
    """Whether `exc` is anyio's own benign cancel-scope bookkeeping error - confirmed by
    direct reproduction to occur only after a real kill already completed, when closing
    a stdio connection from a different task than opened it (see `_close`'s own
    docstring on the `close is terminate` branch). Any other exception is not something
    this mechanism has ever confirmed still means the resource died, so it must not be
    treated the same way - a test's own unrelated bug (a `NameError` in a handler,
    surfacing through this exact branch) reproduced silent, wrong success before this
    check existed to distinguish it from the one specific error that is actually safe.
    """
    return isinstance(exc, RuntimeError) and "cancel scope" in str(exc)
