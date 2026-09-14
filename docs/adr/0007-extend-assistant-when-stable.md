# 0007 - Extend Assistant When Stable

Date: 2026-09-01
Status: Accepted
Related: 0002, 0003, 0004, 0005, 0006, 0008, 0013

## Context and Problem Statement

JARVISv7 should become agent-capable only after the underlying assistant is dependable enough to host delegation. Agents add role-scoped reasoning, specialized context, multi-step execution, and separate process boundaries; those features amplify weaknesses in turn ownership, memory, approvals, artifacts, and runtime readiness.

The current codebase implements major prerequisites: one committed turn engine, resident voice delegation into that engine, prompt authority boundaries, retrieval-backed memory, turn/session artifacts, provider profiles, search evidence, settings surfaces, diagnostics, action-governance records, file-backed agent profiles, direct agent invocation, agent API routes, and a desktop agent panel. Operational agent management and protocol-complete delegated-agent behavior remain incomplete.

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

This ADR is partially implemented. File-backed agents support direct invocation and inspection. Profile management and invocation modes beyond direct remain incomplete.

### Agent profiles and direct invocation

`backend/app/agents/schema.py` defines profile identity, purpose, instructions, invocation modes, capability IDs, memory scope, approval class, timeout, cancellation, output contract, and provider/model policy. Authority-bearing override fields are rejected. `AgentRegistry` reloads YAML profiles from `config/agents/` when files change and reports malformed profiles without disabling the rest of the catalog.

The registry exposes agent profiles through the extension catalog and `agent-invoke-{profile_id}` capability descriptors. Current in-process approval classes map `none` to local-read/allow and `standard` or `strict` to local-write/requires-approval. Only direct mode is currently reachable; profiles without it report misconfigured. `AgentRouter` and `invoke_as_tool` exist but are not connected to complete invocation workflows.

`backend/app/agents/invocation.py` delegates direct work to `TurnEngine.run_agent`, using the shared turn-admission, prompt, provider, and artifact path. Handler bindings in `backend/app/api/app.py` resolve the active session engine. ADR 0002 owns turn/session execution, ADR 0003 prompt authority, ADR 0004 memory boundaries, and ADR 0005 authorization and action evidence.

`backend/app/api/routes/agents.py` provides list, detail, invoke, run listing, and cancellation. Operator invocation uses `CapabilityService.invoke_operator_capability`, so a specific operator request runs without self-approval while preserving execution boundaries and evidence. Agent profile authoring remains file-based. ADR 0008 owns the operator agent surface.

### Agent boundaries

`backend/app/agents/mcp_filter.py` implements agent-scoped MCP connection/tool/resource/prompt filtering. `AgentIsolation` in `backend/app/actions/boundaries.py` provides environment scrubbing, credential reference tracking, output limits, and working-root containment. These are application-level controls, not kernel isolation.

### Boundaries owned elsewhere

ADR 0013 owns ACP adapter behavior, outbound and inbound, for agents that execute in an external runtime. ADR 0006 owns the adapter definitions those agents are declared through. ADR 0008 owns operator-facing agent workflows.

## Confirmation

Implementation files:
- `backend/app/agents/schema.py`
- `backend/app/agents/registry.py`
- `backend/app/agents/invocation.py`
- `backend/app/agents/mcp_filter.py`
- `backend/app/actions/boundaries.py` for `AgentIsolation`
- `backend/app/api/routes/agents.py`
- `config/agents/`

Test coverage:
- `backend/tests/unit/agents/` for schemas, registry, direct invocation, router, session mapping, and MCP filtering
- `backend/tests/unit/services/test_capability_service.py` for operator invocation of `agent-invoke-*` capabilities

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration` when invocation or evidence behavior changes

Live backend validation demonstrated the built-in summarizer profile, a real model-backed direct response, persisted proposal/decision/execution evidence, and denial of a profile lacking direct mode. Live agent runs require actual model/provider availability.

## Follow-up

- Add backend-owned agent profile create/update/delete, enable/disable, validation, conflict handling, persistence, and audit, with desktop controls using those APIs.
- Complete the agent identity/runtime split: profiles own role and scope; runtime adapters select internal TurnEngine execution or external ADR 0013 execution.
- Wire `router_selected`, `as_tool`, and `handoff` paths with selection/fallback evidence, approval boundaries, cancellation, and artifacts. Make model-proposed agent invocation available through the assistant's governed capability path.
- Give `TurnArtifact.delegated_runs` a typed record, as the other action-evidence fields have. It is currently an untyped dict, so delegated-run evidence is the one action field with no schema.
- Validate profile mutation and all invocation modes before marking this ADR implemented.
