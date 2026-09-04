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

The shared action contract is wired. `backend/app/actions/contracts.py` defines `CapabilityDescriptor`, `ModelActionProposal`, `AuthorizationContext`, `AuthorizationDecision`, `ApprovalAuditRecord`, `ExecutionResultRecord`, `ActionCancellationRecord`, `ActionEvidence`, and `CapabilityRegistry`. Descriptors declare an approval mode of `turn_boundary` or `same_turn`. The registry validates effect classes, readiness states, availability states, authorization rules, timeout/cancellation/result schema metadata, unavailable explanations, sorted snapshots, duplicate capability IDs, untrusted metadata claims, execution boundaries, and the input-schema keywords it can actually enforce. Authorization denies unregistered capabilities, arguments the input schema rejects, unavailable readiness, unavailable capabilities, denied rules, and unapproved capabilities that require approval.

`backend/app/actions/catalog.py` builds thirteen descriptors for search, memory lifecycle, provider configuration, and operator configuration from a `CapabilityObservation` of live state: enabled search providers, memory-service and curation presence, provider secret-store lock state and per-profile `readiness_state`, and `.env` presence. `CapabilityService` re-observes on every catalog read and proposal, so readiness and availability are observations rather than static claims.

`backend/app/actions/boundaries.py` declares the execution boundary rules: allowed storage roots limited to the existing `data/`, `cache/`, `reports/`, `models/`, and `runtimes/` roots, a wall-clock timeout ceiling, a cancellation contract, and a result-size bound. `run_bounded` enforces the deadline, the cancellation signal, and the result bound, and `ExecutionBoundary.resolve_path` refuses paths that escape the declared roots. The registry refuses to register a `privileged_execution` capability that does not declare these boundaries.

`backend/app/services/capability_service.py` owns proposal, authorization, approval, execution, cancellation, and audit. `same_turn` capabilities execute inside the HTTP request through `/actions`; approval-required proposals park in a bounded in-memory store, and approval re-runs the authorization ladder against freshly observed state before executing. A decided proposal is retained so a repeated decision is refused rather than reported as missing. Secret-bearing arguments are masked at record time.

`TurnEngine` expresses the search confirmation handshake in this vocabulary. A search plan becomes a `ModelActionProposal` against `search-public-web` or `search-private-web`; a private plan produces an `approval_required` decision carrying an approval ID, and the user's confirmation, refusal, or silence on the next turn becomes an approval record, a denial, or a cancellation. `TurnContext.action_evidence` carries the records, and `_persist_artifact` writes proposals, authorization decisions, approval records, execution results, and cancellations into the turn artifact. Conversational behavior, prompts, and outcome strings are unchanged.

The existing `/memory`, `/config/llm`, and `/config/operator` mutation routes record direct operator authority through `CapabilityService.operator_action`, so an operator request is represented as an approved proposal with an execution result. Their status codes and response bodies are unchanged.

What remains: `delegated_runs` has no producer and stays empty; file, workspace, shell, MCP, plugin, skill-script, and agent capabilities are not registered and are not executable, and process isolation for them is not implemented; the three mutation route groups record through the authorization ladder but still execute outside the capability executor; API-initiated action evidence lives in a bounded in-memory audit rather than a durable artifact; and no desktop surface exists for capability discovery, approval, execution status, cancellation, or audit.

## Confirmation

Implementation files:
- `backend/app/actions/contracts.py`
- `backend/app/actions/boundaries.py`
- `backend/app/actions/catalog.py`
- `backend/app/services/capability_service.py`
- `backend/app/services/operator_config_service.py`
- `backend/app/api/routes/actions.py`
- `backend/app/api/schemas/actions.py`
- `backend/app/api/dependencies.py`
- `backend/app/api/app.py`
- `backend/app/conversation/turn_manager.py`
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
- `backend/tests/unit/actions/test_action_boundaries.py`
- `backend/tests/unit/services/test_capability_service.py`
- `backend/tests/unit/api/test_action_routes.py`
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

- Expose desktop surfaces for capability discovery, approval, execution status, cancellation, and audit.
- Add process and root isolation for file, workspace, shell, MCP, plugin, skill-script, and agent execution before registering those capabilities. Declared storage-root, timeout, cancellation, and result-size boundaries exist, and the registry already refuses `privileged_execution` capabilities that do not declare them.
- Converge the `/memory`, `/config/llm`, and `/config/operator` mutation routes onto the capability executor so one path both authorizes and executes.
- Record API-initiated action evidence in a durable session artifact rather than a bounded in-memory audit.
- Populate `delegated_runs` when delegated agent execution exists; it has no producer today.
