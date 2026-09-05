# 0007 - Extend Assistant When Stable

Date: 2026-09-01
Status: Accepted
Related: 0002, 0003, 0004, 0005, 0006

## Context and Problem Statement

JARVISv7 should become agent-capable only after the underlying assistant is dependable enough to host delegation. Agents add role-scoped reasoning, specialized context, multi-step execution, and separate process boundaries; those features amplify weaknesses in turn ownership, memory, approvals, artifacts, and runtime readiness.

The current codebase implements major prerequisites: one committed turn engine, resident voice delegation into that engine, prompt authority boundaries, retrieval-backed memory, turn/session artifacts, provider profiles, search evidence, settings surfaces, diagnostics, and action-governance records. Agent routes and agent runtime code remain intentionally absent.

The architecture needs a stability gate: agent work can start in narrow slices, but it must not fork sessions, memory, approval, extension, or artifact behavior away from the assistant foundation.

## Decision Drivers

- Preserve ADR 0002's backend-owned interaction loop for direct and delegated work.
- Preserve ADR 0003's model/application boundary so agent output remains proposal until application code accepts it.
- Preserve ADR 0004's application-owned memory retrieval, write, curation, lifecycle, and artifacts.
- Depend on ADR 0005 capability governance before exposing privileged or external agent actions.
- Depend on ADR 0006 extension cataloging before packaging agents, skills, MCP connections, hooks, or plugins.
- Keep non-agent assistant use functional when all agent features are disabled.

## Considered Options

- Add agent routes and runtime first, then backfill governance.
- Use provider-native agents as the primary agent system.
- Keep agents out of JARVISv7 entirely.
- Add agents only after the assistant foundations they depend on are stable enough to host them.

## Decision Outcome

Chosen option: `Add agents only after the assistant foundations they depend on are stable enough to host them`.

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
- approval: sensitive operations pause and resume the same turn/run, including delegated or nested work
- process: subprocess agents have explicit adapters, allowed roots, environment, credentials, timeouts, cancellation, output capture, and cleanup
- client: desktop, CLI/script, daemon, and future clients display agent status, approvals, outputs, failures, and artifacts without owning policy
- validation: unit and integration tests prove each gate before live agent claims are made

These gates are scoped. A read-only summarizer agent needs less than a privileged coding agent. Missing optional capabilities degrade or stay unavailable while ordinary assistant use remains available.

## Consequences

Positive:
- Agent work waits for foundations that can make it reliable and inspectable.
- Delegation can be added without forking sessions, memory, approvals, or artifacts.
- ACP, MCP, skills, plugins, and tools keep distinct roles while sharing one execution boundary.
- Agent modes can scale from low-risk read-only work to approval-gated privileged work.

Negative:
- Broad agent functionality is intentionally delayed until registry, capability, approval, and client surfaces exist.
- Provider-native agent features may need wrapping before they fit v7's policy and artifact model.
- ACP subprocess adapters require lifecycle, timeout, cancellation, output, and credential discipline.
- Agent profile design must stay small enough for a personal project while still preventing hidden authority.
- Delegation requires more evidence per turn/run.

## Implementation

This ADR is partially implemented.

Implemented foundations:
- `backend/app/conversation/engine.py` centralizes text and voice turns through the same reasoning path, session continuity, personality policy, memory retrieval, search planning, response generation, artifact recording, and final state reporting.
- `backend/app/services/turn_service.py` delegates text and voice turn entry points to `TurnEngine`.
- `backend/app/services/resident_voice_invocation.py` routes resident voice work into the session service instead of owning separate assistant behavior.
- Realtime voice support in `backend/app/conversation/realtime/` records events and interruption/recovery behavior without creating an agent runtime.
- Prompt authority boundaries exist in `backend/app/cognition/prompt_envelope.py`, `backend/app/cognition/prompt_assembler.py`, and `backend/app/cognition/prompt_renderer.py`.
- Memory foundations exist in `backend/app/memory/`, `backend/app/services/memory_service.py`, `backend/app/api/routes/memory.py`, and `desktop/src/components/memory-panel.js`.
- Turn and session artifacts exist in `backend/app/artifacts/turn_artifact.py`, `backend/app/artifacts/session_artifact.py`, and `backend/app/artifacts/session_timeline.py`.
- Provider profile, settings, readiness, and search-provider surfaces exist through backend services/routes and thin desktop API/UI bindings.
- Action governance records exist in `backend/app/actions/contracts.py`, including capability descriptors, proposals, authorization decisions, approvals, execution results, cancellation policy, and delegated-run artifact fields.
- ACP client sessions are admitted through the same `TurnEngine` session path and governed capability executor; ACP events, permission requests, cancellation, and results are available for turn artifacts and approval handling. No inbound ACP server, router-selected agent, or agents-as-tools surface is enabled.
- The API currently keeps agent routes closed; `backend/tests/unit/api/test_routes.py` asserts that OpenAPI has no `/agents` routes.

Not implemented yet:
- Agent profile schema.
- General agent profiles and registry beyond explicit ACP extension entries.
- Router-selected invocation, agents-as-tools, or handoff modes.
- Agent-facing delegated-run and client surfaces beyond the ACP client-session boundary.
- Broader agent-mode approval and memory policies beyond explicit ACP client sessions.
- Script, daemon, and future client surfaces beyond the implemented backend API and desktop extension controls.

## Confirmation

Implementation evidence:
- `ProjectVision.md`
- `backend/app/conversation/engine.py`
- `backend/app/conversation/realtime/session.py`
- `backend/app/conversation/realtime/interruption.py`
- `backend/app/services/turn_service.py`
- `backend/app/services/resident_voice_invocation.py`
- `backend/app/cognition/prompt_envelope.py`
- `backend/app/cognition/prompt_assembler.py`
- `backend/app/cognition/prompt_renderer.py`
- `backend/app/cognition/search_policy.py`
- `backend/app/memory/`
- `backend/app/services/memory_service.py`
- `backend/app/api/routes/memory.py`
- `backend/app/artifacts/turn_artifact.py`
- `backend/app/artifacts/session_artifact.py`
- `backend/app/artifacts/session_timeline.py`
- `backend/app/actions/contracts.py`
- `backend/app/services/llm_provider_profiles.py`
- `backend/app/services/llm_provider_service.py`
- `backend/app/api/routes/llm_config.py`
- `backend/app/api/routes/config.py`
- `backend/app/core/settings.py`
- `backend/app/services/search_service.py`
- `backend/app/runtimes/internetsearch/`
- `desktop/src/api-client.js`
- `desktop/src/components/memory-panel.js`
- `desktop/src/components/search-evidence.js`
- `desktop/src/components/llm-provider-settings.js`
- `desktop/src/components/readiness-panel.js`
- `desktop/src-tauri/src/backend.rs`

Validation evidence:
- `backend/tests/unit/api/test_routes.py`
- `backend/tests/unit/services/test_turn_service.py`
- `backend/tests/unit/conversation/test_engine.py`
- `backend/tests/unit/conversation/realtime/test_session.py`
- `backend/tests/unit/conversation/realtime/test_response_and_interruption.py`
- `backend/tests/unit/cognition/test_prompt_assembler.py`
- `backend/tests/unit/cognition/test_search_policy.py`
- `backend/tests/unit/memory/test_working_memory.py`
- `backend/tests/unit/memory/test_episodic.py`
- `backend/tests/unit/memory/test_semantic.py`
- `backend/tests/unit/memory/test_semantic_lifecycle.py`
- `backend/tests/unit/memory/test_retrieval.py`
- `backend/tests/unit/services/test_memory_service.py`
- `backend/tests/unit/api/test_memory_routes.py`
- `backend/tests/unit/artifacts/test_turn_artifact.py`
- `backend/tests/unit/actions/test_action_contracts.py`
- `backend/tests/unit/services/test_llm_provider_profiles.py`
- `backend/tests/unit/services/test_llm_provider_service.py`
- `backend/tests/unit/services/test_search_service.py`
- `backend/tests/runtime/turn/test_turn_control_live.py`
- `backend/tests/runtime/desktop/test_resident_voice_desktop_live.py`

Known absence checks:
- No source directory or file currently implements an agent profile schema.
- General agent profiles and autonomous routing remain absent; explicit ACP client runs register as extensions.
- ACP subprocess bridge behavior exists behind the governed process/action boundary and uses the same TurnEngine admission, approvals, and artifact path; inbound/server and agent-router behavior remains absent.
- Router-selected, agents-as-tools, and handoff modes remain absent.
- OS sandboxing and agent-visible MCP delegation filtering remain outside the explicit ACP client implementation.
- `backend/tests/unit/api/test_routes.py` includes a route-surface guard that agent routes are absent from OpenAPI.

Validation results (linux-amd64):
- `backend/.venv/bin/python scripts/validate_backend.py unit`: PASS, 1259 passed.
- `backend/.venv/bin/python scripts/validate_backend.py integration`: PASS, 19 passed, including actual local MCP and ACP SDK peers.
- `npm --prefix desktop test`: PASS.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml --offline`: PASS.

Protocol tests required execution outside the restricted runner because its asyncio
subprocess/thread I/O stalled. Desktop/mobile screenshots use the actual component
with fixture data; a live native desktop, remote deployment, and other host classes
remain unverified. The declared process controls are not an OS sandbox.

## Follow-up

Gaps required to complete this ADR:
- Complete ADR 0005's governed capability execution path.
- Complete ADR 0006's extension catalog and extension-shape registration.
- Define an agent profile schema with purpose, instructions, provider/model policy, invocation mode, capabilities, memory scope, approval class, timeout, cancellation, and output contract.
- Define direct invocation, router-selected invocation, agents-as-tools, and handoff modes without giving any mode extra authority.
- Add agent profiles, delegated-run APIs, router/agents-as-tools/handoff modes, and future client/TUI interoperability.
- Map ACP session updates, permission requests, terminal/tool chunks, cancellation, stop reasons, and errors into JARVIS artifacts and run/turn state.
- Add MCP filtering for agent-visible resources, prompts, and tools through application-owned capability policy.
- Add process isolation rules for allowed roots, environment variables, credentials, temp/cache paths, output caps, cleanup, and missing executable failures.
- Extend existing ACP delegated-run artifacts with profile and capability-scope evidence when broader agent profiles are introduced.
- Add backend API, desktop, CLI/script, daemon, and future client status/approval surfaces before enabling long-running delegated work.
- Add focused tests for read-only agents before privileged agents; add live validation only when the required model/provider/process is actually available.
