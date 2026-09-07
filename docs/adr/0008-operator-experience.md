# 0008 - Operator Experience

Date: 2026-09-07
Status: Accepted
Related: 0002, 0004, 0005, 0006, 0007

## Context and Problem Statement

The backend, Tauri, and desktop component surfaces for agents, actions, extensions, memory, settings, provider profiles, readiness, and diagnostics exist. The desktop operator layout must expose them clearly without changing backend ownership.

`desktop/src/index.html` currently uses a three-column layout: a left status sidebar, the conversation panel, and a right operator sidebar. The left sidebar shows durable status information: Backend, Readiness, Services, and Personality. The right sidebar shows Resident Voice, Wake, and a row of single-letter/operator buttons for Memory, Actions, Extensions, and Settings.

The required desktop change has three parts:

- Agent capability is not exposed in the desktop surface. `desktop/src/components/agents-panel.js` exists and `desktop/src/api-client.js` reaches Tauri commands backed by live `/agents` routes, but `desktop/src/main.js` and `desktop/src/index.html` do not mount it.
- Provider-profile editing falls back to read-only built-in profiles without a clear explanation, loses the just-created or just-edited profile after reload, and lets unrelated operator-config saves disable Providers & Models controls.
- The operator controls need one clear launch point and one roomier control surface.

Backend, Readiness, and Services are not operator-control categories. They are persistent visibility indicators and remain on the left. Personality is a frequent operator selection and moves to the right sidebar, directly above Resident Voice.

## Decision Drivers

- Fix desktop defects where the UI misrepresents or hides existing backend/Tauri capability.
- Expose Agents through the same advanced-control surface as Memory, Actions, Extensions, Settings, and Providers & Models.
- Keep Backend, Readiness, and Services visible on the left instead of nesting them behind a new control panel.
- Keep frequent session controls visible on the right: Personality, Resident Voice, and Wake.
- Replace the right-side Memory/Actions/Extensions/Settings button row with one clear launch button for advanced operator controls.
- Make no backend route, Tauri command, or capability-record changes.
- Preserve ADR 0005's governed-action visibility and ADR 0006's extension vocabulary.

## Decision Outcome

The desktop operator layout changes as follows:

- Backend, Readiness, and Services remain visible in the left status sidebar.
- A single advanced-control launch button is placed directly below the left-side status indicators.
- Personality moves from the left status sidebar to the right operator sidebar, directly above Resident Voice.
- Resident Voice and Wake remain visible in the right operator sidebar.
- The existing right-side Memory, Actions, Extensions, and Settings button row is removed.
- The advanced-control button opens one larger control panel with a left category rail and right detail pane.

The advanced-control panel contains categories for:

| Category | Current source |
|---|---|
| Providers & Models | `llm-provider-settings.js`: primary/fallback/cloud selection, profile CRUD, connection test, credential rotation |
| Operator Settings | Operator-config fields and `appearance-controls.js` |
| Memory | `memory-panel.js` |
| Actions & Capabilities | `actions-panel.js` |
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
- No backend, Tauri, or capability-registry surface changes are required.

Negative:
- This touches multiple desktop surfaces in one change.
- Existing panel components need their mount/host assumptions adjusted for the shared advanced-control panel.
- Moving Personality from the left to the right changes its visual grouping and requires careful spacing above Resident Voice.
- Tests need to cover both layout relocation and provider/settings state defects.

## Implementation

This ADR is implemented.

Layout:
- `desktop/src/index.html` keeps Backend, Readiness, and Services in the left status sidebar and adds a single `#advanced-controls-trigger` button, with the `#settings-restart-required` badge, in an `.operator-actions` section directly below Services.
- The Personality block moves to the right operator sidebar directly above Resident Voice. Its `dl.facts` markup is replaced by `<label class="selector-label" for="personality-select">Current</label>`, so Personality `CURRENT`, Resident Voice `VOICE SELECTOR`, and `MODE` are the same element and class. The `#personality-select`, `#personality-current`, and `#personality-detail` ids are unchanged.
- The right-side Memory/Actions/Extensions/Settings icon-button row and the four inline mount sections are removed, along with the `.icon-button`, `.settings-trigger-group`, and `.operator-trigger-group` rules in `desktop/src/style.css`.

Advanced-control surface:
- `desktop/src/index.html` adds a native `<dialog id="advanced-panel">` outside `.shell`, holding a header, a `#advanced-panel-rail` category rail of six buttons, and six hidden mounts: `#providers-panel`, `#settings-panel`, `#memory-panel`, `#actions-panel`, `#extensions-panel`, `#agents-panel`.
- `showModal()` supplies modal focus containment, Escape dismissal, `::backdrop`, and focus return to the launch button. `desktop/src/main.js` adds only backdrop-click dismissal and routes Escape, the Close button, and a backdrop click through a single `close`-event hook.
- `desktop/src/components/advanced-panel.js` introduces `createAdvancedPanelCoordinator`, a DOM-free single-select sequencer over `{ id, isOpen, open, close }` categories exposing `openCategory`, `closeActive`, `requestClose`, and `activeCategoryId`. It suppresses dismissal while a category switch or teardown is in progress, so a panel's own `onClose` report cannot re-enter as a new dismissal.
- `createOperatorPanelCoordinator` is removed from `desktop/src/components/memory-panel.js`; the coordinator above replaces it as the single owner of category switching.
- `desktop/src/style.css` adds `.advanced-panel`, `::backdrop`, `.advanced-panel-rail` with an `[aria-selected="true"]` state, and `.advanced-panel-detail`, sized with `min()` and collapsing to a single column inside the existing 820px breakpoint. A `--color-backdrop` token is added inside the token block.

Agents:
- `desktop/src/components/agents-panel.js` is rewritten to the panel contract used by Actions and Extensions: a DOM-free `createAgentsPanelController(handlers, onState)` plus `createAgentsPanel(container, handlers, options)` returning `{ open, close, isOpen, controller }`, mounted from `desktop/src/main.js` through the existing `apiClient` agent methods.
- It unwraps `AgentListResponse.agents` and `AgentRunResponse.records`, uses separate sequence counters for the catalog and runs, and renders runs from their capability-audit envelope (`kind`, `capability_id`, `recorded_at`, nested `record`) rather than assuming top-level run fields. `agentRunProfileId` derives the agent from the `agent-invoke-` capability prefix.
- Governed outcomes are reported honestly: an `awaiting_approval` invocation is not shown as success, a refused cancel is reported as refused, and the Cancel control is gated on the profile's `cancellable` flag.

Provider and settings state:
- `desktop/src/components/llm-provider-settings.js` gains the `openProviderSettings` / `closeProviderSettings` mount for the Providers & Models category, so provider controls no longer live inside the operator settings form. `defaultEditingProfile` prefers the acted-on profile, then the first editable profile, before falling back to the selected or first profile. `builtinProfileNotice` renders an explicit read-only explanation for built-in profiles. The acted-on profile id is threaded through create and update reloads and cleared on delete, so a just-created or just-edited profile stays selected.
- `desktop/src/components/settings-panel.js` replaces its boolean `restartRequired` with a `restartScopes` set of `operator` and `provider`. The badge, restart notice, and Restart button reflect the union; operator fields are disabled only by the operator scope and provider controls only by the provider scope. The blanket `querySelectorAll("input, select, button")` disable is removed, so an unrelated operator-config save no longer disables Providers & Models. Both mounts carry a generation guard so a resolved load cannot repopulate a container that was switched away.

No backend route, Tauri command, API-client route, or capability-record change was made.

## Confirmation

Validated on `linux-amd64` (WSL2):

- `npm --prefix desktop test` — `PASS`. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers advanced-control category registration and switching, single-select rail semantics, idempotent dismissal, re-entrant `onClose` suppression, agent list/run envelope unwrapping, `agentRunProfileId`, honest invoke/cancel reporting, stale-response ordering, provider default selection, post-mutation reselection, built-in read-only messaging, restart-scope isolation, relocated layout and source ordering, and the advanced-control style contract.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml` — `PASS`. `Finished \`dev\` profile ... in 36.12s`, confirming no Tauri-side change was introduced.
- Live desktop session — `SKIPPED`. No screenshot or window-capture tool is available on this host, so the surface was not observed visually. In its place the rendered markup and components were driven end to end in a real DOM outside the repo (no repo dependency added), asserting: Backend/Readiness/Services remain in the left sidebar with the launch button below them; Personality renders above Resident Voice with all three selector labels sharing `.selector-label`; each category mounts and unmounts on rail switching; dismissal unmounts every category exactly once and a rail switch never dismisses; the provider editor opens on an editable profile; selecting a built-in shows the read-only explanation; an operator-config save leaves provider controls enabled; the save outcome survives the re-render; a created profile stays selected after reload; and the agent catalog, run records, and an `awaiting_approval` invocation render honestly.

## Follow-up

The decision is fully implemented. One validation step remains and requires a host with a visible desktop session:

- Confirm the advanced-control dialog's sizing, rail spacing, and selected-category contrast, and confirm Escape, backdrop click, and focus return against a real WebView2/WebKit `<dialog>`. Report the host class and the exact command.
