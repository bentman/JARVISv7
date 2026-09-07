# 0007 - Extend Assistant When Stable

Date: 2026-09-01
Status: Accepted
Related: 0002, 0003, 0004, 0005, 0006

## Context and Problem Statement

JARVISv7 should become agent-capable only after the underlying assistant is dependable enough to host delegation. Agents add role-scoped reasoning, specialized context, multi-step execution, and separate process boundaries; those features amplify weaknesses in turn ownership, memory, approvals, artifacts, and runtime readiness.

The current codebase implements major prerequisites: one committed turn engine, resident voice delegation into that engine, prompt authority boundaries, retrieval-backed memory, turn/session artifacts, provider profiles, search evidence, settings surfaces, diagnostics, action-governance records, file-backed agent profiles, direct agent invocation, agent API routes, and a desktop agent panel. Operational agent management and protocol-complete delegated-agent behavior remain incomplete.

The architecture needs a stability gate: agent work can start in narrow slices, but it must not fork sessions, memory, approval, extension, or artifact behavior away from the assistant foundation.

## Decision Drivers

- Preserve ADR 0002's backend-owned interaction loop for direct and delegated work.
- Preserve ADR 0003's model/application boundary so agent output remains proposal until application code accepts it.
- Preserve ADR 0004's application-owned memory retrieval, write, curation, lifecycle, and artifacts.
- Depend on ADR 0005 capability governance before exposing privileged or external agent actions.
- Depend on ADR 0006 extension cataloging before packaging agents, skills, MCP connections, hooks, or plugins.
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
- ACP v2 subprocess adapters require lifecycle, timeout, cancellation, output, and credential discipline.
- Agent profile design must stay small enough for a personal project while still preventing hidden authority.
- Delegation requires more evidence per turn/run.

## Implementation

This ADR is partially implemented for direct agent operation and the current extension/governance integration. Some invocation modes and profile-management workflows remain follow-up work.

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
- ACP client sessions are admitted through the same `TurnEngine` session path and governed capability executor; ACP events, permission requests, cancellation, and results are available for turn artifacts and approval handling. Current ACP behavior must be aligned to Agent Client Protocol v2 before the project claims ACP compatibility for either outbound agent adapters or the inbound JARVIS server.

The current agent system is file-backed and operational for direct invocation, governed execution evidence, and inspection.

Agent profiles are defined by `AgentProfile` in `backend/app/agents/schema.py`. Each profile declares a `profile_id`, `display_name`, `purpose`, `instructions`, `invocation_modes` (from `direct`, `router_selected`, `as_tool`, `handoff`), `capability_ids`, `memory_scope` (from `none`, `working`, `episodic`, `semantic`, `full`), `approval_class` (from `none`, `standard`, `strict`), `timeout_ms`, `cancellable`, `output_contract`, and `provider_model_policy`. Authority-bearing fields (`tool_policy`, `routing_policy`, `memory_policy`, `safety_overrides`, `hidden_instructions`) are rejected at load time. Profiles are loaded from YAML files under `config/agents/` by `backend/app/agents/loader.py`.

`AgentRegistry` in `backend/app/agents/registry.py` loads and caches profiles, integrates with the extension catalog (as family `agent` in `ExtensionObservation.agents`), and registers capability descriptors (as `agent-invoke-{profile_id}` in `CapabilityObservation.agents`). The `approval_class` maps to effect classes and authorization rules: `none` → `local_read`/`allow`, `standard` → `local_write`/`requires_approval`, `strict` → `privileged_execution`/`requires_approval`.

Invocation is implemented in `backend/app/agents/invocation.py`. `AgentInvoker.invoke_direct()` and `invoke_as_tool()` validate the profile exists and supports the requested mode, then delegate to `TurnEngine.run_agent()`. The engine method admits agent work through `_admit_turn()`, builds a prompt envelope with the agent's instructions as a trusted application segment, calls the LLM, and records a `TurnArtifact` with `delegated_runs`.

`AgentRouter` in `backend/app/agents/router.py` provides heuristic router-selected invocation by matching keywords from the profile's purpose against the request text.

Agent API routes exist at `backend/app/api/routes/agents.py`: `GET /agents` (list profiles), `GET /agents/{profile_id}` (detail), `POST /agents/invoke` (invoke through governed capability path), `GET /agents/runs` (list runs), `POST /agents/{profile_id}/cancel` (cancel). The desktop agent panel at `desktop/src/components/agents-panel.js` provides catalog display, invocation, run tracking, and cancellation through Tauri commands.

Agent profile authoring is not an operator UI workflow in the current codebase. Profiles are edited as YAML under `config/agents/`, then loaded and validated by `AgentRegistry`. The desktop should not expose add/remove/modify controls until backend-owned profile mutation routes exist.

Session mapping in `backend/app/agents/session_mapping.py` maps ACP session events into `AgentSessionRecord` entries that produce `delegated_runs` dicts for `TurnArtifact`. `TurnArtifact.agent_evidence()` filters delegated runs for agent-specific evidence.

Agent-scoped MCP filtering in `backend/app/agents/mcp_filter.py` provides `AgentMcpPolicy` that restricts agent access to specific MCP connections, tools, resources, and prompts based on the agent profile's `capability_ids`.

Process isolation for agents is implemented in `AgentIsolation` in `backend/app/actions/boundaries.py`. It extends `ProcessBoundary` with agent-scoped environment scrubbing (removes sensitive keys like TOKEN, SECRET, PASSWORD, KEY, CREDENTIAL unless explicitly allowlisted), output byte limits, credential reference tracking, and working directory escape prevention.

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
- `backend/app/agents/schema.py`
- `backend/app/agents/loader.py`
- `backend/app/agents/registry.py`
- `backend/app/agents/invocation.py`
- `backend/app/agents/router.py`
- `backend/app/agents/session_mapping.py`
- `backend/app/agents/mcp_filter.py`
- `backend/app/api/routes/agents.py`
- `backend/app/api/schemas/agents.py`
- `backend/app/actions/boundaries.py`
- `backend/app/extensions/contracts.py`
- `backend/app/extensions/catalog.py`
- `backend/app/actions/catalog.py`
- `backend/app/services/extension_service.py`
- `backend/app/services/capability_service.py`
- `backend/app/api/app.py`
- `config/agents/summarizer.yaml`
- `desktop/src/components/agents-panel.js`

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
- `backend/tests/unit/actions/test_action_boundaries.py`
- `backend/tests/unit/services/test_llm_provider_profiles.py`
- `backend/tests/unit/services/test_llm_provider_service.py`
- `backend/tests/unit/services/test_search_service.py`
- `backend/tests/unit/agents/test_agent_schema.py`
- `backend/tests/unit/agents/test_agent_registry.py`
- `backend/tests/unit/agents/test_agent_invocation.py`
- `backend/tests/unit/agents/test_agent_router.py`
- `backend/tests/unit/agents/test_agent_session_mapping.py`
- `backend/tests/unit/agents/test_agent_mcp_filter.py`
- `backend/tests/runtime/turn/test_turn_control_live.py`
- `backend/tests/runtime/desktop/test_resident_voice_desktop_live.py`

Validation results (linux-amd64):
- `backend/.venv/bin/python scripts/validate_backend.py unit`: PASS, 1455 passed.
- `backend/.venv/bin/python scripts/validate_backend.py integration`: PASS, 17 passed, including actual local MCP and ACP SDK peers.
- `npm --prefix desktop test`: PASS.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS.

Protocol tests required execution outside the restricted runner because its asyncio
subprocess/thread I/O stalled. Live native desktop behavior, remote deployment,
and other host classes remain unverified. The declared process controls are not
an OS sandbox.

## Follow-up

- Agent profile control plane: add backend-owned create, update, delete, enable, disable, validation, conflict handling, persistence rules, audit evidence, and desktop controls. Desktop must not mutate profile YAML directly. Operator profile changes must produce clear validation/storage errors and leave the registry in a reloadable state.
- Agent identity/runtime split: keep agent profile identity separate from runtime adapter. The profile owns purpose, instructions, invocation modes, capability IDs, memory scope, approval class, output contract, provider/model policy, and operator-visible metadata. Runtime adapters own how the work is executed: internal `TurnEngine` for JARVIS-owned agents, or Agent Client Protocol v2 for external agents. Do not add a JARVIS-specific external-agent protocol.
- Built-in external agent defaults: ship disabled-by-default, backend-owned ACP v2 profiles/adapters for Antigravity (`agy`), Claude Code, Codex, GitHub Copilot, and Qwen-capable agent execution. These defaults should be immutable application profiles with operator overrides stored outside tracked config. Availability is determined by installed ACP v2 command/runtime discovery, not by assuming the tools exist.
- Outbound ACP v2: delegated subprocess agents must use Agent Client Protocol v2, including initialization/version negotiation, optional auth, `session/new`, `session/list`, `session/resume`, `session/close`, `session/prompt`, streamed `session/update`, `session/request_permission`, `elicitation/create`, cancellation, and durable run evidence. Prompt acceptance and foreground completion are separate states and must be reflected in artifacts and desktop status.
- Inbound ACP v2: replace the current local bridge with an Agent Client Protocol v2 server before exposing inbound agent-client interoperability. A compatible server must expose ACP v2 session lifecycle, update notifications, permission and elicitation handling, cancellation, and absolute-path conventions through the backend-owned turn engine.
- Router and handoff behavior: `router_selected`, `as_tool`, and `handoff` modes need explicit execution paths, ranking or selection evidence, confidence/fallback behavior, approval boundaries, cancellation, and artifacts. The current heuristic selector is not an autonomous routing policy.
- Agent capability integration: agent invocation must be usable from the assistant loop, not only from manual desktop controls. The model may propose an agent capability, but backend policy decides eligibility, approval, memory scope, and execution.
- Desktop Agents: provide a working operator surface for profile list/detail, create/update/delete, enable/disable, adapter configuration, invocation, cancellation, run status, approval/input prompts, evidence, and errors. Add/remove/modify controls are incomplete until the backend control plane exists.
- Validation: prove profile mutation, direct invocation, as-tool invocation, router-selected invocation, handoff, ACP v2 inbound/outbound operation, cancellation, approval, elicitation, run evidence, and native desktop behavior before marking this ADR implemented.
- Live agent validation requires actual model/provider/process availability. Unit tests cover code paths; runtime tests are gated on hardware. `AgentIsolation` provides application-level environment scrubbing and path containment, not kernel-level isolation.
