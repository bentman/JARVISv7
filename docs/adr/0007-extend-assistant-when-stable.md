# 0007 - Extend Assistant When Stable

Date: 2026-09-01
Status: Accepted
Related: 0002, 0003, 0004, 0005, 0006, 0008, 0013

## Context and Problem Statement

JARVISv7 should become agent-capable only after the underlying assistant is dependable enough to host delegation. Agents add role-scoped reasoning, specialized context, multi-step execution, and separate process boundaries; those features amplify weaknesses in turn ownership, memory, approvals, artifacts, and runtime readiness.

The current codebase implements major prerequisites: one committed turn engine, resident voice delegation into that engine, prompt authority boundaries, retrieval-backed memory, turn/session artifacts, provider profiles, search evidence, settings surfaces, diagnostics, action-governance records, file-backed agent profiles, direct agent invocation, agent API routes, and a desktop agent panel. Router selection, handoff, and protocol-complete delegated-agent behavior remain incomplete.

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

This ADR is partially implemented. Agent profiles are managed through backend APIs, select an internal or ACP runtime, and are reachable through `direct` and `as_tool` invocation with typed delegated-run evidence. `router_selected` and `handoff` remain incomplete.

### Agent profiles and management

`backend/app/agents/schema.py` defines profile identity, purpose, instructions, invocation modes, capability IDs, memory scope, approval class, timeout, cancellation, output contract, provider/model policy, and runtime. Authority-bearing override fields are rejected.

`AgentRegistry` observes application profiles in `config/agents/` and operator profiles in `data/agents/`. It reloads when files change and reports malformed or colliding profiles without disabling the rest of the catalog. Application profiles keep their IDs and are read-only.

- **Writes:** operator profiles are validated before they are written atomically. A create refuses an existing ID; an update or delete must match the content fingerprint that was read.
- **Routes:** `backend/app/api/routes/agents.py` exposes create, update, and delete, each wrapped in the governed `agent-profile-write` / `agent-profile-delete` operator actions so every change is audited.
- **Enable/disable:** this uses the extension overlay for `agent:{profile_id}`. A disabled agent is served as a disabled capability.

### Runtime

A profile's `runtime` is `internal` (the default) or `acp` with the `adapter_id` of an ADR 0006 ACP definition.

- **Internal agents** run through `TurnEngine`, and their approval class decides the effect: `none` maps to local-read/allow, and `standard` or `strict` map to local-write/requires-approval.
- **ACP-runtime agents** run through that definition's existing prompt operation, sending the profile instructions as prompt context. They are privileged execution requiring approval, and their capability declares the definition's process boundary. An agent whose ACP definition is missing or disabled is served as unavailable with that reason.

### Invocation modes

`backend/app/services/capability_service.py` binds one handler per `agent-invoke-{profile_id}` capability. The handler chooses the mode from where the call comes from:

- **`as_tool`:** a call from inside the conversation turn that proposed it runs in that same turn through `TurnEngine.run_agent`. This is how the model proposes agent invocation: `TurnEngine` offers enabled internal-runtime agents that declare `as_tool` alongside extension operations, and the existing ADR 0005 approval ladder governs them. A failed delegation is a failed action, and the result returns as untrusted tool context.
- **`direct`:** any other call is admitted as its own turn. `backend/app/api/routes/agents.py` provides list, detail, invoke, run listing, and cancellation. Operator invocation uses `CapabilityService.invoke_operator_capability`, so a specific operator request runs without self-approval while preserving execution boundaries and evidence.

A profile must declare the mode it is reached through; a profile that declares neither executable mode is served as misconfigured. Agent runs honor operation cancellation and deadlines, and closing the session cancels an active agent run.

### Evidence

`DelegatedRunRecord` in `backend/app/actions/contracts.py` is the typed `TurnArtifact.delegated_runs` record. It covers agent runs (internal or ACP) and extension runs, recorded through `ActionEvidence` like the other action-evidence fields. An in-turn operation carries the proposing turn's session and turn IDs.

ADR 0002 owns turn/session execution, ADR 0003 prompt authority, ADR 0004 memory boundaries, ADR 0005 authorization and action evidence, and ADR 0008 the operator agent surface.

### Agent boundaries

An ACP-runtime agent's process is confined by its ACP definition's process boundary: argv allowlist, environment passthrough, working root, timeout, cancellation, and output bounds. Internal agents run no subprocess. `backend/app/agents/mcp_filter.py` implements agent-scoped MCP connection/tool/resource/prompt filtering; it is not wired to invocation yet because internal agents run no tool loop. These are application-level controls, not kernel isolation.

### Boundaries owned elsewhere

ADR 0013 owns ACP adapter behavior, outbound and inbound, for agents that execute in an external runtime. ADR 0006 owns the adapter definitions those agents are declared through. ADR 0008 owns operator-facing agent workflows.

## Confirmation

Implementation files:
- `backend/app/agents/schema.py`
- `backend/app/agents/registry.py`
- `backend/app/agents/invocation.py`
- `backend/app/agents/mcp_filter.py`
- `backend/app/actions/contracts.py` for `DelegatedRunRecord`
- `backend/app/actions/catalog.py` for agent invocation and profile-management descriptors
- `backend/app/services/capability_service.py` for `build_agent_handlers`
- `backend/app/conversation/engine.py` for `run_agent` and the model-facing agent tool offer
- `backend/app/api/routes/agents.py`
- `config/agents/`

Test coverage:
- `backend/tests/unit/agents/` for schemas and runtime, registry storage/precedence/fingerprinted writes/enablement/ACP runtime, invocation, router, and MCP filtering
- `backend/tests/unit/services/test_capability_service.py` for operator invocation of `agent-invoke-*` capabilities and ACP-runtime dispatch
- `backend/tests/unit/conversation/test_tool_turn.py` for model-proposed `as_tool` invocation inside the proposing turn
- `backend/tests/unit/actions/test_action_contracts.py` and `backend/tests/unit/artifacts/test_turn_artifact.py` for the typed delegated-run record
- `backend/tests/integration/api/test_headless_client.py` for profile create/update/delete, direct invocation, audit, and persisted delegated-run evidence through the API
- `backend/tests/integration/test_extension_runtime.py` for extension delegated-run records

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration` when invocation or evidence behavior changes

Live backend validation with a local llama.cpp provider demonstrated operator profile creation, refusal of a stale update, real model-backed direct invocation with a persisted typed delegated run, audited profile writes and deletion, and agents offered to the model as tools. The local model did not emit an agent tool call, so live `as_tool` execution is not yet demonstrated.

## Follow-up

- Wire `router_selected` and `handoff` with selection/fallback evidence, approval boundaries, cancellation, and artifacts.
- Demonstrate live model-proposed `as_tool` execution with a provider that emits tool calls.
- Validate all invocation modes before marking this ADR implemented.
