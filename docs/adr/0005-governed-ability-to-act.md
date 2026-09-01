# 0005 - Governed Ability to Act

## Status

Accepted, living.

## Context

JARVISv7 becomes useful when it can act: search, read, write, call services, change settings, use tools, invoke skills, connect MCP servers, run plugins, and delegate to agents. Acting must feel natural, but it must remain visible enough that the user can understand what happened and stop or correct it.

The fifth project promise is a governed ability to act. Governance is functional: each capability has a clear identity, input contract, effect class, authorization rule, cancellation path, result shape, and artifact evidence.

Current assistant and agent systems use the same functional pattern. Tools are declared with schemas and run through a runtime boundary. Sensitive calls can pause for human approval and resume the same run. MCP treats tool metadata as a contract that still requires host consent. Computer-use guidance emphasizes scoped permissions, untrusted external content, human confirmation for high-impact actions, and action logs.

## Decision

JARVISv7 will expose action through a governable capability loop.

A capability is real only when it has:

1. stable identity and source
2. structured input schema
3. declared effect class
4. readiness and availability state
5. authorization rule
6. execution owner
7. timeout and cancellation behavior
8. typed success and failure result
9. turn/session artifact evidence
10. user-facing explanation when it cannot run

Risk determines friction. Read-only, local, reversible, and low-sensitivity operations run directly when the user asks for them. External, mutating, privileged, destructive, privacy-sensitive, or cloud-transmitting operations require explicit approval or a deliberate policy setting. Approval pauses and resumes the same interaction loop.

The application owns capability exposure and authorization. The model may request a tool call or produce a plan, but the application decides whether the capability exists, whether the input is valid, whether approval is required, whether execution may proceed, and how the result is recorded.

This ADR defines the action contract for tools, MCP, skills, plugins, and agents.

## Current Design

Search is the clearest implemented action path. `SearchIntentResolver` detects explicit search intent, rejects secrets, asks for confirmation before private outbound queries, limits query count, and emits a structured `SearchPlan`. `SearchService` executes provider attempts, records sources and limitations, supports cancellation, and returns `SearchEvidence`. `TurnEngine` records search evidence, provider names, cancellation, failure phase, and final state in the turn artifact.

Provider routing is partially governed action. `LLMProviderProfileStore` owns provider profiles, cloud eligibility, endpoint validation, selection, encrypted API keys, and secret-key rotation. `RoutedLLM` uses explicit cloud requests, configured local fallback, cloud escalation policy, and failure classification before trying another provider. Runtime context records provider attempt evidence.

Memory lifecycle actions are governed through services. `/memory` exposes policy, inspection, confirm, correct, dispute, forget, and curation status through `MemoryService`. Operations use revision checks and lifecycle events. Desktop requests those actions through backend/Tauri APIs.

Settings and provider configuration are explicit backend actions. Operator configuration writes are limited to allowlisted fields. Secret values are masked in responses. Provider profile edits reject built-in profile edits, compatibility-profile edits, and invalid endpoints. Selected provider profiles cannot be deleted.

Prompt and artifact boundaries already reserve a place for tools. `PromptEnvelope` has `tool` authority and `tool_result` content type. Renderers mark tool results as untrusted context. `TurnArtifact` records `tools_invoked`, search evidence, runtime context, retrieved memory evidence, failure state, and phase timings.

The implemented foundations cover selected action paths. The remaining shared action infrastructure is a unified v7 namespace for built-in tools, search, skills, MCP tools, plugins, and agents; a shared approval ledger; permission taxonomy; root confinement policy; tool-result schema; and desktop/TUI approval surface for model-initiated actions.

## Action Classes

Use functional risk classes, not ceremony:

- local read: inspect local state already in scope
- local write: change repo, config, memory, profile, or local files
- external read: send a query or request outside the machine
- external write: mutate a remote system or send a message
- cloud model: transmit prompt/context to a cloud LLM provider
- privileged execution: run shell/process, plugin code, agent process, or MCP server command
- destructive action: delete, overwrite, reset, purchase, transfer, publish, or otherwise hard-to-reverse work

The approval rule is proportional:

- allow direct execution for low-risk local reads and already-confirmed user commands
- ask lightweight confirmation when private data may leave the machine
- require explicit approval for writes, privileged execution, destructive operations, and broad delegation
- allow standing policy only when it is scoped, visible, revocable, and recorded

## Consequences

Benefits:

- Action can grow without each feature inventing its own trust model.
- Low-risk operations stay usable because governance is tied to effect, not form.
- The user sees meaningful approval prompts only where authority or risk changes.
- Search, provider routing, memory lifecycle, tools, MCP, plugins, skills, and agents can share one evidence model.
- Prompt injection and model mistakes are easier to contain because external content and tool output remain untrusted context.

Costs:

- A unified action model requires new application infrastructure before broad tool use is enabled.
- Some provider-native tool features need wrapping before they can participate safely.
- Approval UX must be designed carefully or useful automation will feel blocked.
- Capability metadata can become stale unless readiness and health checks are real observations.
- More artifact detail is needed as actions become more capable.

## Remaining Work

- Define one capability registry for built-in tools, search, skills, MCP tools, plugins, and agent delegation.
- Define stable capability IDs, source/provenance, schema conversion, collision handling, availability, and health state.
- Define permission/effect classes with a small risk-based approval matrix.
- Add a shared authorization context for cloud use, external transmission, local writes, privileged execution, destructive actions, and delegated agents.
- Add an approval surface that pauses, records the proposed action and arguments, accepts approve/reject, and resumes the same turn or run.
- Record tool/action proposals, approvals, denials, executions, outputs, failures, cancellation, and delegated runs in turn/session artifacts.
- Add approved-root and storage-boundary rules before file, workspace, shell, or process tools become model-callable.
- Treat MCP/tool metadata as declared contract. Third-party read-only claims pass through application policy.
- Keep desktop, CLI/script, daemon, and future TUI on backend APIs for capability discovery, approval, execution, status, and audit.
- Keep non-agent interaction functional when tools, plugins, MCP, or agents are disabled.

## Implementation Path

Build action governance as a thin layer around existing services first:

1. Leave `backend/app/core/capabilities.py` as hardware/runtime flags.
2. Add a small action/capability registry under `backend/app/` with stable IDs, schemas, effect classes, readiness, authorization, execution, cancellation, and result records.
3. Register existing search, provider-profile, memory-lifecycle, and operator-config actions before exposing new model-callable tools.
4. Add approval records and root/process boundaries before file, shell, MCP, plugin, skill-script, or agent capabilities can mutate state.
5. Extend `backend/app/artifacts/turn_artifact.py` to record proposals, approvals, denials, executions, failures, and cancellations.
6. Add API/desktop approval surfaces only after backend execution and artifact contracts exist.
7. Add tests under `backend/tests/unit/` near the new registry plus focused service/API/conversation tests for each adopted action.

Dependencies: model-callable action depends on stable capability identity, typed schemas, authorization context, approval records, cancellation, root/process boundaries, and artifact recording.

Targets: a new backend action/capability registry, adopted existing services, turn artifacts, API approval routes, desktop approval surfaces, and focused tests.

Exit evidence: unit tests for registry behavior and effect classification, service/API tests for each adopted action, artifact assertions for proposals/approvals/results, and runtime tests only for live external providers or process execution.

## Guidance

When adding a capability:

1. Define its identity, source, schema, result, timeout, cancellation, and failure behavior.
2. Classify its effect before exposing it to a model or surface.
3. Decide whether it can run directly, needs confirmation, or needs explicit approval.
4. Validate input before execution and return typed errors.
5. Record proposal, execution, output, and failure evidence in the turn/session artifact path.
6. Keep tool output untrusted when it returns to the prompt.
7. Make unavailable or degraded capability state visible before invocation when possible.

When adding approvals:

1. Scope approval to the action, target, arguments, session/turn, and caller.
2. Make approval resumable through the same loop.
3. Support rejection as a normal outcome with model-visible explanation.
4. Allow standing approval only when it is explicit, bounded, revocable, and audited.
5. Deny by default when arguments, schema, source, or authority cannot be inspected.

When adding MCP, plugin, skill, or agent execution:

1. Register through the same capability registry.
2. Preserve source/provenance and provider/schema limitations.
3. Require application-owned trust before lowering approval requirements.
4. Confine local filesystem and process access to approved roots and modes.
5. Keep delegated work inside the same session, memory, artifact, approval, and failure model.

## Evidence

Implementation:

- `backend/app/cognition/search_policy.py`
- `backend/app/services/search_service.py`
- `backend/app/runtimes/internetsearch/base.py`
- `backend/app/runtimes/internetsearch/ddgs_runtime.py`
- `backend/app/runtimes/internetsearch/searxng_runtime.py`
- `backend/app/runtimes/internetsearch/tavily_runtime.py`
- `backend/app/runtimes/internetsearch/page_reader.py`
- `backend/app/conversation/engine.py`
- `backend/app/artifacts/turn_artifact.py`
- `backend/app/cognition/prompt_envelope.py`
- `backend/app/cognition/prompt_renderer.py`
- `backend/app/routing/provider_router.py`
- `backend/app/services/llm_provider_profiles.py`
- `backend/app/services/llm_provider_service.py`
- `backend/app/api/routes/llm_config.py`
- `backend/app/api/routes/config.py`
- `backend/app/core/settings.py`
- `backend/app/services/memory_service.py`
- `backend/app/api/routes/memory.py`
- `desktop/src/components/search-evidence.js`
- `desktop/src/components/llm-provider-settings.js`
- `desktop/src/components/memory-panel.js`
- `desktop/src/api-client.js`
- `desktop/src-tauri/src/backend.rs`

Tests:

- `backend/tests/unit/cognition/test_search_policy.py`
- `backend/tests/unit/services/test_search_service.py`
- `backend/tests/unit/conversation/test_search_turn.py`
- `backend/tests/unit/conversation/test_engine.py`
- `backend/tests/unit/artifacts/test_turn_artifact.py`
- `backend/tests/unit/routing/test_provider_router.py`
- `backend/tests/unit/runtimes/llm/test_provider_runtime.py`
- `backend/tests/unit/services/test_llm_provider_profiles.py`
- `backend/tests/unit/services/test_llm_provider_service.py`
- `backend/tests/unit/api/test_llm_config_routes.py`
- `backend/tests/unit/api/test_routes.py`
- `backend/tests/unit/services/test_memory_service.py`
- `backend/tests/unit/api/test_memory_routes.py`
- `backend/tests/runtime/services/test_search_public_providers_live.py`

External practice reviewed:

- OpenAI Agents SDK: [tools](https://openai.github.io/openai-agents-python/tools/) and [human-in-the-loop approvals](https://openai.github.io/openai-agents-python/human_in_the_loop/).
- Model Context Protocol: [2026-07-28 tool safety, host consent, and stateless request principles](https://modelcontextprotocol.io/specification/2026-07-28).
- Anthropic: [computer/browser-use best practices](https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude).
- Microsoft Agent Framework: [function tools with human approvals](https://learn.microsoft.com/en-us/agent-framework/agents/tools/tool-approval).
