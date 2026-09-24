# 0013 - ACP Adapter

Date: 2026-09-14
Status: Accepted
Related: 0002, 0005, 0006, 0007, 0009

## Context and Problem Statement

An external agent runtime reached over Agent Client Protocol is a process boundary, not a library call. It needs a subprocess or transport held across prompts, a protocol session that can survive process replacement, streamed updates attributed to the right caller, permission requests routed to the host, and honest reporting when a prompt's effects are uncertain.

JARVISv7 also exposes the reverse direction: an inbound bridge that lets an external ACP client drive JARVIS's own turn engine.

This decision was originally recorded inside ADR 0007. It is extracted because ACP v2 conformance is a long-running protocol effort, and holding it in the same ADR as agent identity means agent work cannot close while protocol alignment continues.

## Decision Drivers

- Protocol conformance is a separate concern from what an agent is and what it may do.
- A host conversation should reuse one agent process and protocol session; separate conversations should not share one.
- Replayed updates during resume must be attributed to the current call, not the call that opened the connection.
- An uncertain prompt must not be replayed automatically.
- Connection lifetime and teardown confirmation are ADR 0009's, not this adapter's.

## Decision Outcome

ACP is an adapter over ADR 0009's shared session lifecycle, consuming the adapter definitions ADR 0006 catalogs.

Connection identity is `acp:{agent_id}:{host_session_id}`: prompts in one host conversation reuse the same agent process and protocol session; separate host conversations use separate connections. A remembered protocol session ID may be resumed after process replacement when the agent advertises resume support; missing support or a failed resume falls back to a new session.

ACP work enters the ordinary turn admission path and records delegated-run evidence. It does not get a parallel execution or artifact model.

## Consequences

Positive:
- Agent identity can be completed and closed without waiting on full protocol conformance.
- Conversation-scoped connections give resume a meaningful boundary.
- Streamed updates, permission requests, and cancellation reuse the host's existing callback and evidence surfaces.

Negative:
- Resume is advertised capability, not proven interoperability; a fixture that supports resume does not establish that a real agent does.
- Remembered session IDs are host-memory state, so recovery does not survive a JARVIS restart.
- The inbound bridge's handshake and message shapes predate ACP v2 and must be realigned.

## Implementation

### Outbound

`backend/app/extensions/acp.py` consumes ADR 0006 adapter definitions and ADR 0009's shared session lifecycle. Definition edit/delete closes every connection for that agent through prefix matching.

An open connection holds its subprocess and SDK transport through an `AsyncExitStack`. Initialization and session creation or resume occur once per connection; subsequent work sends prompts. Event and permission callbacks bind before initialization/resume and again for each prompt, attributing replayed updates and new events to the current call.

A remembered protocol session ID can be resumed after process replacement when the agent advertises `sessionCapabilities.resume`. Remembered IDs are host-memory state; recovery across a JARVIS restart is not implemented. The SDK fixture requires the agent process to enable `use_unstable_protocol` for resume routing, so advertised capability alone does not establish real-agent compatibility.

Transport `ConnectionError` signals a dead resource for cleanup and eviction. Subsequent use can create a replacement; an uncertain prompt is not replayed automatically. ACP has a separate PID-based `_stop_process_tree` termination path, so forceful teardown can be retried when a prior close was unconfirmed - this is the adapter-supplied terminate handler ADR 0009 describes.

ACP work enters `TurnEngine.run_extension` admission and records delegated-run evidence as ADR 0007's `DelegatedRunRecord`, attributed to the agent profile when an ACP-runtime agent delegated the run. Streamed updates, permission requests, cancellation, and results flow through host callbacks and extension run records.

### Inbound

`backend/app/extensions/acp_server.py` implements a persistent local JSON-RPC bridge over loopback TCP, with tracked sessions, limits, timeouts, and requests routed through `TurnEngine.run_text_turn`. `backend/app/api/routes/acp_server.py` exposes start, stop, status, and session listing. Its lifecycle is implemented; its handshake and message shapes still require ACP v2 alignment.

### Boundaries owned elsewhere

ADR 0002 owns turn admission. ADR 0005 owns authorization and action evidence. ADR 0006 owns the adapter definitions this consumes. ADR 0007 owns agent identity, profiles, and isolation scope. ADR 0009 owns connection lifetime and teardown confirmation.

## Confirmation

Implementation files:
- `backend/app/extensions/acp.py`
- `backend/app/extensions/acp_server.py`
- `backend/app/api/routes/acp_server.py`

Test coverage:
- `backend/tests/unit/extensions/test_acp_bridge.py` for adapter callbacks, resume negotiation, and unsupported/failed resume fallback
- `backend/tests/unit/extensions/test_acp_server.py` for the local inbound bridge
- `backend/tests/integration/test_acp_sdk.py` for real process/session reuse, separate host-conversation isolation, current-call callbacks, cancellation, dead-process eviction, and resume after process replacement. The resume fixture persists history and emits recovered content, establishing content continuity rather than only matching session IDs
- `backend/tests/integration/test_extension_runtime.py` for ACP turn admission, permission/input handling, and delegated-run persistence

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration`

These establish implemented adapter and controlled fixture behavior. They do not establish interoperability with any external agent.

## Follow-up

- Complete outbound ACP v2 conformance: version/auth negotiation, distinct `session/list` and `session/close` operations, elicitation, and separate prompt acceptance/foreground completion in artifacts and status.
- Replace the inbound bridge's handshake/message shapes with ACP v2 session lifecycle, updates, permission/elicitation, cancellation, and absolute-path conventions.
- Ship disabled application ACP agent defaults for Antigravity, Claude Code, Codex, GitHub Copilot, and Qwen-capable execution, with operator overrides, installed-runtime discovery, setup, status, and unavailable reasons. Verify each real agent's resume routing and recovered conversation content.
- Establish resume durability across a JARVIS restart, or record that remembered session IDs are deliberately process-scoped.

Operator-facing external connection and testing workflows are owned by ADR 0008.
