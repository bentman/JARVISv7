# 0005 - Governed Ability to Act

Date: 2026-09-01
Status: Accepted
Related: 0002, 0003, 0004, 0006, 0007

## Context and Problem Statement

JARVISv7 becomes useful when it can act: search, change settings, configure providers, manage memory lifecycle, call services, use tools, connect external capability, or delegate to agents. Acting must remain visible enough that the user can understand what happened, stop it, correct it, and distinguish low-risk reads from higher-risk side effects.

The architecture needs one governable action loop. A capability must have a stable identity, input contract, effect class, readiness/availability state, authorization rule, execution owner, timeout/cancellation behavior, result shape, artifact evidence, and user-facing unavailable explanation.

## Decision Drivers

- Action governance should be based on effect and risk, not feature label.
- Low-risk, already-requested actions should stay usable.
- External, mutating, privileged, destructive, privacy-sensitive, or cloud-transmitting actions need explicit authorization.
- Model output can request or propose an action, but application code must validate, authorize, execute, and record it.
- Action results and external content must return as untrusted context.
- Tools, search, provider configuration, memory lifecycle, MCP, skills, plugins, and agents need one evidence model.

## Considered Options

- Let each feature define its own action permission and audit behavior.
- Rely on prompt instructions to keep model-initiated action safe.
- Define a shared capability/action contract and wire executable action paths through it.

## Decision Outcome

Chosen option: `Define a shared capability/action contract and wire executable action paths through it`.

Risk determines friction:

- Local read: inspect local state already in scope.
- Local write: change repo, config, memory, profile, or local files.
- External read: send a query or request outside the machine.
- External write: mutate a remote system or send a message.
- Cloud model: transmit prompt/context to a cloud LLM provider.
- Privileged execution: run shell/process, plugin code, agent process, or MCP server command.
- Destructive action: delete, overwrite, reset, purchase, transfer, publish, or otherwise hard-to-reverse work.

Low-risk local reads and already-confirmed user commands can run directly. Private outbound requests, writes, privileged execution, destructive operations, broad delegation, and cloud transmission require confirmation, approval, or a deliberate scoped policy setting.

## Consequences

Positive:
- Action can grow without each feature inventing its own trust model.
- Low-risk operations stay usable because governance is tied to effect, not form.
- The user sees meaningful approval prompts where authority or risk changes.
- Search, provider routing, memory lifecycle, tools, MCP, plugins, skills, and agents can share one evidence model.
- Prompt injection and model mistakes are easier to contain because external content and tool output remain untrusted context.

Negative:
- A unified action model requires shared infrastructure before broad model-callable tool use is enabled.
- Provider-native tool features need wrapping before they can participate safely.
- Approval UX must be designed carefully or useful automation will feel blocked.
- Capability metadata can become stale unless readiness and health checks are real observations.
- More artifact detail is needed as actions become more capable.

## Implementation

This ADR is partially implemented.

Search is the clearest implemented governed action path. `SearchIntentResolver` detects explicit search intent, rejects secrets, asks for confirmation before private outbound queries, limits query count, and emits a structured `SearchPlan`. `SearchService` executes provider attempts, records sources and limitations, supports cancellation, and returns `SearchEvidence`. `TurnEngine` records search evidence, provider names, cancellation, failure phase, and final state in the turn artifact.

Provider routing is partially governed action. `LLMProviderProfileStore` owns provider profiles, cloud eligibility, endpoint validation, selection, encrypted API keys, and secret-key rotation. `RoutedLLM` uses explicit cloud requests, configured local fallback, cloud escalation policy, and failure classification before trying another provider. Runtime context records provider attempt evidence.

Memory lifecycle actions are governed through services. `/memory` exposes policy, inspection, confirm, correct, dispute, forget, and curation status through `MemoryService`. Operations use revision checks and lifecycle events. Desktop requests those actions through backend/Tauri APIs.

Settings and provider configuration are explicit backend actions. Operator configuration writes are limited to allowlisted fields. Secret values are masked in responses. Provider profile edits reject built-in profile edits, compatibility-profile edits, invalid endpoints, and deletion of selected provider profiles.

Prompt and artifact boundaries reserve action evidence. `PromptEnvelope` has `tool` authority and `tool_result` content type. Renderers mark tool results as untrusted context. `TurnArtifact` records `tools_invoked`, `action_proposals`, `authorization_decisions`, `approval_records`, `action_execution_results`, `action_cancellations`, `delegated_runs`, search evidence, runtime context, retrieved memory evidence, failure state, and phase timings.

Action contract scaffolding exists in `backend/app/actions/contracts.py`. It defines `CapabilityDescriptor`, `ModelActionProposal`, `AuthorizationContext`, `AuthorizationDecision`, `ApprovalAuditRecord`, `ExecutionResultRecord`, and `CapabilityRegistry`. The registry validates effect classes, readiness states, availability states, authorization rules, timeout/cancellation/result schema metadata, unavailable explanations, sorted snapshots, duplicate capability IDs, and untrusted metadata claims.

The shared action loop is not fully wired yet. Existing governed paths do not all register as capability descriptors; model-callable tools do not yet execute through the registry; approval does not yet pause/resume turns through a backend/API/desktop approval surface; and root/process boundaries for file, shell, MCP, plugin, skill-script, or agent execution are not yet implemented.

## Confirmation

Implementation files:
- `backend/app/actions/contracts.py`
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

Test coverage:
- `backend/tests/unit/actions/test_action_contracts.py`
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

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration` when action behavior crosses service/API boundaries
- `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families services --devices ...` for live external-provider validation claims
- `npm --prefix desktop test` for desktop action/config/memory/search contract changes

## Follow-up

Required to complete this ADR:

- Register existing governed actions, including search, provider-profile, memory-lifecycle, and operator-config actions, through the capability registry.
- Wire capability authorization into action execution so registered capabilities use one authorization path.
- Add an approval flow that records proposed action arguments, accepts approve/reject, and resumes the same turn or run.
- Populate turn/session artifacts with action proposals, authorization decisions, approval records, execution results, cancellations, and delegated runs.
- Add root, storage, process, timeout, cancellation, and output-boundary rules before file, workspace, shell, MCP, plugin, skill-script, or agent capabilities become executable.
- Expose backend API and desktop surfaces for capability discovery, approval, execution status, cancellation, and audit.
- Add focused tests for registered capability execution, approval decisions, artifact recording, unavailable/degraded capability state, and no execution leakage when capabilities are disabled.
