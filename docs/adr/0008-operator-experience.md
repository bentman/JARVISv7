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

Not yet implemented.

Scope:
- `desktop/src/index.html`
- `desktop/src/main.js`
- `desktop/src/style.css`
- `desktop/src/components/agents-panel.js`
- `desktop/src/components/memory-panel.js`
- `desktop/src/components/actions-panel.js`
- `desktop/src/components/extensions-panel.js`
- `desktop/src/components/settings-panel.js`
- `desktop/src/components/llm-provider-settings.js`
- `desktop/src/components/appearance-controls.js`

No backend route, Tauri command, API-client route, or capability-record change is part of this ADR. The underlying `/agents`, action, extension, memory, settings, provider-profile, readiness, and diagnostics APIs already exist.

Expected shape of the change:
- Remove the current right-side Memory/Actions/Extensions/Settings trigger row.
- Add one advanced-control launch button below Backend, Readiness, and Services in the left sidebar.
- Implement one advanced-control panel with a category rail and detail pane for Providers & Models, Operator Settings, Memory, Actions & Capabilities, Extensions, and Agents.
- Move the Personality selector/detail block from the left sidebar to the right sidebar directly above Resident Voice.
- Keep Resident Voice and Wake in the right sidebar.
- Keep Backend, Readiness, and Services in the left sidebar.
- Align right-sidebar selector label typography so Personality `CURRENT`, Resident Voice `VOICE SELECTOR`, and Resident Voice `MODE` use the same font size, weight, casing pattern, and spacing.
- Preserve each panel's existing behavior after relocation.
- Add concrete responsive sizing, keyboard focus handling, Escape/backdrop dismissal, and visible selected-category state for the advanced-control panel.

## Confirmation

Confirmation requires:
- `npm --prefix desktop test` covering advanced-control launch, category switching, relocated panel mounting, selected-category state, keyboard dismissal, focus behavior, provider default selection, provider post-mutation reselection, built-in-profile messaging, scoped restart-required behavior, and right-sidebar selector-label typography.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml` to confirm no Tauri-side change was introduced.
- A live desktop session: Backend, Readiness, and Services remain visible on the left; the advanced-control button appears directly below them; Personality appears on the right above Resident Voice; Resident Voice and Wake remain visible; Agents, Memory, Actions, Extensions, Settings, and Providers & Models are reachable from the advanced-control panel and keep their existing behavior.

## Follow-up

Gaps required to complete this ADR:
- Implement the left-sidebar advanced-control launch button below Backend, Readiness, and Services.
- Implement the shared advanced-control panel in the desktop HTML, JavaScript, and CSS.
- Mount Providers & Models, Operator Settings, Memory, Actions & Capabilities, Extensions, and Agents inside the shared panel.
- Move Personality to the right sidebar above Resident Voice.
- Keep Backend, Readiness, Services, Resident Voice, and Wake outside the shared panel.
- Fix provider profile default selection, built-in read-only messaging, post-mutation reselection, and scoped restart-required behavior.
- Align the right-sidebar selector label typography for Personality, Voice Selector, and Mode.
- Add or update desktop tests for the relocated controls and state-handling fixes.
