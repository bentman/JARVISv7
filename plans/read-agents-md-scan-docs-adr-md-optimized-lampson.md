# Plan: Close ADR 0007 (Extend Assistant When Stable)

## Context

ADR 0007 is `Accepted`. Agents defined in files can already be invoked directly, but five follow-up items keep the ADR open:

1. Backend-owned profile management
2. The split between agent identity and runtime
3. The remaining invocation modes
4. A typed `delegated_runs` record
5. Validation

This pass implements four of those pieces:

- Profile CRUD and enable/disable
- The internal/ACP runtime split
- `as_tool` invocation proposed by the model, alongside the existing `direct` mode
- A typed delegated-run record

`router_selected` and `handoff` stay in ADR 0007's decision and Follow-up for a later pass. ADR 0007 stays `Accepted`, with its sections updated to show what this pass completed.

What exists today:

- `TurnEngine.run_agent` (`backend/app/conversation/engine.py:230`) always takes the turn lock through `_admit_turn`. Called from inside a turn, it is refused. That is why `ExtensionRuntimeService.tool_catalog` (`backend/app/services/extension_runtime_service.py:976`) never offers agents or ACP operations to the model.
- `run_agent` treats `mode` as a label only. It ignores `operation.cancel`, and `prepare_close` cannot cancel it.
- `delegated_runs` has three different untyped shapes:
  - Agent runs: `{agent_id, mode, response}` at `engine.py:~262`
  - Extension/ACP runs: rows keyed by `extension_id`, from `engine.py:226`
  - `session_mapping.to_delegated_run()`, which nothing calls
- `AgentRouter`, `AgentInvoker.invoke_as_tool`, `mcp_filter` and `AgentIsolation` exist but no code path uses them.
- `config/agents/` is the only source of profiles. There is no write path.

## Scope notes

- `INVOCATION_MODES`, `AgentRouter` (`backend/app/agents/router.py`) and its test are not changed. The runtime still reports profiles that declare only `router_selected` or `handoff` as not reachable.
- No new ADR.
- **Scaffolds stay.** Code that has no caller yet is kept for later work, not removed. That covers `AgentRouter`, `AgentInvoker.invoke_as_tool`, `session_mapping.py` (ADR 0013), `mcp_filter.py` and `AgentIsolation`, together with their tests. This pass only connects callers to them.

## Step 2: Typed delegated-run record

- Add a frozen, slotted `DelegatedRunRecord` in `backend/app/actions/contracts.py`, following `ActionCancellationRecord`: validate in `__post_init__` and expose `to_dict()` through `_deep_asdict`.
  - Fields: `run_id`, `kind` (`agent` | `extension`), `target_id` (profile ID or extension ID), `runtime` (`internal` | `acp` | family), `mode` (optional), `status`, `session_id`, `turn_id`, `output`, `error`.
- Add a `delegated_runs` list to `ActionEvidence`, plus a sink entry in `_EVIDENCE_SINKS` (`contracts.py:~375`).
- `engine.py`: copy `delegated_runs` into the artifact the same way as the other evidence fields (`engine.py:~1472`).
  - Convert the extension-run rows (`engine.py:226`) and the agent path to this record.
- `session_mapping.py` is ADR 0013's scaffold and stays as it is. `DelegatedRunRecord` fields are chosen so `to_delegated_run()`'s keys can map onto the record when ADR 0013 wires it.
- Update the affected assertions:
  - `backend/tests/integration/test_extension_runtime.py:242` (`extension_id` becomes `target_id`)
  - `backend/tests/unit/artifacts/test_turn_artifact.py:202`, which has the comment "no record type yet"

## Step 3: Split identity and runtime

- `AgentProfile` gains an optional `runtime` mapping. It defaults to `{kind: internal}`; the other form is `{kind: acp, adapter_id: <ACP definition local id>}`. It is validated in `schema.py` and is not a required key, so `summarizer.yaml` stays valid.
- `AgentRegistry.to_capability_records` (`backend/app/agents/registry.py:95`):
  - The ACP runtime maps to `privileged_execution` / `requires_approval` whatever the `approval_class`. The existing comment at `registry.py:8` already anticipates this.
  - If the referenced ACP definition is missing or disabled, the agent is reported `unavailable` with a reason.
- Agent handler in `capability_service.py:1012` (`build_agent_handlers`):
  - Internal runtime dispatches to `TurnEngine`.
  - ACP runtime reuses the existing ACP extension execution path (`run_extension` + `backend/app/extensions/acp.py`), the same one `build_extension_handlers` uses. It is not authorized a second time.
  - The profile's instructions are sent as prompt context, and the result is recorded as a `DelegatedRunRecord` with `runtime="acp"`.
  - **Check during implementation:** how `build_extension_handlers` exposes ACP work so it can be called for a named adapter.

## Step 4: `as_tool` (model proposes the agent call inside a turn)

- **Refactor `TurnEngine.run_agent`:**
  - Split it into an admitted wrapper (`direct`: new turn, takes the lock) and an inner `_delegate_agent(context, profile, prompt, mode, operation)`.
  - The inner method builds the agent prompt envelope and makes one bounded generation, with no nested tool loop.
  - It checks `operation.cancel` before and after generation. It stores `self._agent_operation` so `prepare_close` (`engine.py:193`) cancels it, the same way `_extension_operation` is handled.
  - It appends a `DelegatedRunRecord` to `context.action_evidence`.
- **Choosing the mode inside the handler:**
  - If `operation.turn_id` matches the engine's active turn, run nested in that turn's context with mode `as_tool`.
  - Otherwise, admit a new turn with mode `direct`.
  - Either way, the profile must declare that mode. The handler calls the existing `AgentInvoker.invoke_direct` or `AgentInvoker.invoke_as_tool`, which gain an `operation` parameter. That puts `invoke_as_tool` to use without replacing it.
- **Offering agents to the model:** extend the tool-definition source (`engine.py:787` `_tool_definitions`) with agent capabilities that are all of:
  - declaring `as_tool`
  - enabled and available
  - using the internal runtime (ACP-runtime agents stay direct-only because `run_extension` needs the turn lock)

  Update the `tool_catalog` docstring to match.
- **Approval:** the existing ladder in `_run_selected_tool` / `_resolve_pending_tool` applies. `approval_class: none` runs; `standard` / `strict` go through the existing confirmation path. The agent's output comes back as untrusted tool context (ADR 0003).

## Step 5: Profile management

- **Storage:** `config/agents/` stays application-owned and read-only. Operator profiles go in `data/agents/*.yaml`.
  - `AgentRegistry` observes both directories. Application profiles win, and an ID collision is reported in `errors()` rather than raised.
  - The change signature covers both directories.
- **Writes:**
  - `AgentRegistry.write_profile(data, expected_fingerprint)` and `delete_profile(id, expected_fingerprint)` follow `ExtensionRuntimeService.write_definition` / `delete_definition` (`extension_runtime_service.py:478-578`).
  - Validate with `AgentProfile.from_dict`, which already rejects authority fields.
  - Refuse application IDs. Omitting the fingerprint means create-only; a stale fingerprint is a conflict.
  - Write through `write_text_atomic`, then refresh the registry and capability actions.
- **Audit:** routes wrap the writes in `CapabilityService.execute_operator_action` (`capability_service.py:543`), as `routes/config.py:48` does. That records proposal, decision and result without making profile edits a tool the model can propose.
- **Enable/disable:** agents are already the `agent` family in the extension catalog (`backend/app/extensions/catalog.py:77`). Reuse `ExtensionService.set_state` (overlay revision conflict + `extension_event` audit) and make disabled agents unavailable in the capability catalog.
  - No new state API. The desktop calls the existing extension state route.
- **Routes** (`backend/app/api/routes/agents.py` + `backend/app/api/schemas/agents.py`):
  - `POST /agents` (create), `PUT /agents/{id}` (update with `expected_fingerprint`), `DELETE /agents/{id}`.
  - Profile responses gain `source`, `editable`, `enabled`, `fingerprint`.
  - Load errors are listed on `GET /agents`.
- **Desktop:**
  - `desktop/src/api-client.js` (create/update/delete/state)
  - `desktop/src-tauri/src/backend.rs` + `lib.rs` commands
  - `desktop/src/components/agents-panel.js`: an edit form for operator profiles and an enable toggle; application profiles are read-only
  - Native interaction validation stays with ADR 0008.

## Step 6: Boundary scaffolds

- Nothing is removed.
- `AgentIsolation`: connect it to the ACP runtime's process boundary only if the ACP path does not already enforce the same roots and environment.
- `mcp_filter`: left untouched for later work.

## Tests (extend the nearest existing tests first)

- `backend/tests/unit/agents/test_agent_schema.py`: runtime field; rejected modes.
- `test_agent_registry.py`: both directories, application precedence/collision, write/delete conflicts, disabled → unavailable, ACP runtime effect class.
- `test_agent_invocation.py`: nested (as_tool) vs admitted (direct) selection, mode refused when not declared, cancellation.
- `backend/tests/unit/artifacts/test_turn_artifact.py`: typed record round-trip.
- `backend/tests/unit/conversation/test_tool_turn.py`: an agent offered as a tool, the approval path, and a delegated run recorded in the same turn artifact.
- `backend/tests/unit/services/test_capability_service.py`: internal vs ACP dispatch.
- Integration: extend `backend/tests/integration/api/test_headless_client.py` with profile CRUD → invoke → evidence through the API using the fake LLM. No integration test covers agents today.
- `desktop/tests/static.test.mjs`: panel CRUD/state wiring.

## Verification

```
backend/.venv/Scripts/python scripts/validate_backend.py unit
backend/.venv/Scripts/python scripts/validate_backend.py integration
backend/.venv/Scripts/python scripts/validate_desktop.py
```

- Report each run with host class `windows-amd64`.
- Live check against the running backend with a real provider:
  - create an operator profile
  - invoke it directly
  - have the assistant propose it as a tool in a text turn and approve it
  - confirm the typed `delegated_runs` entry in the turn artifact
  - check that a stale-fingerprint update is refused
- Then update ADR 0007 but keep Status `Accepted`:
  - Rewrite Implementation and Confirmation for profile management, the runtime split, `as_tool` and the typed record. Confirmation lists durable files and commands only.
  - Cut Follow-up down to the `router_selected` / `handoff` wiring (selection/fallback evidence, approval, cancellation, artifacts) and final validation of all modes.
  - Add the one-line ADR 0013 note that ACP runs record `DelegatedRunRecord`.
