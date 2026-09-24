# 0007 - Extend Assistant When Stable

Date: 2026-09-01
Status: Implemented
Related: 0002, 0003, 0004, 0005, 0006, 0008, 0013

## Context and Problem Statement

JARVISv7 should become agent-capable only after the underlying assistant is dependable enough to host delegation. Agents add role-scoped reasoning, specialized context, multi-step execution, and separate process boundaries; those features amplify weaknesses in turn ownership, memory, approvals, artifacts, and runtime readiness.

The current codebase implements major prerequisites: one committed turn engine, resident voice delegation into that engine, prompt authority boundaries, retrieval-backed memory, turn/session artifacts, provider profiles, search evidence, settings surfaces, diagnostics, action-governance records, file-backed agent profiles, agent API routes, and a desktop agent panel. Protocol-complete delegated-agent behavior is ADR 0013's.

The architecture needs a stability gate: agent work can start in narrow slices, but it must not fork sessions, memory, approval, extension, or artifact behavior away from the assistant foundation.

This ADR owns agent identity, invocation modes, and agent scope boundaries. ADR 0013 owns Agent Client Protocol adapter behavior; ADR 0006 owns extension-family cataloging, lifecycle, runtime operations, and non-agent operator workflows.

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
- Agents that execute in an external runtime depend on ADR 0013 adapter conformance, which is a separate and longer-running effort.
- Agent profile design must stay small enough for a personal project while still preventing hidden authority.
- Delegation requires more evidence per turn/run.

## Implementation

Agent profiles are managed through backend APIs and the desktop Agents panel, select an internal or ACP runtime, and are reachable in all four invocation modes with typed delegated-run evidence. An agent reads only the memory its scope allows and uses only the capabilities its profile allows.

### Agent profiles and management

`backend/app/agents/schema.py` defines profile identity, purpose, instructions, invocation modes, capability IDs, memory scope, approval class, timeout, cancellation, output contract, provider/model policy, and runtime. Authority-bearing override fields are rejected.

`AgentRegistry` observes application profiles in `config/agents/` and operator profiles in `data/agents/`. It reloads when files change and reports malformed or colliding profiles without disabling the rest of the catalog. Application profiles keep their IDs and are read-only.

- **Writes:** operator profiles are validated before they are written atomically. A create refuses an existing ID; an update or delete must match the content fingerprint that was read.
- **Routes:** `backend/app/api/routes/agents.py` exposes create, update, and delete, each wrapped in the governed `agent-profile-write` / `agent-profile-delete` operator actions so every change is audited.
- **Enable/disable:** this uses the extension overlay for `agent:{profile_id}`. A disabled agent is served as a disabled capability.
- **Desktop:** `desktop/src/components/agents-panel.js` creates and edits operator profiles through a form that describes invocation modes, approval, memory, allowed tools, time limit, and runtime in operator language, and duplicates a built-in profile into an editable operator profile. Fields the form does not show are carried over unchanged.

### Memory and tools

`TurnEngine` applies an internal agent's profile scope on every run:

- **Memory:** `memory_scope` chooses which layers the agent reads: `none`, `working` (this conversation), `episodic` (plus past conversations), `semantic` (plus known facts), or `full`. Retrieval reuses the assistant's retrieval over only those layers, and `runtime_context.agent_memory` records the scope and what was retrieved. Agents read memory and never write it; what a turn teaches is retained only through the host turn's own write path, so retention stays under the operator's ADR 0004 memory policy.
- **Tools:** `capability_ids` allows the agent a subset of the capabilities the assistant's model may use (`ExtensionRuntimeService.tool_catalog`). `GET /agents/tools` lists them for the profile form. The agent proposes one capability per run as `agent:{profile_id}`, and the ADR 0005 ladder governs it. An allowed capability runs and the agent answers from its result. One that requires approval pauses the agent: in a conversation, JARVIS asks the user, and the next turn's confirmation runs the capability and resumes the agent with its result, while a decline or a lapse at the turn boundary runs nothing. A `direct` run from the Agents panel cannot be approved mid-run, so it stops and says so. A capability outside the profile's allowance is refused.

### Runtime

A profile's `runtime` is `internal` (the default) or `acp` with the `adapter_id` of an ADR 0006 ACP definition.

- **Internal agents** run through `TurnEngine`, and their approval class decides the effect: `none` maps to local-read/allow, and `standard` or `strict` map to local-write/requires-approval. They are reachable in every invocation mode.
- **ACP-runtime agents** run through that definition's existing prompt operation, sending the profile instructions as prompt context. They are privileged execution requiring approval, and their capability declares the definition's process boundary. That operation admits its own turn, so an ACP-runtime agent is reachable only in `direct`. An agent whose ACP definition is missing or disabled is served as unavailable with that reason.

### Invocation modes

`backend/app/services/capability_service.py` binds one handler per `agent-invoke-{profile_id}` capability. `AgentInvoker.invoke` checks that the profile declares the requested mode. A call from inside a turn runs in the mode that turn is delegating in (`TurnEngine.in_turn_mode`); any other call is `direct`.

- **`direct`:** admitted as its own turn. `backend/app/api/routes/agents.py` provides list, detail, invoke, run listing, and cancellation. Operator invocation uses `CapabilityService.invoke_operator_capability`, so a specific operator request runs without self-approval while preserving execution boundaries and evidence.
- **`as_tool`:** `TurnEngine` offers enabled internal-runtime agents that declare `as_tool` to the model alongside extension operations. A model-selected agent runs inside the proposing turn under the ADR 0005 approval ladder. A failed delegation is a failed action, and the result returns as untrusted tool context.
- **`router_selected`:** `backend/app/agents/router.py` selects an agent only when the user addresses it by display name or ID (`Notes, …`, `hey Notes …`, `ask Notes to …`, `@notes …`). The router proposes `agent-invoke-{profile_id}` with the remaining task. An allowed agent answers the turn; one that requires approval asks first and answers when the user confirms. `runtime_context.agent_route` records the outcome (`selected`, `awaiting_approval`, `denied`, `unavailable`, or `failed`) and its reason. When the agent cannot answer, the assistant answers instead.
- **`handoff`:** the user starts a handoff by asking to talk to an agent. An agent that requires approval asks first. While the handoff is active, every turn, text or voice, is proposed to that agent and answered by it, with no search opened. It ends when the user says "back to JARVIS", through `POST /session/handoff/end`, when the session closes, or when the agent becomes unavailable, in which case the assistant answers and says why. `runtime_context.agent_handoff` records start, refusal, and end events, and `GET /session/status` reports `active_agent`.

Agent runs honor operation cancellation and deadlines, and closing the session cancels an active agent run.

`backend/app/runtimes/llm/local_runtime.py` drops tool-schema repetition bounds of 2000 or more before offering tools to llama.cpp, because its sampling grammar rejects the whole request otherwise; argument validation still uses the declared schema. A tool offer that the provider rejects is recorded in `runtime_context.tool_selection_error` instead of being hidden.

### Evidence

`DelegatedRunRecord` in `backend/app/actions/contracts.py` is the typed `TurnArtifact.delegated_runs` record. It covers agent runs (internal or ACP) in every mode and extension runs, recorded through `ActionEvidence` like the other action-evidence fields. An in-turn operation carries the proposing turn's session and turn IDs.

ADR 0002 owns turn/session execution, ADR 0003 prompt authority, ADR 0004 memory boundaries, ADR 0005 authorization and action evidence, and ADR 0008 the operator agent surface.

### Agent boundaries

An ACP-runtime agent's process is confined by its ACP definition's process boundary: argv allowlist, environment passthrough, working root, timeout, cancellation, and output bounds. Internal agents run no subprocess of their own; a capability they use runs under that capability's own boundary. These are application-level controls, not kernel isolation.

### Boundaries owned elsewhere

ADR 0013 owns ACP adapter behavior, outbound and inbound, for agents that execute in an external runtime. ADR 0006 owns the adapter definitions those agents are declared through. ADR 0008 owns operator-facing agent workflows.

## Confirmation

Implementation files:
- `backend/app/agents/schema.py`
- `backend/app/agents/registry.py`
- `backend/app/agents/invocation.py`
- `backend/app/agents/router.py`
- `backend/app/actions/contracts.py` for `DelegatedRunRecord`
- `backend/app/actions/catalog.py` for agent invocation and profile-management descriptors
- `backend/app/services/capability_service.py` for `build_agent_handlers`
- `backend/app/conversation/engine.py` for `run_agent`, the model-facing agent tool offer, router selection, and handoff
- `backend/app/runtimes/llm/local_runtime.py` for grammar-safe tool offers
- `backend/app/services/session_service.py` and `backend/app/api/routes/session.py` for `active_agent` and ending a handoff
- `backend/app/api/routes/agents.py`
- `desktop/src/components/agents-panel.js` for the operator profile form, duplication, and handoff status
- `config/agents/`

Test coverage:
- `backend/tests/unit/agents/` for schemas and runtime, registry storage/precedence/fingerprinted writes/enablement/ACP runtime, invocation modes, the agent tools list, and name-addressed routing and handoff phrases
- `backend/tests/unit/services/test_capability_service.py` for operator invocation of `agent-invoke-*` capabilities and ACP-runtime dispatch
- `backend/tests/unit/conversation/test_tool_turn.py` for `as_tool`, `router_selected` (including approval and fallback), `handoff` (start, approval, routed turns, end, and ending when the agent becomes unavailable), memory layers per scope, and agent capability use (allowed, paused for approval and resumed, declined, outside the allowance, and stopped in a panel run)
- `backend/tests/unit/runtimes/llm/test_llm_runtime.py` for grammar-safe llama.cpp tool offers
- `backend/tests/unit/actions/test_action_contracts.py` and `backend/tests/unit/artifacts/test_turn_artifact.py` for the typed delegated-run record
- `backend/tests/integration/api/test_headless_client.py` for profile create/update/delete, direct invocation, audit, persisted delegated-run evidence, and a handoff through the session API
- `backend/tests/integration/test_extension_runtime.py` for extension delegated-run records
- `desktop/tests/static.test.mjs` for the profile form including memory and tool choices, duplication of built-in profiles, fingerprinted edits and deletes, enablement, and handoff status

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration`
- `backend/.venv/Scripts/python scripts/validate_desktop.py regression` for the agent panel and handoff status

Live backend validation with the local llama.cpp provider demonstrated profile management through the API with stale-update refusal, and every invocation mode over text with persisted typed delegated runs: `direct` through the API, model-proposed `as_tool`, a name-addressed `router_selected` turn, and a handoff from start through two agent-answered turns to "back to JARVIS". Against the same provider, an agent with working-memory scope answered from the conversation while the same agent with no memory could not, and an agent's approval-gated local tool paused the agent, ran on confirmation, and the agent answered from its result. In native desktop use, a voice handoff request reached the router and was correctly refused for a built-in agent that does not declare `handoff`. The same use showed that the first operator profile editor, a raw JSON field, could not be used; it was replaced by the form described above.

Operator confirmation in the native desktop with an agent created there: create, duplicate a built-in agent, edit, enable/disable, and delete through the Agents panel; a voice handoff from start through a handed-off turn to its end by phrase and by the Back to JARVIS button; a name-addressed `router_selected` turn; `direct` invocation from the panel; model-proposed `as_tool` invocation by voice; and working-memory recall by the agent.

## Follow-up

None for this ADR.

New invocation modes, a change to agent memory or tool scope, or a change to how agents reach the governed execution path should update this ADR when they preserve the same agent architecture, or create/supersede an ADR when they change it.
