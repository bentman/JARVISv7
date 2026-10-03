# 0014 - Unified Operator Experience

Date: 2026-09-29
Status: Implemented
Related: 0002, 0005, 0007, 0008, 0013

## Context and Problem Statement

ADR 0008 gave every operator family a surface, but each surface was built on its own. The result read as several applications sharing a window:

- Visual language: a thin token set, about fifteen font sizes (several below 11px), one button style with no hover or focus-visible state, sunken inputs only in Settings, an undefined `--color-bg-card`, and every panel prefix redeclaring its own section, facts, notice, error, and help rules with different values.
- Panel behavior: `appendText`, labeled values, error formatting, disclosures, buttons, and fields copied three or four times; Memory, Settings, and Providers re-rendering without preserving drafts; destructive actions without confirmation; drifting words (Deny/Decline, Delete/Remove, three meanings of Cancel); raw enums, ISO times, and identifiers in the open.
- Channel and interface continuity: an approval-required action raised inside a text or voice turn was held only by the turn engine, never reached the capability service's pending inbox, and lapsed at the next turn. Only execution results from turns reached the capability audit. Agent handoff replies carried no agent name. Turns made over HTTP or the inbound ACP bridge never appeared in the desktop, and the desktop conversation was lost on reload because no history API existed.

The operator must see one assistant: the same words, controls, and look on every surface, and the same turns and approvals whichever channel (text, push-to-talk, wake, hands-free, handoff) or interface (desktop, HTTP client, ACP bridge, a panel decision) produced them.

## Decision Drivers

- One visual language and one vocabulary across the shell and every Advanced Controls category.
- Every turn and every approval is visible in the conversation and in the panels, regardless of the channel or interface that produced it.
- An approval is one shared item: deciding it anywhere settles it everywhere.
- The conversation survives a desktop reload.
- Backend APIs change additively; ADR 0002 keeps turn ownership and ADR 0005 keeps governance.
- Refine the existing dark look rather than add a theme.
- The operator interfaces are the desktop, HTTP clients, and the inbound ACP bridge; `scripts/run_jarvis.py` stays a developer diagnostic path.

## Decision Outcome

The desktop adopts one design system and one vocabulary, and the backend exposes one continuity contract that the desktop conversation projects.

Design system:
- One token set in `desktop/src/style.css`: a type scale with a 12px floor, weights, line heights, a 4-8-12-16-24-32 spacing scale, radii, a focus ring, and motion that is disabled under `prefers-reduced-motion`. Appearance presets override only the scale tokens.
- Plain buttons are secondary. Submit buttons and `.btn-primary` carry the accent; `.btn-danger` marks destructive actions and `.btn-ghost` row-level actions. Every button, input, select, textarea, and summary has hover, focus-visible, and disabled states. Inputs share one sunken style.
- Panels share generic classes (`panel-header`, `panel-box`, `panel-field`, `panel-facts`, `panel-help`, `panel-notice`, `panel-error`, `panel-buttons`, `status-badge[data-state]`) in place of per-prefix copies.

Shared primitives in `desktop/src/components/ui/`:
- `dom.js` builds text, options, buttons by variant, labeled fields with help, facts, and Details disclosures.
- `format.js` owns readable errors, conflict detection, value and time formatting, enum humanizing, and one status-text and status-state map.
- `vocabulary.js` owns the operator words: Approve/Decline for approvals, Cancel run for runs only, Discard for closing an unsaved form, Delete for operator-owned profiles and definitions, Enable/Disable. "Action" is the operator word; "capability" and identifiers appear only inside Details. Rail labels match each panel heading.
- `panel.js` owns the panel header, the live notice/error region, loading/empty/unavailable section states, and a lifecycle that renders through the render-state keeper and polls only while live work exists.
- `confirm.js` owns the destructive-action confirmation, injected into panels so it is testable.

Continuity contract:
- Turn origin. Every turn records where it came from: `desktop`, `api`, `acp`, `voice`, `panel`, `extension`, or `agent`. `POST /task/text` accepts an optional origin, the desktop sends `desktop`, and the inbound ACP bridge passes `acp`.
- Agent attribution. A turn answered by a handed-off or routed agent records `agent: {profile_id, display_name}` in its artifact and text-turn response.
- History. `GET /session/turns?after=<turn_id>&limit=` returns the active session's turn summaries, oldest first: origin, modality, transcript, response, agent, final state, failure, start time, search evidence, and the actions the turn proposed or settled with their status. A confirm or cancel turn lists the proposal it approved, executed, declined, or withdrew, so an action's outcome appears in the turn that decided it.
- One approval inbox. When a turn raises an approval-required action, the engine holds it in the capability service as a conversation-origin pending approval with a readable label. It appears in `/actions/pending`, in the Agents panel for the agent that asked, and as `pending_approval` in session status. A decision from any panel settles it by running the conversation's own confirm or cancel turn with origin `panel`; a spoken or typed answer, or the turn boundary, releases it from the inbox.
- Complete audit. Proposal, authorization-decision, approval, and cancellation records produced inside turns are mirrored into the capability audit, so turn-initiated actions have the same timeline as panel-initiated ones.

Conversation projection:
- The desktop conversation is a projection of the session's turns. It loads history at startup and fetches turns after the last one it rendered whenever the turn count changes, deduplicating by turn id. A local text turn renders from its own response and is reconciled by turn id; voice turns arrive through the same feed. When a later turn reports a newer status for an action, every chip for that action shows it.
- A page reload keeps the backend and its session: unloading the page stops only polling, closing the window shuts the backend down natively, and startup resumes the session the backend still holds instead of creating one.
- Each turn shows its speaker (the agent during a handoff, otherwise the personality), its time, origin and modality chips, and action chips that open Actions on that action. The agent chip and the handoff status open Agents on that agent.
- While the conversation waits on an approval, it shows an approval card with Approve and Decline. A decision made from the card, Actions, Agents, or a reply clears it everywhere, and the resulting panel-origin turn reads as the operator's answer.

## Consequences

Positive:
- Every surface looks, reads, and behaves the same, so learning one panel teaches the rest.
- An approval the assistant asks for stays visible and answerable until it is decided, however busy the conversation.
- Turns made by other interfaces are visible to the operator, and the conversation survives reload.
- Panel code shrinks; fixes to shared behavior land once.

Negative:
- The conversation depends on the history API and polling cadence for turns made elsewhere.
- Conversation-origin approvals are settled through a turn, so a panel decision waits for an idle conversation and reports `conversation_busy` while another turn runs.
- Shared primitives are a coupling point; a change to one reaches every panel.

## Implementation

Backend:
- `backend/app/conversation/turn_manager.py` and `backend/app/artifacts/turn_artifact.py` carry turn `origin`; the artifact also carries `agent`.
- `backend/app/conversation/engine.py` records origin per entry point, attributes agent-answered turns, holds approval-required tool and agent approvals in the capability service with a settle callback, releases them on a spoken answer, turn boundary, or session close, and exposes `pending_approval` and `settle_pending_approval`.
- `backend/app/actions/contracts.py` gives `ActionEvidence` an optional sink; `backend/app/services/capability_service.py` mirrors turn evidence into its audit, lists held approvals in `pending()` with `origin`, `label`, and `proposed_by`, and routes `decide`, `cancel`, and `status` for held approvals through the conversation.
- `backend/app/services/session_service.py` builds turn summaries and pages them; `backend/app/api/routes/session.py` and `backend/app/api/schemas/session.py` expose `GET /session/turns` and `pending_approval`; `backend/app/api/routes/task.py` and `backend/app/api/schemas/task.py` carry origin and agent on text turns; `backend/app/extensions/acp_server.py` passes origin `acp`.

Desktop:
- `desktop/src-tauri/src/backend.rs` and `desktop/src-tauri/src/lib.rs` add the `get_session_turns` command and send origin `desktop`; `desktop/src/api-client.js` exposes `getSessionTurns`. `start_backend` resumes the tracked session through `resumable_session`, and an extension invocation outlasts the backend's 60 s operation ceiling so a run waiting on operator input is not reported as a transport failure.
- The Backend panel carries ARCH and the endpoint with a compact Restart control that starts or restarts the backend; the session id sits in the Conversation header; Readiness lists model families followed by cloud escalation. Settings places Display Language beside Appearance and pairs each search service toggle with its configuration; the Redis cache fields stay out of the Settings panel.
- `desktop/src/style.css` holds the tokens, control states, generic panel classes, and conversation entry, chip, and approval-card styles.
- `desktop/src/components/ui/` holds the shared primitives; the Actions, Agents, Extensions, Memory, Settings, and Providers panels are built on them.
- `desktop/src/components/conversation.js` renders turns, notes, and the approval card; `desktop/src/main.js` feeds it from session status and `get_session_turns`, and opens Advanced Controls on a linked action or agent. `desktop/src/components/resident-voice.js` hands completed voice turns to the same feed. The resident-voice and wake widgets render readable labels and values.
- The shared panel lifecycle polls only while live work exists; for Extensions that includes an invocation that has not returned, whose run may be waiting on an input request only the poll can surface.

## Confirmation

Implementation files:
- `backend/app/conversation/engine.py`
- `backend/app/conversation/turn_manager.py`
- `backend/app/artifacts/turn_artifact.py`
- `backend/app/actions/contracts.py`
- `backend/app/services/capability_service.py`
- `backend/app/services/session_service.py`
- `backend/app/services/turn_service.py`
- `backend/app/api/routes/session.py`
- `backend/app/api/routes/task.py`
- `backend/app/api/schemas/actions.py`
- `backend/app/api/schemas/session.py`
- `backend/app/api/schemas/task.py`
- `backend/app/extensions/acp_server.py`
- `desktop/src-tauri/src/backend.rs`
- `desktop/src-tauri/src/lib.rs`
- `desktop/src/api-client.js`
- `desktop/src/style.css`
- `desktop/src/index.html`
- `desktop/src/main.js`
- `desktop/src/components/conversation.js`
- `desktop/src/components/ui/dom.js`
- `desktop/src/components/ui/format.js`
- `desktop/src/components/ui/vocabulary.js`
- `desktop/src/components/ui/panel.js`
- `desktop/src/components/ui/confirm.js`
- `desktop/src/components/actions-panel.js`
- `desktop/src/components/agents-panel.js`
- `desktop/src/components/extensions-panel.js`
- `desktop/src/components/memory-panel.js`
- `desktop/src/components/settings-panel.js`
- `desktop/src/components/llm-provider-settings.js`
- `desktop/src/components/appearance-controls.js`
- `desktop/src/components/resident-voice.js`
- `desktop/src/components/wake-indicator.js`

Test coverage:
- `backend/tests/unit/conversation/test_tool_turn.py` for the shared inbox, audit mirroring, the turn-boundary release, a spoken answer settling the shared entry, panel decisions running the conversation's turn and appearing in that turn's summary, and agent attribution
- `backend/tests/unit/api/test_routes.py` for text-turn origin, `pending_approval` in session status, and `/session/turns` paging after a cursor
- `backend/tests/unit/artifacts/test_turn_artifact.py` for the artifact fields
- `backend/tests/unit/services/test_turn_service.py`, `backend/tests/unit/extensions/test_acp_server.py`, and `backend/tests/integration/api/test_headless_client.py` for origin passing
- `desktop/tests/app.test.mjs` for history at startup, the origin chip, the approval card deciding and clearing, the action chip opening Actions and updating to the settled status, and single rendering across syncs
- `desktop/src-tauri/src/backend.rs` unit tests for resuming only the session the backend still holds
- `desktop/tests/extensions.test.mjs` for an unanswered invocation counting as live work and a failed action keeping its extension in view
- `desktop/tests/layout.test.mjs` for defined tokens, the type-scale floor, button variants, and focus-visible
- `desktop/tests/agents.test.mjs`, `desktop/tests/extensions.test.mjs`, `desktop/tests/memory.test.mjs`, `desktop/tests/settings.test.mjs`, and `desktop/tests/actions.test.mjs` for shared vocabulary, confirmations, conflict reloads, and draft keys
- `desktop/tests/shell.test.mjs` for command and route parity including `get_session_turns`

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration`
- `backend/.venv/Scripts/python scripts/validate_desktop.py regression`

## Follow-up

None for this ADR.

Future operator-surface or continuity work should update this ADR when it preserves the same architecture,
or create/supersede an ADR when it changes the architecture.
