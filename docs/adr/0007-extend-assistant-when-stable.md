# 0007 - Extend Assistant When Stable

## Status

Accepted, living.

## Context

JARVISv7 becomes agent-capable after the underlying assistant is dependable. Agents serve role-scoped delegation, specialized context, multi-step execution, and separate process boundaries.

The seventh project promise is agents built on the assistant foundation. An agent is a role-scoped reasoning and delegation unit with a defined purpose, available capabilities, memory scope, permission boundary, invocation mode, and completion contract.

Current v7 exposes the prerequisites for later agent work: one committed turn engine, resident voice delegation into that engine, prompt authority boundaries, retrieval-backed memory, turn/session artifacts, provider profiles, search evidence, settings surfaces, diagnostics, and partial governed-action foundations. Agent routes and agent runtime code remain future implementation targets.

Current public practice points to the same shape. Agent frameworks treat handoffs and agents-as-tools as orchestration choices inside one run. Human approvals pause and resume the same run, including nested agents. Guardrails, tool contracts, MCP connections, and ACP client/agent sessions are separate mechanisms that application policy composes. ACP, in this ADR, means Agent Client Protocol v2.

## Decision

JARVISv7 will add agents only after the assistant foundations they depend on are stable enough to host them.

An agent uses:

1. the same session and turn ownership model
2. the same prompt authority and untrusted-context rules
3. the same memory retrieval and write boundaries
4. the same extension registry and capability registry
5. the same authorization, approval, cancellation, and artifact flow
6. the same provider/profile readiness and cloud-escalation policy
7. the same desktop, CLI/script, daemon, and future TUI status surfaces

Agents may be invoked directly by the user, selected by an application router, called as a tool by another agent, or reached through a handoff. Those are invocation modes. Authority comes from application policy and capability records.

Prefer modern protocol boundaries:

- Use ACP for agent/client session control, subprocess adapters, progress updates, permission requests, cancellation, and future TUI/client interoperability.
- Use MCP for external resources, prompts, and tools available to an agent.
- Use skills for reusable procedural knowledge an agent may apply.
- Use plugins only to package agents and their related extension shapes.

## Current Design

The interaction loop is centralized in `TurnEngine`. Text and voice turns converge on the same reasoning path, session continuity, personality policy, memory retrieval, search planning, response generation, artifact recording, and final state reporting.

Resident voice wraps the committed loop. Realtime voice records events, handles interruption/recovery paths, and delegates committed turns to backend services.

Memory is application-owned. Working memory, episodic artifacts, semantic memory, retrieval, curation, lifecycle review, and desktop inspection already exist. The model may propose memory candidates, but identity, policy, lifecycle, and persistence remain application-owned.

Action is partially governed. Search, provider routing, settings, provider profiles, memory lifecycle, prompt envelopes, and turn artifacts show the intended shape. Future agent work depends on a general model-callable capability registry, shared approval ledger, filesystem/process boundaries, MCP execution, skills, plugins, and agent delegation.

The current API keeps the agent surface closed. `backend/tests/unit/api/test_routes.py` asserts that OpenAPI has no `/agents` routes.

## Stability Gates

Agent work starts when these gates are true for the intended scope:

- loop: text, voice, interruption, cancellation, failure, and recovery enter one backend-owned interaction loop
- mind: model output is parsed, validated, bounded, and treated as proposal until application code accepts it
- memory: retrieval, write, lifecycle, curation, and artifact ingestion are application-owned and inspectable
- action: capabilities have stable IDs, schemas, effect classes, authorization rules, timeouts, cancellation, typed results, and artifacts
- extension: skills, MCP, hooks, plugins, prompts, providers, and connectors register through one extension/capability model
- approval: sensitive operations pause and resume the same turn/run, including delegated or nested work
- process: subprocess agents have explicit adapters, allowed roots, environment, credentials, timeouts, cancellation, output capture, and cleanup
- client: desktop, CLI/script, daemon, and future TUI clients display agent status, approvals, outputs, failures, and artifacts without owning policy
- validation: unit and integration tests prove each gate before live agent claims are made

These gates are scoped. A read-only summarizer agent needs less than a privileged coding agent. A local ACP adapter needs less than a remote cloud agent. Missing optional capabilities degrade or stay unavailable while ordinary assistant use remains available.

## Agent Rules

An agent profile must declare purpose, instructions, invocation mode, allowed models/providers, available capabilities, memory scope, approval needs, timeout/cancellation behavior, and output contract.

Agent profiles come from application-owned defaults or operator-approved extension records.

Delegation is explicit and observable. The user can inspect which agent ran, why it was selected, what it could access, what it did, whether it requested approval, how it stopped, and what artifact evidence was produced.

Agent outputs enter the same prompt, memory, artifact, and result-validation boundaries as model output from the primary assistant.

An agent uses MCP tools, skills, provider tools, or local tools through the governed capability loop. MCP metadata and skill metadata are declarations.

Non-agent interaction remains fully functional when all agent features are disabled.

## Consequences

Benefits:

- Agent work waits for foundations that can make it reliable and inspectable.
- Delegation can be added without forking sessions, memory, approvals, or artifacts.
- ACP, MCP, skills, plugins, and tools keep distinct roles while sharing one execution boundary.
- Different agent modes can scale from low-friction read-only work to approval-gated privileged work.
- A future TUI can participate as another client of the same loop.

Costs:

- Broad agent functionality is intentionally delayed until registry, capability, approval, and client surfaces exist.
- Some provider-native agent features may need wrapping before they fit v7's policy and artifact model.
- ACP subprocess adapters require lifecycle, timeout, cancellation, output, and credential discipline.
- Agent profile design must stay small enough for a personal project while still preventing hidden authority.
- More evidence must be recorded per turn/run as delegation becomes more capable.

## Remaining Work

- Complete the capability registry and action contract from ADR 0005.
- Complete the extension registry/catalog and extension-shape rules from ADR 0006.
- Define an agent profile schema with purpose, instructions, provider/model policy, invocation mode, capabilities, memory scope, approval class, timeout, cancellation, and output contract.
- Define direct invocation, router-selected invocation, agents-as-tools, and handoff modes without giving any mode extra authority.
- Add an ACP adapter boundary for subprocess agents and future client/TUI interoperability.
- Map ACP session updates, permission requests, terminal/tool chunks, cancellation, stop reasons, and errors into JARVIS artifacts and run/turn state.
- Add MCP filtering for agent-visible resources, prompts, and tools through application-owned capability policy.
- Add process isolation rules for allowed roots, environment variables, credentials, temp/cache paths, output caps, cleanup, and missing executable failures.
- Add delegated-run artifacts that record agent identity, selected profile, capabilities exposed, approvals requested, outputs, failures, cancellation, and final contract result.
- Add desktop, CLI/script, daemon, and TUI-ready status/approval surfaces before enabling long-running delegated work.
- Add focused tests for read-only agents before privileged agents; add live validation only when the required model/provider/process is actually available.

## Implementation Path

Add agent support in slices, gated by the earlier ADRs:

1. Keep `/agents` absent until there is a backend-owned profile schema, registry entry, and disabled-state response.
2. Start with a read-only local agent profile that cannot write files, run shell commands, call external services, or update memory directly.
3. Add an ACP v2 adapter boundary for subprocess/session communication before adding multiple agent implementations.
4. Map ACP updates, permission requests, terminal/tool chunks, stop reasons, and cancellation into existing turn/session artifacts.
5. Add governed capability exposure for agent tools through ADR 0005 and extension discovery through ADR 0006.
6. Add desktop/API/script status and approval surfaces before enabling long-running or privileged delegation.
7. Add a dedicated unit-test package for agent code only when agent code exists, plus focused conversation, service, API, artifact, and desktop contract tests for the slice.

Dependencies: agent support depends on the interaction loop, model/application boundary, memory layers, governed capability registry, extension registry, approval flow, artifact model, provider readiness, and client status surfaces.

Targets: agent profile schema, backend registry entries, ACP adapter, capability exposure, delegated-run artifacts, API/desktop/script/TUI-ready status surfaces, and focused tests.

Exit evidence: route/API tests for disabled and enabled agent surfaces, unit tests for profile validation and ACP event mapping, artifact assertions for delegated runs, approval tests for privileged delegation, and live validation only when the required model/provider/process is available.

## Guidance

When adding an agent, first identify the required mechanism. Use a prompt for repeatable phrasing, a skill for reusable procedure, a tool for one action, MCP for an external capability, and an agent for role-scoped reasoning or delegation.

When adding an agent profile, keep it small and inspectable. Declare what it is for, what it can use, where its memory comes from, what it may return, and what approvals it needs.

When adding delegation, keep the root interaction in control. Nested agents and handoffs surface approvals and interruptions on the root turn or run and resume from the same state.

When adding an ACP adapter, treat ACP as the session/process protocol. ACP agent memory writes, file changes, commands, and external service calls run through governed capabilities.

When adding MCP to agents, keep JARVIS as the host. Filter tools and resources before exposure, preserve schemas, report health honestly, use current per-request protocol metadata, and keep server-provided annotations separate from permission.

## Evidence

Implementation:

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
- `backend/app/services/llm_provider_profiles.py`
- `backend/app/services/llm_provider_service.py`
- `backend/app/api/routes/llm_config.py`
- `backend/app/api/routes/config.py`
- `backend/app/core/settings.py`
- `backend/app/services/search_service.py`
- `backend/app/runtimes/internetsearch/`
- `desktop/src/components/memory-panel.js`
- `desktop/src/components/search-evidence.js`
- `desktop/src/components/llm-provider-settings.js`
- `desktop/src/components/readiness-panel.js`
- `desktop/src/api-client.js`
- `desktop/src-tauri/src/backend.rs`

Tests:

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
- `backend/tests/unit/memory/test_retrieval.py`
- `backend/tests/unit/services/test_memory_service.py`
- `backend/tests/unit/api/test_memory_routes.py`
- `backend/tests/unit/artifacts/test_turn_artifact.py`
- `backend/tests/unit/services/test_llm_provider_profiles.py`
- `backend/tests/unit/services/test_llm_provider_service.py`
- `backend/tests/unit/services/test_search_service.py`
- `backend/tests/runtime/turn/test_barge_in_live.py`
- `backend/tests/runtime/desktop/test_resident_loop_live.py`

External practice reviewed:

- OpenAI Agents SDK: [agents and orchestration choices](https://openai.github.io/openai-agents-python/agents/), [handoffs](https://openai.github.io/openai-agents-js/guides/handoffs/), [human-in-the-loop run resume](https://openai.github.io/openai-agents-js/guides/human-in-the-loop/), [guardrails](https://openai.github.io/openai-agents-js/guides/guardrails/), and [tools](https://openai.github.io/openai-agents-python/tools/).
- Agent Client Protocol v2: [overview](https://github.com/agentclientprotocol/agent-client-protocol/blob/main/docs/protocol/v2/overview.mdx) for JSON-RPC methods/notifications, initialization, sessions, updates, permission requests, cancellation, client-managed environment access, and extensibility.
- Model Context Protocol: [2026-07-28 stateless core, per-request capability metadata, resources, prompts, tools, elicitation, extensions, JSON-RPC messages, and security principles](https://modelcontextprotocol.io/specification/2026-07-28), plus [deprecated roots, sampling, logging, DCR, and HTTP+SSE guidance](https://modelcontextprotocol.io/specification/2026-07-28/deprecated).
- Open Agent Skills: [`SKILL.md` frontmatter, optional `scripts/`, `references/`, `assets/`, and progressive disclosure](https://openagentskills.dev/docs/specification).
- Agent Client Protocol ecosystem: [compatible agents](https://agentclientprotocol.com/get-started/agents), [ACP Registry](https://agentclientprotocol.com/get-started/registry), and [registry repository](https://github.com/agentclientprotocol/registry) showing ACP-compatible agents such as Codex, Claude Agent, Cline, Gemini CLI, GitHub Copilot, Goose, OpenCode, Cursor, Devin, Grok Build, and Qwen Code.
- JetBrains ACP overview: [public ecosystem framing for editor/agent interoperability across local, remote, and in-house agents](https://www.jetbrains.com/acp/).
