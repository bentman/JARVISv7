# ADR 0014 — Unified Operator Experience: design system and cross-channel continuity

## Context

After ADR 0008's work the desktop is usable, but it still feels uneven. Three read-only audits found where the unevenness comes from.

**Visual (`desktop/src/style.css`)**
- The token block is thin:
  - spacing stops at 9px
  - about 15 font sizes are in use, several under 11px
  - there are no tokens for weight, line-height, focus or motion
- There is one button style (accent fill) and no hover or focus-visible states anywhere.
- Only Settings gets sunken inputs. Textareas skip `font: inherit`.
- `.profile-detail` overrides every panel's size and colour.
- `--color-bg-card` is used but never defined.
- Every panel prefix (`memory-`, `actions-`, `agents-`, `extensions-`, `settings-`) re-declares the same section, facts, status, notice, error and help rules with different values. For example, errors are amber in Memory and red elsewhere.

**Panel behaviour (`desktop/src/components/*.js`)**
- `appendText`, `labeledValue`, `errorMessage`, `isConflict`, `formatValue`, disclosures, buttons and fields are each copied 3–4 times.
- Memory, Settings and Providers re-render without keeping drafts. Settings and Providers can throw away unsaved edits.
- About 10 destructive actions have no confirmation.
- Wording drifts: Deny vs Decline, Delete vs Remove, three meanings of "Cancel", Completed vs succeeded.
- Raw enums, ISO times and ids appear in the open in Memory, Extensions and the shell status widgets.

**Channels and interfaces (backend + shell)**
- An approval-required action raised in a text or voice turn is held only in `TurnEngine._pending_tool` (`backend/app/conversation/engine.py:1057`). The operator is asked in chat text. The request never reaches `CapabilityService._pending`, so it doesn't appear in the Actions or Agents inbox, and the next unrelated turn silently cancels it.
- Only `execution_result` records from turns reach the capability audit.
- Agent-handoff replies carry no agent name.
- Turns made over HTTP or the inbound ACP bridge (`acp_server.py:204`) never appear in the desktop conversation.
- There is no history API, so the desktop log is lost on reload.

**Your scope decisions**
- UI plus backend continuity, owned by a new ADR 0014.
- Refine the current dark look; no light theme.
- The CLI (`scripts/run_jarvis.py`) is out of scope.

**Intended outcome:** one visual language and one vocabulary across the shell and all six panels. Every turn and approval appears in the conversation and the panels whichever channel (text, PTT, wake, hands-free, handoff) or interface (desktop, HTTP, ACP bridge) produced it, and the conversation survives a reload.

## Approach

### 1. Design tokens and base styles (`desktop/src/style.css`)
- **Tokens:**
  - Type scale: xs .75rem, sm .8125rem, md .875rem, lg 1rem, xl 1.25rem. Nothing below 12px.
  - Weights 400/600/700; line-heights tight 1.25, base 1.45.
  - Spacing 4/8/12/16/24/32.
  - Radius sm/md/lg; border width.
  - Focus ring: 2px accent plus offset.
  - Motion: 120ms, disabled under `prefers-reduced-motion`.
  - Define `--color-bg-card`, and add `--color-accent-hover` and `--color-danger`.
  - Replace the 10 raw font sizes, the 7 raw line-heights, the duplicated column template, and the extensions-list magic calc with tokens or shared variables.
- **Controls:**
  - Buttons get `.btn` variants: primary (default), secondary (`.btn-secondary`: elevated surface, border), danger (`.btn-danger`) and ghost (`.btn-ghost`, for row actions), each with hover, active, focus-visible and disabled states.
  - One sunken style for `input`, `select` and `textarea`, with `font: inherit` everywhere.
  - Checkbox and radio controls get `accent-color`.
- **Headings:** panel h2 xl, h3 lg, h4 md/600. h5 is not used.
- Remove the `.profile-detail` override for the Advanced Controls mounts.
- **Contrast:**
  - Turn-rail labels go to xs at readable opacity.
  - The failed badge uses inverse text.
  - Drop sub-11px text.
- Fix the 820px breakpoint so the header collapses too.

### 2. Shared UI primitives (new `desktop/src/components/ui/`)
The primitives are extracted from the existing copies, not written fresh.

- **`ui/dom.js`:** `appendText`, `el`, `option`, `button({variant, focusKey, onClick})`, `buttonRow`, `field(label, control, {help})` (from agents `formField` and extensions `labeled`), `details(facts, raw)` (from `detailsDisclosure`), `facts(entries)` / `labeledValue`, `processFields` (moved from `extensions-panel.js`).
- **`ui/format.js`:**
  - `errorMessage` and `isConflict`, also used by `main.js` and Providers in place of `String(error)`.
  - `formatTime(value, {timeOnly})`.
  - `humanize(enum, map)`.
  - One `STATUS_TEXT` / `statusState` map for activity, readiness and run statuses. It merges the mappers in actions `STATUS_TEXT`, agents `agentRunActivityState`, and `statusKind` in resident-voice, wake and service-status.
- **`ui/vocabulary.js`** — one glossary used by every panel and the conversation:
  - Approve / Decline
  - Cancel run (runs only)
  - Discard (close an editor or add form)
  - Delete (operator-owned profiles and definitions)
  - Enable / Disable
  - "Action" is the operator word; "capability" appears only inside Details.
  - The rail labels match each panel's h2.
- **`ui/panel.js`:**
  - `renderPanelHeader(title)`.
  - `messageRegion({notice, error})`: aria-live, with separate notice (accent) and error (danger) channels. Validation errors move off the notice channel.
  - `sectionState({loading, error, empty})`: one set of loading, empty and unavailable wording.
  - `createPanelLifecycle(container, controller, render, {poll, onClose})`: wraps `createRenderStateKeeper` (`render-state.js`), focuses the h2, and runs a focus-guarded poll. The poll only runs while live work exists; Extensions currently re-renders every second.
- **`ui/confirm.js`:** `confirmDestructive(message)` (one `window.confirm` wrapper), injected through options. Applied to:
  - agent delete and cancel run
  - extension retire, remove, forget authorization and cancel run (its prompt loses the raw id)
  - provider delete and rotate key
  - the existing memory forget and action cancel

### 3. Panel migration (every panel reuses §1–2 and gets generic CSS classes)
- **Generic classes** replace the per-prefix copies: `.panel-header`, `.panel-section`, `.panel-facts`, `.panel-list`, `.panel-row[aria-pressed]`, `.panel-help`, `.panel-notice`, `.panel-error`, `.panel-buttons`, `.status-badge[data-state]`, `.audit-steps`. Keep the layout classes the tests use (`extensions-panel-layout`/`-list`/`-detail`, `.agents-panel`).
- **Memory, Settings and Providers** move to `createPanelLifecycle`, so drafts, scroll and focus survive refreshes.
  - Settings stops re-rendering from stale `loadedFields`.
  - Providers keeps unsaved profile edits across selection saves.
  - Settings gets real `<label>` wrapping.
  - Remove Settings' in-panel Close button; the dialog already has one.
- **Readable text everywhere:** Memory's kind, authority and lifecycle values, ISO times and fact ids; the Extensions detail enums; the Providers test status; resident-voice and wake boolean rows; and "BOOTSTRAP". Raw ids stay inside Details.
- **Agents:**
  - Add 409 conflict handling.
  - The pending-approvals list is scoped to the selected agent.
  - Editor fields get draft and focus keys.
- **Extensions:** `decide` and `cancel` show failures. `run-request.js` stops writing `extensions-*` classes into Agents.

### 4. Backend continuity (ADR 0002, 0005 and 0007 boundaries; APIs are additive only)
- **Turn origin:**
  - `TurnEngine.run_text_turn(text, origin="api")` and `_create_context` record `origin` in a new `TurnArtifact.origin` field (`desktop`, `api`, `acp`, `voice`, `panel`).
  - `TextTurnRequest` gains an optional `origin`; the desktop sends `desktop`.
  - The ACP bridge passes `acp`. Voice turns record `voice`.
- **Agent attribution:** turn artifacts and `TextTurnResponse` carry `agent: {profile_id, display_name} | null`, taken from the active handoff or route (`engine.py:1432` `agent_route`, `session_service.py:231` `active_agent`).
- **History:** `GET /session/turns?after=<turn_id>&limit=` reads `SessionManager.turn_artifacts`. It returns `{turn_id, origin, input_modality, transcript, response_text, agent, final_state, failure_reason, started_at, actions: [{proposal_id, capability_id, status}], pending_approval}`.
  - Add a matching Tauri command in `lib.rs`/`backend.rs` and an `apiClient` method.
  - `shell.test.mjs` guards command and route parity.
- **One approval inbox:**
  - When a turn raises `approval_required` (`engine.py:1042`), the engine also registers it with `CapabilityService` through a new `register_turn_approval(proposal, approval_id, settle)`. The proposal is stored with `origin="conversation"` and a settle callback. It now appears in `/actions/pending` and in `SessionStatusResponse.pending_approval`.
  - `CapabilityService.decide`/`cancel` on a conversation-origin proposal call the engine's new `settle_pending_tool(outcome, decided_by="operator")`. That runs an admitted text turn with origin `panel`, reusing the `_resolve_pending_tool` approve and decline branches. The decision and its result then appear in the conversation, the audit and the Actions panel alike.
  - A turn-boundary cancellation and a yes/no answered by text or voice both remove the shared pending entry.
- **Complete audit:** the engine's turn proposal, authorization-decision, approval and cancellation records are also written with `CapabilityService._record`, so turn-initiated actions show full timelines in Actions and Agents.

### 5. Shell conversation continuity (`desktop/src/main.js`, `resident-voice.js`, new `components/conversation.js`)
- **One source of truth:**
  - The conversation log becomes a projection of `/session/turns`.
  - Load history at startup.
  - When `turn_count` changes, fetch turns after the last rendered turn and dedupe by `turn_id`.
  - Local text turns render immediately and are reconciled by `turn_id`.
  - The voice-only completion path in `appendResidentVoiceCompletion` goes through the same renderer. Turns from HTTP and ACP clients appear with an origin tag.
- **Each turn card shows:**
  - the speaker (the agent's name during a handoff, otherwise the personality name)
  - an origin and modality chip
  - the time via `formatTime`
  - action and agent-run chips that open the matching Advanced Controls category focused on that proposal. This needs an `openAdvancedCategory(id, {focus})` hook in `main.js` plus a `controller.selectProposal` or `selectAgent` call.
- **Pending approval card:**
  - While `pending_approval` is set, the conversation shows an approval card with Approve and Decline, using the same wording as the panels.
  - A decision made anywhere — card, Actions, Agents, or a yes/no reply — clears it everywhere.
- The handoff header ("Talking to X") links to the agent in Agents.

### 6. ADR 0014 and ADR updates
- **New `docs/adr/0014-unified-operator-experience.md`** (follows `0000-adr-template.md`; Related: 0002, 0005, 0007, 0008, 0013). It records the decision:
  - tokens and components
  - the vocabulary
  - the continuity contract: turn origin, history API, one approval inbox, agent attribution
- **ADR 0008:**
  - It keeps native validation ownership.
  - Its Extensions/Actions/Agents surface text defers visual and vocabulary rules to 0014.
  - The model-proposed approval follow-up becomes achievable through the shared inbox.
- **ADR 0013:** the inbound bridge's turns now carry origin `acp` and are visible to the operator.

## Critical files
- **Modified:**
  - `desktop/src/style.css`, `desktop/src/index.html` (rail labels), `desktop/src/main.js`
  - `desktop/src/components/{memory-panel,settings-panel,llm-provider-settings,appearance-controls,actions-panel,agents-panel,extensions-panel,run-request,resident-voice,wake-indicator,service-status,readiness-panel,desktop-state}.js`
  - `desktop/src/api-client.js`, `desktop/src-tauri/src/{lib,backend}.rs`
  - `backend/app/conversation/engine.py`, `backend/app/artifacts/turn_artifact.py`, `backend/app/services/capability_service.py`, `backend/app/services/session_service.py`
  - `backend/app/api/routes/{task,session}.py`, `backend/app/api/schemas/{task,session}.py`, `backend/app/extensions/acp_server.py`
- **New:**
  - `desktop/src/components/ui/{dom,format,vocabulary,panel,confirm}.js`
  - `desktop/src/components/conversation.js`
  - `docs/adr/0014-unified-operator-experience.md`

## Tests (extend nearest existing files; no new test files)
- **`desktop/tests/layout.test.mjs`**, as a CSS contract:
  - no raw font sizes below the token floor
  - every `var(--*)` used is defined
  - button variants and focus-visible exist
- **`actions`/`agents`/`extensions`/`memory`/`settings.test.mjs`:**
  - the shared vocabulary is used (Decline everywhere)
  - destructive actions call the injected confirm
  - Memory, Settings and Providers keep drafts across a refresh
  - Agents shows 409 conflicts
- **`app.test.mjs`:**
  - history loads at startup
  - an ACP-origin turn appears with its origin chip
  - the approval card approves and clears from both the card and Actions
  - an action chip opens Actions with that proposal selected
- **`shell.test.mjs`:** the new command and route pair.
- **Backend:**
  - `tests/unit/services/test_capability_service.py`: conversation-origin approvals are registered and settled; full audit timeline.
  - The turn/engine tests: origin is recorded; a turn-boundary cancel clears the shared pending entry; agent attribution.
  - `tests/unit/api/`: `/session/turns` pagination.
  - `tests/integration/test_extension_runtime.py` or the nearest engine integration test: a panel decision runs the pending tool and yields a `panel`-origin turn.

## Verification
1. Inner loop: `npm --prefix desktop test`, plus focused `pytest` on the changed backend tests.
2. Closeout:
   - `backend/.venv/Scripts/python scripts/validate_desktop.py regression`
   - `backend/.venv/Scripts/python scripts/validate_backend.py unit`
   - `backend/.venv/Scripts/python scripts/validate_backend.py integration`
3. Native pass (computer-use against the `npm --prefix desktop run dev` window, attaching to `jarvisv7-desktop.exe` without `open_application`):
   - visual consistency of the shell plus all six panels
   - a model-proposed approval from a text turn, decided from the conversation card and then from Actions
   - a turn sent via `curl` to `/task/text` appearing in the desktop
   - an agent handoff reply attributed by name
   - reload keeps the conversation
   - Results go in `reports/validation/<ts>-native_desktop.txt`, on host windows-amd64.
