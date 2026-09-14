# 0009 - Shared Session Lifecycle

Date: 2026-09-14
Status: Implemented
Related: 0005, 0010, 0013

## Context and Problem Statement

Several capability families hold a live external resource across more than one call: an MCP stdio subprocess, an MCP streamable-HTTP connection, an ACP agent process. Each needs the same things - keep the resource reachable between calls, serialize work against it, tear it down on demand, and report honestly when teardown could not be confirmed.

Without a shared owner, each family invents its own connection registry, its own event loop, and its own definition of "closed". That produces divergent teardown semantics, duplicated race handling, and per-family answers to the question an operator actually asks: is this thing still running?

This decision was originally recorded inside ADR 0005. It is extracted because two ADRs consume it, and a decision owned by one of its own consumers cannot close independently.

## Decision Drivers

- Connection reuse is infrastructure, not a property of any one protocol family.
- Teardown must be reported as confirmed or unconfirmed, never assumed.
- A call whose effects are uncertain must not be replayed automatically.
- Race handling between open, work, close, and cancellation should be written once.
- Family-specific protocol negotiation, session identity, and recovery stay with the family.

## Decision Outcome

Session-bearing capabilities use one host-owned lifecycle mechanism to keep connections reachable across calls.

`SessionManager` owns connection registry, scheduling, serialization, teardown confirmation, and shutdown. Family adapters own protocol negotiation, session identity, recovery, and resource teardown, supplied as handlers.

Connection reuse is a transport fact. It does not by itself provide durable conversation recovery, and it does not authorize subsequent actions - ADR 0005 owns authorization.

## Consequences

Positive:
- MCP and ACP do not each manage their own process lifetime.
- Race handling, bounded waits, and confirmation semantics are written and tested once.
- Unconfirmed teardown is visible rather than silently treated as success.
- A family can be added by supplying handlers rather than a parallel lifecycle.

Negative:
- A single background loop per manager is a shared failure domain.
- Confirmation semantics are stricter than most SDK close paths report, so adapters must map their own signals onto them.
- Containment is application-level: this is not an OS sandbox and does not guarantee process death.

## Implementation

`backend/app/actions/sessions.py` defines `SessionManager` and `SessionHandlers`. One background event loop in a dedicated thread owns a manager's connections. An opaque connection ID selects the resource; a per-connection lock serializes the complete open-and-work sequence. Adapters supply open, close, and async terminate handlers. Cancelled initialization must clean up its own partial resources.

Close coordinates with the same lock, marks the connection closed to new work, and uses bounded waits for draining and cancellation. Queued calls cannot reuse or reopen a closed connection object. An adapter-reported dead resource receives best-effort cleanup before its reference is discarded; a subsequent call can open a replacement. Calls with uncertain effects raise `SessionCallOutcomeUnknownError` and are not automatically replayed.

`close` and `close_prefix` return whether teardown was confirmed. `_close_and_evict_if_confirmed` removes a connection only after confirmation, checking object identity so it cannot remove a newer resource under the same ID. Unconfirmed teardown retains the resource and registry entry while blocking further work. `is_open` therefore reports a retained resource, not a guarantee that it is healthy or usable.

Adapters whose close and terminate handlers are identical get one awaited teardown attempt with a bounded ceiling; a failed attempt remains unconfirmed on subsequent closes rather than invoking a consumed handler and treating a no-op as success. Adapters with a separate terminate handler can retry that forceful path. Only a specifically recognized SDK cancel-scope exception is accepted as completed teardown; unrelated exceptions remain failures.

`shutdown` closes tracked connections, requests loop stop, and joins the thread with a bounded timeout; the loop object closes when its worker exits. This does not establish that every resource was terminated: unconfirmed teardown remains unconfirmed, and a coroutine that never cooperates with cancellation may remain pending. The thread-join timeout is not a total shutdown deadline.

`ExtensionRuntimeService` supplies one manager to both adapters. Family adapters bind callbacks to the current call, so connection reuse does not retain the first caller's event or permission context.

ADR 0005 owns authorization and action evidence for work performed over these connections. ADR 0010 owns MCP adapter behavior; ADR 0013 owns ACP adapter behavior, including its separate PID-based termination path.

## Confirmation

Implementation files:
- `backend/app/actions/sessions.py`
- `backend/app/services/extension_runtime_service.py`

Test coverage:
- `backend/tests/unit/actions/test_sessions.py`

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration` when adapter lifecycle behavior changes

## Follow-up

None for this ADR.

Future session-bearing families, durable cross-restart session recovery, or a change to confirmation semantics should update this ADR when they preserve the same lifecycle architecture, or create/supersede an ADR when they change it.
