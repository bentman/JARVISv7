# ADR 0008 Operator Experience — implementation plan

## Context

ADR 0008 is `Accepted` and marked partially implemented. The layout, Advanced Controls dialog, provider and settings fixes, and agent-panel remount are already done. It remains open because of seven follow-ups:

- three code gaps:
  - the Actions audit view is not readable by an operator;
  - the named agent workflows are incomplete;
  - draft, scroll and focus are not preserved across the shell;
- four native-validation obligations. ADR 0008 is the single owner of native operator validation for the repo.

Scope decisions from you:
- **Native evidence:** I drive the real Tauri window through computer-use.
- **ACP connection test:** status plus a test prompt, with no new backend route.
- **ACP scope:** a definition picker plus ACP definition CRUD. The inbound ACP server surface stays out; ADR 0013 still owns its v2 realignment.

Host: `windows-amd64`. No backend route changes. One Tauri command changes its signature (`invoke_agent`), and no Tauri command is added.

## Gaps found

**Actions panel** ([actions-panel.js](desktop/src/components/actions-panel.js)):
- Audit rows show `record.kind · capability_id` (≈652) and never show the nested record's outcome, decider, error or cancel reason.
- Pending rows and detail show proposal id, capability id, raw `JSON.stringify(arguments)` and raw ISO times in the open (≈528–534, 585–594).
- Descriptor problems are printed as `${capability_id}: ${reason}` (≈502).
- `degraded` and `unavailable` readiness get no text.
- Every emit runs `replaceChildren`, so focus and scroll are lost.

**Agents panel** ([agents-panel.js](desktop/src/components/agents-panel.js)):
- It ignores `AgentListResponse.problems`.
- The ACP adapter is a free-text field (≈757).
- There is no output or result display, no run detail, no permission/elicitation input, and no approve/decline.
- Cancel is disabled while `invoke` holds `mutationPending` (≈596), so an in-flight run cannot be cancelled.
- In `lib.rs:816`, `invoke_agent` is a synchronous Tauri command. An ACP agent waiting on a permission answer would therefore hold a blocking thread, the same issue `invoke_extension` already fixed.

**Extensions panel:** it has no ACP definition CRUD. Tool and MCP CRUD already exist; the ACP definition shape is `command` plus `process`, the same as a tool (`backend/app/extensions/acp.py:33`). The backend already validates `family: "acp"` through `extension-definition-write` (`extension_runtime_service.py:594`).

**Shell:** the only draft/scroll/focus preservation lives in `extensions-panel.js` `renderPanel` (≈2007–2072). It is not shared, and it is discarded when a category closes, because `closeActive` → `replaceChildren()`.

## Plan

### 1. Shared render-state preservation
- New `desktop/src/components/render-state.js`, extracted from the capture/restore code in `extensions-panel.js` `renderPanel`:
  - `captureRenderState(container)` returns `{drafts, scroll, focusKey}` from `[data-draft-key]`, `[data-scroll-key]` and `activeElement.dataset.focusKey`;
  - `restoreRenderState(container, snapshot)`.
- Extensions, Actions and Agents `renderPanel` wrap `replaceChildren` with these helpers.
- Each panel factory's `close()` stores a snapshot, and `open()` restores it on the first render. Drafts, scroll and focus then survive a category switch and a dialog reopen.
- Add `data-draft-key`, `data-scroll-key` and `data-focus-key` attributes to the actions and agents lists, detail sections, forms and buttons.

### 2. Operator-readable Actions audit and detail (`actions-panel.js`)
- Add a pure `describeAuditRecord(envelope)` with one sentence per kind:
  - `action_proposal`: "Requested by operator / proposed by assistant: <reason>"
  - `authorization_decision`: "Allowed", "Needs approval" or "Denied: <reason>"
  - `approval_record`: "Approved/Declined by <decided_by>"
  - `execution_result`: "Completed", "Failed: <error>", "Cancelled" or "Outcome unknown — effects may have happened"
  - `action_cancellation`: "Cancelled by <who>: <reason>"
- Each row shows a readable capability title (the catalog `title`/name, falling back to the id) and a localized time.
- Group audit rows by `proposal_id`, so one action reads as a timeline.
- Raw values go only inside an explicit `<details>Details</details>`: capability id, proposal id, approval id, the raw record JSON, and the `execution_owner` class path.
- Pending rows and `renderDetail`:
  - show the title, readable arguments (a key/value list), the reason and the expiry as a relative/local time;
  - show the execution summary as status, error and duration;
  - move ids and JSON into Details;
  - drop the raw id from the cancel confirm text.
- Descriptor problems get a "Could not load" heading, with the readable reason shown and the id kept in Details.
- `degraded` and `unavailable` readiness get explicit text.
- The generic runner (`renderProposeForm`) stays, labelled "Run manually (audit/fallback)".

### 3. Named agent workflows (`agents-panel.js`, `main.js`, `lib.rs`)
- `main.js` passes these additional handlers to the Agents mount, all of them existing apiClient methods:
  - `getExtensions` and `getExtensionRuntime`, for the ACP picker and status. If `getExtensionRuntime` has no apiClient method, add the missing apiClient wrapper around the existing `get_extension_runtime` Tauri command.
  - `getExtensionRuns`, `answerExtensionInput`, `decideAction` and `cancelAction`;
  - the extension invoke method that `extensions-panel` uses.
- **Profile management:**
  - Render `problems` as readable "could not load" entries.
  - Replace the free-text adapter field with a `<select>` of `acp` family extensions, showing each one's readiness.
- **External connection/testing:** the agent detail for an ACP runtime shows:
  - the linked definition's enabled state and readiness;
  - `connected` from runtime;
  - a **Test connection** button. It invokes `acp:<adapter_id>` `prompt` with a fixed short prompt through the existing extension invoke path, then shows the reply, or a readable failure or unavailable reason.
- **Invocation and cancellation:**
  - Split `mutationPending` into `invokePending` and `mutationPending`, so Cancel stays enabled during a run.
  - Cancel targets the specific run through `cancelAction(proposal_id)` once the run's proposal id is known. Before that it falls back to the existing `cancelAgent(profileId)`.
- **Evidence:**
  - Show `AgentInvokeResponse.output` or its error.
  - Add a run detail disclosure that uses `describeAuditRecord` from step 2, exported and shared.
  - Link the ACP extension run by `proposal_id`: its latest event, result, and raw events in Details.
- **Permission and elicitation input:**
  - While invoking, or while a linked extension run is `awaiting_input` or `awaiting_approval`, poll `getExtensionRuns` every second. This is the same pattern as `createExtensionsPanel`: skip while an input has focus, and clear on close.
  - Render the permission option select and elicitation fields by extracting and sharing the run-request renderer from `extensions-panel.js` (≈1880–1935), not by copying it. It moves to `render-state.js`'s sibling module, `desktop/src/components/run-request.js`.
- **Tauri:** make `invoke_agent` in `desktop/src-tauri/src/lib.rs` `async` with `tauri::async_runtime::spawn_blocking`, matching `invoke_extension` (≈746–762). Give the request in `backend.rs`'s `invoke_agent` a timeout that covers the profile's maximum `timeout_ms` (600 s) plus margin.

### 4. ACP definition CRUD (`extensions-panel.js`)
- Add ACP Add/Edit/Remove by generalizing the local-tool functions (≈735–830):
  - `addLocalTool`, `updateLocalTool` and `removeLocalTool` become family-parameterized (`"tool"` or `"acp"`), with the `toolDefinition` builder shared;
  - the ACP definition omits the tool-only `skill_id` and `script`.
- Show the form in the ACP family view, guarded by operator provenance like tools.
- Keep the fingerprint on edit. Transport stays fixed.

### 5. Tests (extend existing files; no new test files)
- `actions.test.mjs`:
  - parameterize `describeAuditRecord` over the five kinds, including failure, `outcome_unknown` and cancellation;
  - rendered-DOM assertion that raw capability, proposal and approval ids appear only inside `details`;
  - update the existing assertions at ≈79–86 that currently require the raw id and `execution_owner` in the open.
- `agents.test.mjs`:
  - `problems` rendered;
  - ACP picker populated from extensions;
  - Cancel enabled during invoke and targeting `cancelAction(proposal_id)`;
  - permission answer routed through `answerExtensionInput`;
  - Test connection success and failure.
- `extensions.test.mjs`: extend the local-tool CRUD test to cover `family: "acp"`, and keep the existing preservation tests passing against the extracted helper.
- `app.test.mjs`: extend the Advanced Controls test so that a draft typed in Actions, plus the scroll position, survive switching to Agents and back, and survive closing and reopening the dialog.
- `shell.test.mjs`: run unchanged. It still guards command/route parity.
- Rust: `cargo test` covers the `invoke_agent` signature through the existing build.

### 6. Native validation (computer-use on the real Tauri window)
- Start the backend and desktop through the existing path (`npm --prefix desktop run dev`, which launches the backend through `desktop/src-tauri/src/backend.rs`).
- Drive the window with computer-use screenshots and clicks through the ADR 0008 Follow-up list:
  - right-sidebar fit, selector font size and compact Personality;
  - Advanced dialog sizing, single Close, Escape, backdrop click and focus return;
  - the Extensions list/detail split;
  - the provider-profile smoke test: create an `openai_compatible` profile with endpoint, model, context window, timeout and credential; check that it stays selected; force a readable validation error;
  - category switching, retention, and draft/scroll preservation;
  - action direct execution, a model-proposal approval, cancellation and audit detail;
  - extension invoke, elicitation, input answer, cancel, Disconnect and `outcome_unknown` recovery, as fixtures allow;
  - agent create/edit/test/invoke/cancel and the permission prompt.
- Credentials: use test values only. Generate them and record them in `.env`, not in chat.
- Record the observations in `reports/validation/<ts>-native_desktop.txt`, which is gitignored like the other reports.
- Any item that cannot be exercised on this host (for example, no ACP agent binary is installed) is reported as `SKIPPED` with the reason. It is not closed.

### 7. ADR update (`docs/adr/0008-operator-experience.md`, re-read from disk first)
- Update Implementation: the render-state helper, audit presentation, agent workflows, ACP CRUD, and the `invoke_agent` async change. Replace the sentence "no Tauri command change" accordingly.
- Update Confirmation with the new files and the test names they cover.
- Remove each satisfied Follow-up item.
- Set Status to `Implemented` only if every native item has evidence; otherwise keep only the unexercised items in Follow-up.

## Files
- Modified:
  - `desktop/src/components/actions-panel.js`, `agents-panel.js` and `extensions-panel.js`;
  - `desktop/src/main.js`, and `desktop/src/api-client.js` only if a wrapper is missing;
  - `desktop/src-tauri/src/lib.rs` and `desktop/src-tauri/src/backend.rs`;
  - `desktop/tests/{actions,agents,extensions,app}.test.mjs`;
  - `docs/adr/0008-operator-experience.md`.
- New:
  - `desktop/src/components/render-state.js`;
  - `desktop/src/components/run-request.js`, which holds the run-request renderer extracted from extensions-panel.

## Verification
1. Inner loop: `npm --prefix desktop test`
2. Closeout: `backend/.venv/Scripts/python scripts/validate_desktop.py regression` (npm tests and cargo tests), expected exit 0, with the report in `reports/validation/`
3. `backend/.venv/Scripts/python scripts/validate_backend.py unit` is needed only if a backend file changes. None is planned.
4. Native: the computer-use session from step 6, with its report path cited in the closeout message. For each item, the result is PASS, FAIL or SKIPPED, with the host class `windows-amd64`.
