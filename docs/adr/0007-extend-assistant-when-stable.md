# 0007 - Extend Assistant When Stable

Date: 2026-09-01
Status: Accepted
Related: 0002, 0003, 0004, 0005, 0006, 0008

## Context and Problem Statement

JARVISv7 should become agent-capable only after the underlying assistant is dependable enough to host delegation. Agents add role-scoped reasoning, specialized context, multi-step execution, and separate process boundaries; those features amplify weaknesses in turn ownership, memory, approvals, artifacts, and runtime readiness.

The current codebase implements major prerequisites: one committed turn engine, resident voice delegation into that engine, prompt authority boundaries, retrieval-backed memory, turn/session artifacts, provider profiles, search evidence, settings surfaces, diagnostics, action-governance records, file-backed agent profiles, direct agent invocation, agent API routes, and a desktop agent panel. Operational agent management and protocol-complete delegated-agent behavior remain incomplete.

The architecture needs a stability gate: agent work can start in narrow slices, but it must not fork sessions, memory, approval, extension, or artifact behavior away from the assistant foundation.

This ADR owns agent identity, invocation modes, agent runtime adapters, and Agent Client Protocol behavior; ADR 0006 owns extension-family cataloging, lifecycle, runtime operations, and non-agent operator workflows.

## Decision Drivers

- Preserve ADR 0002's backend-owned interaction loop for direct and delegated work.
- Preserve ADR 0003's model/application boundary so agent output remains proposal until application code accepts it.
- Preserve ADR 0004's application-owned memory retrieval, write, curation, lifecycle, and artifacts.
- Depend on ADR 0005 capability governance before exposing privileged or external agent actions.
- Depend on ADR 0006 extension cataloging before agent profiles or runtime adapters reference extension-backed capabilities.
- Keep non-agent assistant use functional when all agent features are disabled.

## Decision Outcome

An agent is a role-scoped reasoning and delegation unit with a defined purpose, available capabilities, memory scope, permission boundary, invocation mode, and completion contract.

Agents use:
- the same session and turn ownership model
- the same prompt authority and untrusted-context rules
- the same memory retrieval and write boundaries
- the same extension registry and capability registry
- the same authorization, approval, cancellation, and artifact flow
- the same provider/profile readiness and cloud-escalation policy
- the same backend-owned status and client surfaces

Agents may be invoked directly by the user, selected by an application router, called as a tool by another agent, or reached through a handoff. Those are invocation modes. Authority comes from application policy and capability records.

Agent work starts only when the needed scope is stable:
- loop: text, voice, interruption, cancellation, failure, and recovery enter one backend-owned interaction loop
- mind: model output is parsed, validated, bounded, and treated as proposal until application code accepts it
- memory: retrieval, write, lifecycle, curation, and artifact ingestion are application-owned and inspectable
- action: capabilities have stable IDs, schemas, effect classes, authorization rules, timeouts, cancellation, typed results, and artifacts
- extension: skills, MCP, hooks, plugins, prompts, providers, and connectors register through one extension/capability model
- approval: model-proposed operations requiring authorization pause and resume the same turn/run; specific operator requests follow ADR 0005 without self-approval
- process: subprocess agents have explicit adapters, allowed roots, environment, credentials, timeouts, cancellation, output capture, and cleanup
- client: desktop, CLI/script, daemon, and future clients display agent status, approvals, outputs, failures, and artifacts without owning policy
- validation: unit and integration tests prove each gate before live agent claims are made

These gates are scoped. A read-only summarizer agent needs less than a privileged coding agent. Missing optional capabilities degrade or stay unavailable while ordinary assistant use remains available.

## Consequences

Positive:
- Agent work waits for foundations that can make it reliable and inspectable.
- Delegation can be added without forking sessions, memory, approvals, or artifacts.
- Agent runtime adapters can use ADR 0006 extension-backed capabilities without taking ownership of MCP, skills, plugins, or tools.
- Agent modes can scale from low-risk read-only work to approval-gated privileged work.

Negative:
- Broad agent functionality is intentionally delayed until registry, capability, approval, and client surfaces exist.
- Provider-native agent features may need wrapping before they fit v7's policy and artifact model.
- ACP v2 subprocess adapters require lifecycle, timeout, cancellation, output, and credential discipline.
- Agent profile design must stay small enough for a personal project while still preventing hidden authority.
- Delegation requires more evidence per turn/run.

## Implementation

This ADR is partially implemented. File-backed agents support direct invocation and inspection. The outbound ACP adapter supports persistent, conversation-scoped connections and negotiated resume. Profile management, other invocation modes, and full inbound/outbound ACP v2 conformance remain incomplete.

### Agent profiles and direct invocation

`backend/app/agents/schema.py` defines profile identity, purpose, instructions, invocation modes, capability IDs, memory scope, approval class, timeout, cancellation, output contract, and provider/model policy. Authority-bearing override fields are rejected. `AgentRegistry` reloads YAML profiles from `config/agents/` when files change and reports malformed profiles without disabling the rest of the catalog.

The registry exposes agent profiles through the extension catalog and `agent-invoke-{profile_id}` capability descriptors. Current in-process approval classes map `none` to local-read/allow and `standard` or `strict` to local-write/requires-approval. Only direct mode is currently reachable; profiles without it report misconfigured. `AgentRouter` and `invoke_as_tool` exist but are not connected to complete invocation workflows.

`backend/app/agents/invocation.py` delegates direct work to `TurnEngine.run_agent`, using the shared turn-admission, prompt, provider, and artifact path. Handler bindings in `backend/app/api/app.py` resolve the active session engine. ADR 0002 owns turn/session execution, ADR 0003 prompt authority, ADR 0004 memory boundaries, and ADR 0005 authorization and action evidence.

`backend/app/api/routes/agents.py` provides list, detail, invoke, run listing, and cancellation. `desktop/src/components/agents-panel.js` exposes catalog, invocation, run status, and cancellation through Tauri. Agent profile authoring remains file-based. Operator invocation still uses the generic proposal path and can park for self-approval; the shared authorization correction is tracked in ADR 0005.

### Outbound ACP

`backend/app/extensions/acp.py` consumes ADR 0006 adapter definitions and ADR 0005's shared `SessionManager`. Connection identity is `acp:{agent_id}:{host_session_id}`: prompts in one host conversation reuse the same agent process and protocol session; separate host conversations use separate connections. Definition edit/delete closes every connection for that agent through prefix matching.

An open connection holds its subprocess and SDK transport through an `AsyncExitStack`. Initialization and session creation or resume occur once per connection; subsequent work sends prompts. Event and permission callbacks bind before initialization/resume and again for each prompt, attributing replayed updates and new events to the current call.

A remembered protocol session ID can be resumed after process replacement when the agent advertises `sessionCapabilities.resume`. Missing support or a failed resume falls back to a new session. Remembered IDs are host-memory state; recovery across a JARVIS restart is not implemented. The SDK fixture requires the agent process to enable `use_unstable_protocol` for resume routing, so advertised capability alone does not establish real-agent compatibility.

Transport `ConnectionError` signals a dead resource for cleanup and eviction. Subsequent use can create a replacement; an uncertain prompt is not replayed automatically. ACP has a separate PID-based `_stop_process_tree` termination path, allowing forceful teardown to be retried when a prior close was unconfirmed. Shared coordination and confirmation semantics belong to ADR 0005.

ACP work enters `TurnEngine.run_extension` admission and records delegated-run evidence. Streamed updates, permission requests, cancellation, and results flow through host callbacks and extension run records. The implemented SDK flow does not yet establish full ACP v2 conformance, including distinct prompt acceptance and foreground completion.

### Inbound bridge and agent boundaries

`backend/app/extensions/acp_server.py` implements a persistent local JSON-RPC bridge over loopback TCP, with tracked sessions, limits, timeouts, and requests routed through `TurnEngine.run_text_turn`. `backend/app/api/routes/acp_server.py` exposes start, stop, status, and session listing. Its lifecycle is implemented; its handshake and message shapes still require ACP v2 alignment.

`backend/app/agents/session_mapping.py` maps session events into delegated-run artifacts. `backend/app/agents/mcp_filter.py` implements agent-scoped MCP connection/tool/resource/prompt filtering. `AgentIsolation` in `backend/app/actions/boundaries.py` provides environment scrubbing, credential reference tracking, output limits, and working-root containment. These are application-level controls, not kernel isolation.

## Confirmation

Implementation files are identified above. Focused coverage:

- `backend/tests/unit/agents/`: schemas, registry, direct invocation, router, session mapping, and MCP filtering.
- `backend/tests/unit/extensions/test_acp_bridge.py`: adapter callbacks, resume negotiation, and fallback behavior.
- `backend/tests/unit/extensions/test_acp_server.py`: local inbound bridge.
- `backend/tests/integration/test_acp_sdk.py`: real process/session reuse, separate host-conversation isolation, current-call callbacks, cancellation, dead-process eviction, and resume after process replacement. The resume fixture persists history and emits recovered content during resume, establishing content continuity rather than only matching session IDs.
- `backend/tests/integration/test_extension_runtime.py`: ACP turn admission, permission/input handling, and delegated-run persistence.
- `desktop/tests/static.test.mjs`: agent panel behavior.

Recorded validation:

- Windows-amd64: `backend\.venv\Scripts\python.exe scripts\validate_backend.py integration`: PASS, 46 passed, including real-process death and resume coverage.
- Windows-amd64: `backend\.venv\Scripts\python.exe -m pytest backend\tests\unit\extensions\test_acp_bridge.py`: PASS, 6 passed, including unsupported/failed resume fallback.
- Later integrated backend suite and desktop build/test evidence is recorded in ADR 0005.
- Linux-amd64 live backend validation demonstrated the built-in summarizer profile, a real model-backed direct response, persisted proposal/decision/execution evidence, and denial of a profile lacking direct mode.

These results establish the implemented adapter and controlled fixture behavior. They do not establish interoperability with every external agent or native operator interaction.

## Follow-up

- Add backend-owned agent profile create/update/delete, enable/disable, validation, conflict handling, persistence, and audit, with desktop controls using those APIs.
- Complete the agent identity/runtime split: profiles own role and scope; runtime adapters select internal TurnEngine execution or external ACP v2 execution.
- Ship disabled application ACP agent defaults for Antigravity, Claude Code, Codex, GitHub Copilot, and Qwen-capable execution, with operator overrides, installed-runtime discovery, setup, status, and unavailable reasons. Verify each real agent's resume routing and recovered conversation content.
- Complete outbound ACP v2 conformance: version/auth negotiation, distinct `session/list` and `session/close` operations, elicitation, and separate prompt acceptance/foreground completion in artifacts and status.
- Replace the inbound bridge's handshake/message shapes with ACP v2 session lifecycle, updates, permission/elicitation, cancellation, and absolute-path conventions.
- Wire `router_selected`, `as_tool`, and `handoff` paths with selection/fallback evidence, approval boundaries, cancellation, and artifacts. Make model-proposed agent invocation available through the assistant's governed capability path.
- Complete named desktop agent workflows for profile management, external connection/testing, invocation, cancellation, evidence, and permission/elicitation input.
- Validate profile mutation, all invocation modes, real ACP peers, cancellation, input handling, and run evidence before marking this ADR implemented. ADR 0008 owns native layout and interaction validation; live tests require actual model/provider/process availability.
