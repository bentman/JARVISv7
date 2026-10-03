# 0008 - Operator Experience

Date: 2026-09-07
Status: Implemented
Related: 0005, 0006, 0007, 0010, 0011, 0013, 0014

## Context and Problem Statement

The backend, Tauri, and desktop component surfaces for agents, actions, extensions, memory, settings, provider profiles, readiness, and diagnostics exist. The desktop operator layout must expose them clearly without changing backend ownership.

The layout decision starts from `desktop/src/index.html`'s three-column shell: a left status sidebar, the conversation panel, and a right operator sidebar. Backend, Readiness, and Services are durable status information; Personality, Resident Voice, Wake, Memory, Actions, Extensions, and Settings are operator controls with different frequency and space needs.

At decision time, the desktop defects were:

- Agent capability is not exposed in the desktop surface. `desktop/src/components/agents-panel.js` exists and `desktop/src/api-client.js` reaches Tauri commands backed by live `/agents` routes, but `desktop/src/main.js` and `desktop/src/index.html` do not mount it.
- Provider-profile editing falls back to read-only built-in profiles without a clear explanation, loses the just-created or just-edited profile after reload, and lets unrelated operator-config saves disable Providers & Models controls.
- The operator controls need one clear launch point and one roomier control surface.

Backend, Readiness, and Services are not operator-control categories. They are persistent visibility indicators and remain on the left. Personality is a frequent operator selection and moves to the right sidebar, directly above Resident Voice.

Two of those defects - the unmounted agents panel and the provider-profile state loss - predate this redesign and would normally belong in their own record rather than in a layout ADR. They are kept here because the remount is what surfaced and fixed them, and because a retroactive ADR for already-shipped work would add process without recording a decision. Future operator-surface defect work gets its own record.

## Decision Drivers

- Fix desktop defects where the UI misrepresents or hides existing backend/Tauri capability.
- Expose Agents through the same advanced-control surface as Memory, Actions, Extensions, Settings, and Providers & Models.
- Keep Backend, Readiness, and Services visible on the left instead of nesting them behind a new control panel.
- Keep frequent session controls visible on the right: Personality, Resident Voice, and Wake.
- Replace the right-side Memory/Actions/Extensions/Settings button row with one clear launch button for advanced operator controls.
- Make no backend route or Tauri command changes. Provider profile writes and provider selection changes are direct operator-local writes and do not require a separate approval record.
- Preserve ADR 0005's governed-action visibility and ADR 0006's extension vocabulary.

## Decision Outcome

The desktop operator layout changes as follows:

- Backend, Readiness, and Services remain visible in the left status sidebar.
- A single advanced-control launch button is placed directly below the left-side status indicators.
- Personality moves from the left status sidebar to the right operator sidebar, directly above Resident Voice.
- Resident Voice and Wake remain visible in the right operator sidebar.
- The existing right-side Memory, Actions, Extensions, and Settings button row is removed.
- The advanced-control button opens one larger control panel with a left category rail and right detail pane.
- Each Advanced Controls category presents operator-familiar workflows for its family. Internal registry words such as capability ID, proposal, authorization rule, fingerprint, local ID, and raw definition are hidden by default and appear only in explicit detail/audit views.

The advanced-control panel contains categories for:

| Category | Current source |
|---|---|
| Provider Model Profiles | `llm-provider-settings.js`: routing and escalation selection, profile CRUD from provider-type presets, profile duplication, connection test with model discovery, credential rotation |
| Settings | Operator-config fields and `appearance-controls.js` |
| Memory | `memory-panel.js` |
| Actions | `actions-panel.js` |
| Extensions | `extensions-panel.js` |
| Agents | `agents-panel.js` |

Backend, Readiness, Services, Personality, Resident Voice, and Wake are not moved into the advanced-control panel.

Specific behavior corrections included in this ADR:

- Mount `agents-panel.js` through the advanced-control panel using the existing `apiClient` methods and Tauri/backend routes.
- In `llm-provider-settings.js`, prefer an editable profile when available instead of defaulting to the selected built-in managed profile.
- When a built-in provider profile is selected, show an explicit read-only explanation.
- After provider profile create/update, keep the acted-on profile selected after reload.
- In `settings-panel.js`, do not let unrelated operator-config saves blanket-disable Providers & Models controls.
- Make right-sidebar selector labels, including Resident Voice `VOICE SELECTOR` and `MODE`, match the font and size of Personality's `CURRENT` label.

## Consequences

Positive:
- Agents are reachable from the same advanced-control surface as the other non-persistent operator categories.
- Advanced controls get a scalable container without hiding durable system visibility indicators.
- Backend, Readiness, and Services remain visible while the operator works.
- Personality, Resident Voice, and Wake stay fast to reach.
- Provider-editor state better matches backend state.
- Provider profile writes and provider selection changes become direct local writes in the capability registry; destructive provider actions remain approval-gated.

Negative:
- This touches multiple desktop surfaces in one change.
- Existing panel components need their mount/host assumptions adjusted for the shared advanced-control panel.
- Moving Personality from the left to the right changes its visual grouping and requires careful spacing above Resident Voice.
- Tests need to cover both layout relocation and provider/settings state defects.

## Implementation

This ADR is implemented in code and contract tests and confirmed in native operator validation.

Layout:
- `desktop/src/index.html` keeps Backend, Readiness, and Services in the left status sidebar and adds a single `#advanced-controls-trigger` button, with the `#settings-restart-required` badge, in an `.operator-actions` section directly below Services.
- The Personality block moves to the right operator sidebar directly above Resident Voice. Its `dl.facts` markup is replaced by `<label class="selector-label" for="personality-select">Current</label>`, so Personality `CURRENT`, Resident Voice `VOICE SELECTOR`, and `MODE` are the same element and class. The `#personality-select`, `#personality-current`, and `#personality-detail` ids are unchanged.
- The right-side Memory/Actions/Extensions/Settings icon-button row and the four inline mount sections are removed, along with the `.icon-button`, `.settings-trigger-group`, and `.operator-trigger-group` rules in `desktop/src/style.css`.

System state:
- `desktop/src/components/desktop-state.js` owns the error panel as well as System State and the Turn Status rail. A failed operation is shown in the error panel and the rail; System State reports backend lifecycle and readiness, and an error changes it only when the caller names a lifecycle state such as `BACKEND_UNAVAILABLE`. `desktop/src/main.js` delegates `showError` and `clearError` to it.

Rendered shell evidence:
- `desktop/tests/app.test.mjs` boots the real `desktop/src/index.html` and `desktop/src/main.js` in jsdom through `bootDesktop` in `desktop/tests/support.mjs`, standing in only the Tauri `invoke` bridge. jsdom is a `desktop/package.json` devDependency. It covers startup rendering from backend payloads, startup failure diagnostics, text turns rendered as text, personality switching and saved-preference restore, voice-mode selection with the wake PTT fallback, and Advanced Controls category switching, mount/unmount, last-category retention, and backdrop and Close dismissal.
- jsdom implements no modal dialog behavior, so the harness models `showModal` and `close` from the HTML specification. Escape, focus containment, focus return, layout, and fonts need the native Tauri WebView and remain native validation.

Advanced-control surface:
- `desktop/src/index.html` adds a native `<dialog id="advanced-panel">` outside `.shell`, holding a header, a `#advanced-panel-rail` category rail of six buttons, and six hidden mounts: `#providers-panel`, `#settings-panel`, `#memory-panel`, `#actions-panel`, `#extensions-panel`, `#agents-panel`.
- `showModal()` supplies modal focus containment, Escape dismissal, `::backdrop`, and focus return to the launch button. `desktop/src/main.js` adds only backdrop-click dismissal and routes Escape, the Close button, and a backdrop click through a single `close`-event hook.
- `desktop/src/components/advanced-panel.js` introduces `createAdvancedPanelCoordinator`, a DOM-free single-select sequencer over `{ id, isOpen, open, close }` categories exposing `openCategory`, `closeActive`, `requestClose`, and `activeCategoryId`. It suppresses dismissal while a category switch or teardown is in progress, so a panel's own `onClose` report cannot re-enter as a new dismissal.
- `createOperatorPanelCoordinator` is removed from `desktop/src/components/memory-panel.js`; the coordinator above replaces it as the single owner of category switching.
- `desktop/src/style.css` adds `.advanced-panel`, `::backdrop`, `.advanced-panel-rail` with an `[aria-selected="true"]` state, and `.advanced-panel-detail`, sized with `min()` and collapsing to a single column inside the existing 820px breakpoint. A `--color-backdrop` token is added inside the token block.
- `.advanced-panel-detail` is shared by every category, so `desktop/src/main.js` records its scroll position per category before a switch and before the dialog closes (Close, backdrop, and the dialog's `cancel` event for Escape), and restores it when that category reopens.

Draft, scroll, and focus preservation:
- `desktop/src/components/render-state.js` owns capture and restore of `data-draft-key` field values, `data-scroll-key` scroll positions, and the focused `data-focus-key` control across a panel's full re-render. `createRenderStateKeeper` also retains that state when a category closes and reapplies it on the next open until the reopened panel has loaded.
- Extensions, Actions, and Agents render through the keeper; Actions and Agents key their buttons and prompt/propose controls so a click that triggers a refresh keeps focus.

Agents:
- `desktop/src/components/agents-panel.js` is rewritten to the panel contract used by Actions and Extensions: a DOM-free `createAgentsPanelController(handlers, onState)` plus `createAgentsPanel(container, handlers, options)` returning `{ open, close, isOpen, controller }`, mounted from `desktop/src/main.js` through the existing `apiClient` agent methods.
- It unwraps `AgentListResponse.agents` and `AgentRunResponse.records`, uses separate sequence counters for the catalog and runs, and renders runs from their capability-audit envelope (`kind`, `capability_id`, `recorded_at`, nested `record`) rather than assuming top-level run fields. `agentRunProfileId` derives the agent from the `agent-invoke-` capability prefix.
- Governed outcomes are reported honestly: an `awaiting_approval` invocation is not shown as success, a refused cancel is reported as refused, and the Cancel control is gated on the profile's `cancellable` flag.
- Profile problems from `AgentListResponse.problems` are listed as agents that could not be loaded. The external-agent definition is chosen from the catalog's `acp` extensions with their status, not typed.
- An invocation holds its own pending state, so Cancel and permission/input answers stay available while it runs. While a run is live the panel polls agent runs and extension runs; `agentProposalId` finds the in-flight invocation's proposal, Cancel targets it through `cancelAction`, and the existing `cancelAgent` route is the fallback before that proposal is known.
- An ACP-runtime agent's detail shows its definition's status and live connection, and a Test connection control that sends one fixed prompt through the definition's own `prompt` operation (`invokeExtension`) and reports the streamed reply or a readable failure. The linked extension runs render their permission and input requests through `desktop/src/components/run-request.js`, the same controls the Extensions panel uses.
- The last run's output is read from `output.response` for internal agents and from the linked run's streamed `agent_message_chunk` updates for ACP agents. An invocation paused for approval lists pending approvals with Approve and Decline. Runs render as per-proposal timelines named by agent, with identifiers and records behind Details.
- `invoke_agent` in `desktop/src-tauri/src/lib.rs` is async and dispatches through `spawn_blocking`, like `invoke_extension`, so a run waiting on an operator answer does not hold the blocking pool that answering and cancelling use. `desktop/src-tauri/src/backend.rs` gives `POST /agents/invoke` a timeout covering the 600 s profile maximum.

Action audit:
- `desktop/src/components/actions-panel.js` presents capabilities, pending approvals, execution status, and audit in operator language: `capabilityTitle`, `formatCapabilityRisk`, `capabilityReadinessText` (including degraded and unavailable readiness), `actionStatusText`, and `describeAuditRecord`, which reads the nested record of each kind - proposal, authorization decision, approval, execution result (including failure error and `outcome_unknown`), and cancellation. `groupAuditRecords` renders one timeline per proposal.
- Capability, proposal, and approval IDs, the execution owner, raw arguments, and raw records appear only inside explicit Details disclosures. Descriptor problems are grouped under Could not load. The generic runner remains as Run manually for audit and fallback use.

Provider and settings state:
- Provider type presets (Unsloth, llama.cpp, Ollama, vLLM, OpenAI, Anthropic, Custom OpenAI-compatible) fill the endpoint, model, context window, and timeout of a new profile; models found by a connection test populate a selector that also sets the context window. A profile that holds the primary, fallback, or cloud role cannot be deleted. Provider Model Profiles lays routing and escalation beside profile editing.
- Stopping a backend the desktop spawned requests `POST /daemon/shutdown` and waits for the process to exit before falling back to a kill, so the server lifespan stops the managed llama.cpp sidecar. `/daemon/shutdown` raises an in-process `SIGINT`, which runs that lifespan on Windows.
- `desktop/src/components/llm-provider-settings.js` exposes the `openProviderSettings` / `closeProviderSettings` mount for the Provider Model Profiles category. `defaultEditingProfile` prefers the acted-on profile, then the first editable profile, before falling back to the selected or first profile. `builtinProfileNotice` renders an explicit read-only explanation for built-in profiles. The acted-on profile id is threaded through create and update reloads and cleared on delete, so a just-created or just-edited profile stays selected.
- `desktop/src/components/settings-panel.js` replaces its boolean `restartRequired` with a `restartScopes` set of `operator` and `provider`. The badge, restart notice, and Restart button reflect the union; operator fields are disabled only by the operator scope and provider controls only by the provider scope. Provider controls remain enabled after unrelated operator-config saves. Both mounts carry a generation guard so a resolved load cannot repopulate a container that was switched away.

`invoke_agent` changed only from a synchronous to an async command. `POST /config/llm/profiles/{profile_id}/test` accepts an optional draft body so a new or edited profile is tested before it is saved; `resolve_provider_test_target` in `backend/app/services/llm_provider_service.py` resolves it for the route and for the `provider-connectivity-test` capability alike. A built-in managed profile is tested by id and reports its readiness without discovery, and a stored credential is used only while the draft keeps the saved profile's kind and endpoint. The Tauri `test_llm_profile` command forwards the optional draft. `backend/app/api/app.py` installs one `CapabilityServiceError` handler, so a direct operator request its capability refuses - for example a provider profile timeout below the argument schema minimum - returns the capability service's status and readable message instead of a 500. `backend/app/actions/catalog.py` classifies provider profile writes and provider selection changes as direct `allow` local writes, and `CapabilityService.execute_operator_action` records approval evidence only for direct operator requests whose capability rule actually requires approval.

### Family workflow surfaces

This ADR owns the operator presentation of every family whose behavior another ADR owns. Backend policy, execution, and evidence stay with the owning ADR; only the surface is decided here.

- Actions: `desktop/src/components/actions-panel.js` exposes catalog availability, descriptor problems, typed invocation, pending decisions, cancellation, and selectable audit records. Route-owned credential and input-answer operations identify their execution owner. ADR 0005 owns the underlying governance.
- Extensions: `desktop/src/components/extensions-panel.js` provides MCP Add/Edit/Remove for stdio and HTTP, discovery, grouped Tools/Resources/Prompts, invocation, Disconnect, credentials, and OAuth controls; Skill Import/Edit/Remove with progressive body disclosure and provenance-based editability; and Local Tool and External Agent (ACP) Add/Edit/Remove for fixed argv commands with a process boundary, sharing one workflow keyed by family. Edits preserve hidden manifest fields and use fingerprints; transport is fixed at creation. The panel follows the other Advanced Controls surfaces: the catalog offers Add MCP connection, Import skill, Add local tool, and Add external agent buttons that open their form in the detail column (as Agents opens its editor), every control sits in a labeled field with placeholders reserved for examples, the family filter is a labeled select, and the detail leads with the extension name while identifier, provenance, source, and revision stay under Details. ADR 0006 owns the taxonomy and catalog, ADR 0010 and ADR 0011 the MCP behavior.
- Runs: run identity, masked requested inputs, progress, readable event/failure summaries, cancellation, structured elicitation, model-proposal decisions, and explicit unknown-outcome warnings. Text tool results, prompt messages, and text/image resources render from their actual wrapped result. Discovery shows counts and artifacts are listed when present; full results, unsupported content, events, and correlation IDs remain in Run details. Records created before operation metadata was retained still render their status and existing evidence.
- Agents: `desktop/src/components/agents-panel.js` as described above. ADR 0007 owns agent identity; ADR 0013 owns external runtime behavior.
- Preserved drafts, scroll, and keyed control focus across panel refreshes; source, revision, and internal identifiers remain available through detail disclosure.

Native `invoke_extension` is async and dispatches the blocking backend request through `tauri::async_runtime::spawn_blocking`.

ADR 0014 owns the visual language, shared panel primitives, operator vocabulary, and the conversation's continuity with these surfaces; this ADR owns which surfaces exist and what each exposes.

Advanced Controls stays operator-facing: Providers use profile and credential language; Memory uses review, confirm, correct, and forget language; Actions is an audit/debug view; Extensions uses ADR 0006 family workflows; Agents uses ADR 0007 and ADR 0013 workflows. Internal registry words - capability ID, proposal, authorization rule, fingerprint, local ID, raw definition - stay behind explicit detail views.

### Native validation ownership

This ADR is the single owner of native operator validation. No other ADR carries native interaction evidence as follow-up: backend and contract evidence closes those ADRs, and confirming their behavior in a real desktop session is this ADR's closeout obligation.

## Confirmation

Implementation files:
- `desktop/src/index.html`
- `desktop/src/main.js`
- `desktop/src/style.css`
- `desktop/src/api-client.js`
- `desktop/src/components/advanced-panel.js`
- `desktop/src/components/render-state.js`
- `desktop/src/components/run-request.js`
- `desktop/src/components/actions-panel.js`
- `desktop/src/components/extensions-panel.js`
- `desktop/src/components/agents-panel.js`
- `desktop/src/components/memory-panel.js`
- `desktop/src/components/llm-provider-settings.js`
- `desktop/src/components/settings-panel.js`
- `desktop/src/components/appearance-controls.js`
- `desktop/src/components/desktop-state.js`
- `desktop/package.json`
- `desktop/src-tauri/src/lib.rs`
- `desktop/src-tauri/src/backend.rs`
- `backend/app/api/app.py`
- `scripts/validate_desktop.py`

Test coverage:
- `desktop/tests/layout.test.mjs` for advanced-control category registration and switching, single-select rail semantics, idempotent dismissal, re-entrant `onClose` suppression, and relocated layout and source ordering
- `desktop/tests/agents.test.mjs` for agent list/run envelope unwrapping, honest invoke/cancel reporting, stale-response ordering, the profile form against the backend `AgentProfile` fields, profile problems, the ACP definition picker, in-flight cancellation by proposal, permission answers, output from internal and ACP agents, connection testing, and the rendered external-agent detail
- `desktop/tests/settings.test.mjs` for provider default selection and post-mutation reselection, built-in read-only messaging, and restart-scope isolation
- `desktop/tests/extensions.test.mjs` for wrapped-result rendering, Disconnect refresh, connection status, the extension id rule shared with the backend, local tool and ACP definition add/remove, scroll retention across polling and category close, and main.js wiring every handler each operator panel calls
- `desktop/tests/actions.test.mjs` for unknown-outcome presentation, operator-language risk/readiness/titles, one sentence per audit record kind, per-proposal timelines, and raw identifiers appearing only inside Details
- `desktop/tests/status.test.mjs` for System State, Turn Status, and operation errors that must not replace System State
- `desktop/tests/shell.test.mjs` for client commands matching registered Tauri commands and bridge calls matching backend routes
- `desktop/tests/app.test.mjs` for the rendered desktop shell described under Rendered shell evidence, including per-category scroll restoration and an unsent draft surviving a category switch
- `desktop/src-tauri/src/backend.rs` and `desktop/src-tauri/src/lib.rs` unit tests for backend launch, shutdown drain, port-owner safety, and citation destinations
- `backend/tests/unit/services/test_capability_service.py`, `backend/tests/unit/api/test_llm_config_routes.py`, and `backend/tests/unit/services/test_llm_provider_profiles.py` for provider profile writes as direct local actions; `test_llm_config_routes.py` also covers a refused profile write returning its readable reason, selection updates passing capability validation, and draft connection tests for new, overridden, and built-in profiles
- `backend/tests/unit/api/test_routes.py` for the default daemon shutdown raising an in-process signal

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_desktop.py regression` (runs `npm --prefix desktop test` and `cargo test --manifest-path desktop/src-tauri/Cargo.toml`)
- `backend/.venv/Scripts/python scripts/validate_backend.py unit` when provider or action classification changes
- Native visible-session validation on `windows-amd64` through `npm --prefix desktop run dev`, with results recorded under `reports/validation/`

Native validation has covered the shell layout and sizing, Close, backdrop, focus return, per-category scroll retention, the Extensions split, the provider-profile create/select/error/delete workflow, ACP definition add/edit/remove, the agent workflows (definition picker, Test connection, invocation, a permission request answered from the Agents panel, in-flight cancellation, last-run output), and the readable action audit with its Details disclosures. It has also covered Escape dismissal by physical keypress; a model-proposed approval raised in a conversation turn and decided from the Actions panel and from the conversation card; MCP invocation, elicitation answered from the Extensions panel, confirmed cancellation, Disconnect, and reconnection after the server process was killed mid-call and after a call outlived its deadline; and ADR 0014's surface - one visual language across the shell and all six categories, a `POST /task/text` turn from another client appearing with its origin, a handoff reply attributed to its agent, and the conversation surviving a page reload. Which MCP call paths report `outcome_unknown` is ADR 0010's; the operator presentation of that status is covered by `desktop/tests/actions.test.mjs` and `desktop/tests/extensions.test.mjs`.

## Follow-up

None for this ADR.

Future operator-surface work should update this ADR when it preserves the same architecture,
or create/supersede an ADR when it changes the architecture.
