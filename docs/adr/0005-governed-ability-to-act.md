# 0005 - Governed Ability to Act

Date: 2026-09-01
Status: Accepted
Related: 0002, 0003, 0004, 0006, 0007, 0008

## Context and Problem Statement

JARVISv7 becomes useful when it can act: search, change settings, configure providers, manage memory lifecycle, call services, use tools, connect external capability, or delegate to agents. Acting must remain visible enough that the user can understand what happened, stop it, correct it, and distinguish low-risk reads from higher-risk side effects.

The architecture needs one governable action loop. A capability must have a stable identity, input contract, effect class, readiness/availability state, authorization rule, execution owner, timeout/cancellation behavior, result shape, artifact evidence, and user-facing unavailable explanation.

## Decision Drivers

- Action governance should be based on effect and risk, not feature label.
- Specific operator requests authorize the requested action without a second approval.
- External, mutating, privileged, destructive, privacy-sensitive, or cloud-transmitting actions need explicit authorization.
- Model output can request or propose an action, but application code must validate, authorize, execute, and record it.
- Action results and external content must return as untrusted context.
- Tools, search, provider configuration, memory lifecycle, MCP, skills, plugins, and agents need one evidence model.
- Preserve ADR 0002's turn ownership, ADR 0003's model/application authority boundary, and ADR 0004's memory lifecycle while action capability grows.

## Decision Outcome

Risk determines friction:

- Local read: inspect local state already in scope.
- Local write: change repo, config, memory, profile, or local files.
- External read: send a query or request outside the machine.
- External write: mutate a remote system or send a message.
- Cloud model: transmit prompt/context to a cloud LLM provider.
- Privileged execution: run shell/process, plugin code, agent process, or MCP server command.
- Destructive action: delete, overwrite, reset, purchase, transfer, publish, or otherwise hard-to-reverse work.

A clear, specific operator request authorizes that action, regardless of effect class or whether it arrives through a UI or natural language. The application validates scope, arguments, readiness, and execution boundaries and records authorization and execution evidence, without asking the operator to approve the same request again. This authority does not extend to additional actions proposed by the model. Those proposals follow the effect-based authorization rules, including explicit approval for private outbound context and other approval-required operations.

Session-bearing capabilities use one host-owned lifecycle mechanism to keep connections reachable across calls. Family adapters own protocol negotiation, session identity, recovery, and resource teardown. Connection reuse does not itself provide durable conversation recovery or authorize subsequent actions.

## Consequences

Positive:
- Action can grow without each feature inventing its own trust model.
- Low-risk operations stay usable because governance is tied to effect, not form.
- The user sees meaningful approval prompts where authority or risk changes.
- Search, provider routing, memory lifecycle, tools, MCP, plugins, skills, and agents can share one evidence model.
- Prompt injection and model mistakes are easier to contain because external content and tool output remain untrusted context.

Negative:
- A unified action model requires shared infrastructure before broad model-callable tool use is enabled.
- Provider-native tool features need wrapping before they can participate safely.
- Approval UX must be designed carefully or useful automation will feel blocked.
- Capability metadata can become stale unless readiness and health checks are real observations.
- More artifact detail is needed as actions become more capable.

## Implementation

This ADR is partially implemented. Shared governance, execution boundaries, durable evidence, and session management are built. Agent operator-invocation authorization and the action audit presentation remain incomplete.

### Capability governance and execution

`backend/app/actions/contracts.py` defines capability descriptors, proposals, authorization decisions, approval records, execution results, cancellation records, and the capability registry. Registration validates schemas, availability, effect classes, execution boundaries, metadata trust, and duplicate identities. `APPROVAL_EFFECT_CLASSES` supplies the default authorization posture; private-context search, executable plugin installation, and server-declared MCP tool effects use explicit approval rules. ADR 0006 owns MCP classification.

`backend/app/services/capability_service.py` owns proposal, authorization, execution, cancellation, and audit. It refreshes observed readiness and handler bindings, reports malformed descriptors individually, and revalidates parked proposals before approval. Pending proposals have bounded retention; repeated decisions are refused and secret-bearing arguments are masked.

`execute_operator_action` and `invoke_operator_capability` carry operator authorization while retaining the shared execution and evidence path. Dedicated extension invocation uses the latter. Model proposals still follow the approval ladder. `execute_authorized` supplies the turn-scoped execution entry point; the generic operator API refuses turn-boundary capabilities that require a conversation owner.

`backend/app/actions/boundaries.py` enforces allowed storage roots, deadlines, cancellation, result limits, and process argv/environment/working-directory declarations. Process-bearing extension capabilities use these controls. They provide application-level containment, not an OS sandbox.

Search records plans, provider attempts, sources, approval, cancellation, and failure evidence through `SearchIntentResolver`, `SearchService`, and `TurnEngine`. Provider routing observes cloud eligibility, endpoint and secret-store readiness, fallback policy, and attempt evidence. Settings writes are allowlisted and masked; memory lifecycle operations use service-owned revision checks and lifecycle events. ADR 0003 owns model authority and ADR 0004 owns memory behavior.

### Shared connection lifecycle

`backend/app/actions/sessions.py` defines `SessionManager` and `SessionHandlers`. One background event loop in a dedicated thread owns a manager's connections. An opaque connection ID selects the resource; a per-connection lock serializes the complete open-and-work sequence. Adapters supply open, close, and async terminate handlers. Cancelled initialization must clean up its own partial resources.

Close coordinates with the same lock, marks the connection closed to new work, and uses bounded waits for draining and cancellation. Queued calls cannot reuse or reopen a closed connection object. An adapter-reported dead resource receives best-effort cleanup before its reference is discarded; a subsequent call can open a replacement. Calls with uncertain effects raise `SessionCallOutcomeUnknown` and are not automatically replayed.

`close` and `close_prefix` return whether teardown was confirmed. `_close_and_evict_if_confirmed` removes a connection only after confirmation, checking object identity so it cannot remove a newer resource under the same ID. Unconfirmed teardown retains the resource and registry entry while blocking further work. `is_open` therefore reports a retained resource, not a guarantee that it is healthy or usable.

For adapters whose close and terminate handlers are identical, the manager awaits one teardown attempt with a 10-second ceiling. A failed attempt remains unconfirmed on subsequent closes instead of invoking a consumed handler and treating a no-op as success. Adapters with a separate terminate handler can retry that forceful path. Only the specifically recognized SDK cancel-scope exception is accepted as completed teardown; unrelated exceptions remain failures. MCP and ACP adapter details belong to ADR 0006 and ADR 0007 respectively.

`shutdown` closes tracked connections, requests loop stop, and joins the thread with a bounded timeout; the loop object closes when its worker exits. This does not establish that every resource was terminated: unconfirmed teardown remains unconfirmed, and a coroutine that never cooperates with cancellation may remain pending. The thread-join timeout is not a total shutdown deadline.

`ExtensionRuntimeService` supplies one manager to both adapters. Family adapters bind callbacks to the current call, so connection reuse does not retain the first caller's event or permission context.

### Evidence and operator surface

Action records are persisted and fsynced to `data/actions/action-log.jsonl`, with bounded rotation. Turn artifacts retain proposals, decisions, approvals, execution results, cancellations, search evidence, and delegated runs. Tool results enter prompts as untrusted context.

`SessionCallOutcomeUnknown` is preserved as `outcome_unknown` by both capability execution and extension run recording. Desktop status renders it distinctly; extension invocation warns against repeating a call whose effects are unknown.

Extension run records retain operation identity, display name, and arguments masked by the existing action policy. ADR 0006 owns their operator-readable presentation and MCP teardown-result handling.

`desktop/src/components/actions-panel.js` exposes catalog availability, descriptor problems, typed invocation, pending decisions, cancellation, and selectable audit records through backend/Tauri APIs. Route-owned credential and input-answer operations identify their execution owner. Dedicated extension and agent workflows are owned by ADR 0006 and ADR 0007; ADR 0008 owns native operator layout and interaction validation.

## Confirmation

Implementation files are identified above. Focused coverage:

- `backend/tests/unit/actions/test_action_contracts.py`, `backend/tests/unit/actions/test_action_catalog.py`, and `backend/tests/unit/actions/test_action_boundaries.py`: registration, authorization posture, and execution boundaries.
- `backend/tests/unit/actions/test_sessions.py`: reuse, serialized work, initialization/close races, cancellation-resistant handlers, bounded waits, shutdown, confirmed teardown, retained failed closes, and family-specific retry behavior.
- `backend/tests/unit/services/test_capability_service.py`: authorization, execution, audit, and preservation of `outcome_unknown`.
- `backend/tests/integration/test_extension_runtime.py`: operator invocation without self-approval, model-proposal approval, and propagation of teardown and unknown-outcome records through application services. Family-specific lifecycle evidence belongs to ADR 0006 and ADR 0007.
- `desktop/tests/static.test.mjs`: action controls, audit presentation, and distinct unknown-outcome styling.

`backend/tests/fixtures/search_providers.py` and `backend/tests/fixtures/action_governance.py` support deterministic action-path checks; `scripts/validate_backend.py runtime --mock` selects mock-based runtime coverage.

Recorded validation (windows-amd64):

- `backend\.venv\Scripts\python scripts/validate_backend.py unit`: PASS, 1555 passed, 7 platform/privilege skips.
- `backend\.venv\Scripts\python scripts/validate_backend.py integration`: PASS, 60 passed, including MCP subprocess lifecycle, operator/model authorization, and failed OAuth teardown.
- `npm --prefix desktop test`: PASS; static and behavior checks for actions, extensions, and agents.
- `cargo build --manifest-path desktop/src-tauri/Cargo.toml`: PASS. The compiler reported an incremental-cache finalization warning; the build completed successfully.

Earlier live backend validation on linux-amd64 demonstrated direct allow execution, approval/denial/cancellation records, refusal of repeated decisions, secret masking in durable audit, and isolation of malformed catalog entries. Native desktop interaction remains unverified. Backend closeout uses `scripts/validate_backend.py unit` and `scripts/validate_backend.py integration`; runtime checks require the relevant provider/process availability.

## Follow-up

- Route fully specified operator agent invocation through `CapabilityService.invoke_operator_capability`. `POST /agents/invoke` still uses the proposal path and can ask for self-approval; preserve agent run tracking, cancellation, and evidence when correcting it. ADR 0007 owns the agent workflow.
- Complete operator-readable action audit/detail presentation for proposals, decisions, results, cancellations, descriptor problems, and unavailable states. Keep raw IDs and backend records in explicit detail controls, with the generic runner available for audit and fallback use.
- Obtain native interaction evidence for direct execution, required model-proposal approvals, cancellation, and inspectable action evidence. ADR 0008 owns native layout and interaction validation; computer-use validation was excluded from MCP closeout.
