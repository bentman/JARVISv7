# Plan: Close ADR 0007's remaining follow-up (router_selected, handoff, live as_tool)

## Context

ADR 0007 has three open follow-up items:
1. Wire `router_selected` and `handoff` with selection/fallback evidence, approval boundaries, cancellation, and artifacts.
2. Demonstrate live model-proposed `as_tool` execution.
3. Validate every invocation mode, then mark the ADR `Implemented`.

Your decisions:
- **Router:** routes only when the user addresses an agent by name.
- **Handoff:** the user starts it and ends it with a phrase; an agent that needs approval asks "Reply yes to confirm" first.
- **Live `as_tool`:** diagnose why the local Qwen3-8B (llama.cpp) answered in text instead of calling the tool it was offered, fix whatever is on the app side, and re-run the check.

What exists today:
- `AgentRouter` (`backend/app/agents/router.py`) matches any purpose word longer than two letters, so it would route almost every turn.
- `AgentInvoker` has `invoke_direct` and `invoke_as_tool`.
- The capability handler in `build_agent_handlers` (`backend/app/services/capability_service.py`) treats every call from inside a turn as `as_tool`.
- Text and voice turns share the same path from `_run_reasoning_path` onward (`backend/app/conversation/engine.py`). Engine state is per session, because `SessionService.start_session` rebuilds the engine.
- `_pending_tool` with `CONFIRM_REPLY`/`CANCEL_REPLY` (`backend/app/cognition/search_policy.py`) is the existing pattern for asking before acting.

## Step 1: Name-addressed router (reuses the `AgentRouter` scaffold)

Rewrite `backend/app/agents/router.py`. It stays pure and deterministic, with no model call.

- **Eligible agents:** profiles that are enabled, available, use the internal runtime, and declare the mode. ACP-runtime agents stay direct-only, because `run_extension` needs the turn lock.
- **Names:** an agent is addressed by `display_name` or by `profile_id` with hyphens read as spaces. Matching is case-insensitive and on word boundaries.
- **`route(text) -> AgentRoute | None`** recognises these address forms:
  - `"<name>, <task>"` or `"<name>: <task>"`
  - `"hey <name> <task>"`
  - `"ask <name> to <task>"`
  - `"@<id> <task>"`

  It returns the profile and the remaining task text. When the name belongs to an agent that is disabled, uses the ACP runtime, or lacks `router_selected`, it returns a route carrying the reason.
- **`handoff_request(text)`** recognises "hand me over to / hand off to / talk to / switch to `<name>`".
- **`ends_handoff(text)`** recognises "back to JARVIS", "end handoff", and "stop handoff".
- Replace the keyword tests in `backend/tests/unit/agents/test_agent_router.py`. Also delete the keyword matcher itself, since this work replaces it.

## Step 2: One way to invoke, with the mode chosen by the engine

- `AgentInvoker` gets a single `invoke(profile_id, prompt, mode, engine_getter, operation)` that checks the profile declares the mode. It replaces `invoke_direct` and `invoke_as_tool`, so those two are removed and their tests updated.
- `TurnEngine` records which mode it is delegating in: `_delegation_mode`, set to `as_tool`, `router_selected`, or `handoff` by the path that starts the delegation.
- `engine.in_turn_mode(turn_id)` returns that mode for the active turn, or `None`. The handler in `build_agent_handlers` uses it instead of assuming `as_tool`; any call from outside a turn stays `direct`. `run_agent` checks that an in-turn mode really is running inside the active turn.

## Step 3: `router_selected` in the turn

In `_generate_response`, check the steps below in order. All of them come after `_resolve_pending_tool` and apply only when no search operation is open:
1. Pending handoff confirmation (Step 4).
2. Active handoff (Step 4).
3. Handoff request (Step 4).
4. Router address, handled like this:
   - The router proposes `agent-invoke-{id}` with `proposed_by="router"` and the task as `prompt`, and authorizes it with `authorize_turn`.
   - **Allowed:** set the mode to `router_selected` and run it through the existing `_execute_tool`. The agent's `output.response` becomes the turn's response and goes through the normal bounding, style guard, TTS, and artifact steps.
   - **Approval required:** reuse `PendingToolApproval`. The prompt reads "May I hand this to `<Agent>`? Reply yes to confirm.", and yes, no, and lapse behave as they do for tools today.
   - **Evidence:** `context.runtime_context["agent_route"] = {outcome, profile_id, reason}`, where outcome is `selected`, `awaiting_approval`, `denied`, `unavailable`, `failed`, or `fallback`. The field is written only when an address matched, so ordinary turns carry no noise.
   - **Fallback:** if the agent is unavailable, denied, or fails, the normal assistant path answers the turn and the reason is recorded.

## Step 4: `handoff` (the agent owns the following turns)

- **State:** `TurnEngine._handoff: ActiveHandoff | None` holds `profile_id`, `approval_id`, and `started_turn_id`, alongside `_pending_handoff`. Because both live on the engine, they end automatically when the session closes or a new one starts.
- **Start:**
  - `handoff_request` matches a profile that declares `handoff`.
  - The profile's descriptor is authorized through the capability ladder.
  - If the rule is `allow`, the handoff starts immediately. If it is `requires_approval`, the engine asks and sets `_pending_handoff`, and yes, no, or lapse resolve it the way `_resolve_pending_tool` does.
  - The turn replies "You're now talking to `<Agent>`. Say 'back to JARVIS' to return."
- **While active:** each turn proposes `agent-invoke-{id}` with the transcript as `prompt`. Mode is `handoff`, and the confirmed handoff's `approval_id` carries `operator_approved`. The agent's response is the turn's response, and each turn records its proposal, decision, execution, and a `DelegatedRunRecord` with mode `handoff`. `_run_reasoning_path` does not open a search operation while a handoff is active.
- **End:** any of these ends the handoff:
  - an end phrase
  - `POST /session/handoff/end`, a new route in `backend/app/api/routes/session.py` that calls `engine.end_handoff()`
  - session close
  - the agent becoming unavailable (disabled, deleted, or misconfigured), which ends the handoff, falls back for that turn, and says why

  Start and end events are recorded in `runtime_context["agent_handoff"]`.
- **Cancellation:** a handoff turn runs through the operation path, so `prepare_close` and the deadline cancel it through the existing `_agent_operation` hook.
- **Status:**
  - `SessionService.status()` adds `active_agent` (`{profile_id, display_name}` or `None`), following the `active_search` pattern, and `SessionStatusResponse` (`backend/app/api/schemas/session.py`) gains the field.
  - The desktop main status shows "Talking to `<Agent>`" with an End button, calling the new route through `desktop/src/api-client.js` and new Tauri commands in `desktop/src-tauri/src/backend.rs` and `lib.rs`.

## Step 5: Diagnose live `as_tool` on the local model

1. Capture the raw llama.cpp request and response for a tool-offered turn. The capture runs locally with debug logging and is not committed. Check:
   - Does the `content` hold Qwen `<tool_call>` text that was never parsed?
   - Is `<think>` output using up the personality's `max_tokens: 120`?
   - Do the stop strings (`\nUser:`, `\nAssistant:`) cut generation short?
   - Does the chat template actually carry the tool section?
2. Fix only what is on the app side, in `backend/app/runtimes/llm/local_runtime.py` (`generate_with_tools`) or `backend/app/cognition/tool_policy.py`. Examples: a token allowance for tool turns, parsing tool-call text, or clearer tool descriptions. Add a runtime test using the existing `test_llm_runtime.py` monkeypatch pattern for whichever failure mode is confirmed.
3. If the cause is the model itself and not the app, record that honestly and do not add workarounds.

## Step 6: Cleanup and ADR closeout

- Remove the scaffolds this work replaces: the keyword router logic and `invoke_direct`/`invoke_as_tool`.
- `mcp_filter.py`: once this pass lands, no remaining ADR 0007 work consumes it, because agents run no MCP tool loop. Remove it, its test, and its ADR mention, since agent-scoped MCP access would be a new decision. Tell me on plan review if you want it kept.
- ADR 0007:
  - Rewrite Implementation and Confirmation to cover router, handoff, the mode selection, and the as_tool diagnosis outcome, citing durable files and commands only.
  - Record that ACP-runtime agents are reachable in `direct` only.
  - Set Status to `Implemented` only if every mode has passing evidence; otherwise keep `Accepted` and list exactly what is missing.

## Tests (extend the nearest existing tests)

- `backend/tests/unit/agents/test_agent_router.py`: the address forms, word boundaries, ineligible-agent reasons, and handoff start/end phrases.
- `backend/tests/unit/agents/test_agent_invocation.py`: `invoke(mode)` refuses a mode the profile does not declare.
- `backend/tests/unit/conversation/test_tool_turn.py`, reusing the `_agent_engine` helper:
  - a routed turn answered by the agent
  - approval-gated routing: asks first, runs on yes
  - fallback evidence when the agent is disabled
  - handoff: start (allow and approval-gated), turns routed to the agent, end phrase, auto-end on disable, and no search while active
- `backend/tests/unit/services/test_capability_service.py`: the handler takes the mode from `in_turn_mode`.
- `backend/tests/integration/api/test_headless_client.py`: start a handoff through `/task/text`, check `/session/status` shows `active_agent`, end it through `POST /session/handoff/end`, and confirm the artifacts carry mode `handoff`.
- `desktop/tests/static.test.mjs`: the active-agent status and End action.

## Verification

```
backend/.venv/Scripts/python scripts/validate_backend.py unit
backend/.venv/Scripts/python scripts/validate_backend.py integration
backend/.venv/Scripts/python scripts/validate_desktop.py regression
cargo check --manifest-path desktop/src-tauri/Cargo.toml
```

Report each run with host class `windows-amd64`.

Live check against a running backend with the local model. Router and handoff do not depend on the model calling tools, so all of these should work locally:
- **Text:** a name-addressed request ("Notes, tidy these…"), a handoff start, two handed-off turns, and "back to JARVIS". Inspect `agent_route`, `agent_handoff`, and `delegated_runs` in `data/turns/…`.
- **Voice:** one name-addressed turn through the resident voice path, confirming the same evidence.
- **`as_tool`:** re-run after the Step 5 fix.
- **Cleanup:** delete the test profile through the API and stop the backend.
