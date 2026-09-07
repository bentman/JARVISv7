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

## Decision Outcome

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

This ADR is partially implemented. The shared action mechanics are in place. A first reclassification pass is done: capabilities whose only effect is a local write confined to `data/` no longer require approval. Reclassifying the remaining broad defaults is follow-up.

Search is the clearest implemented governed action path. `SearchIntentResolver` detects explicit search intent, rejects secrets, asks for confirmation before private outbound queries, limits query count, and emits a structured `SearchPlan`. `SearchService` executes provider attempts, records sources and limitations, supports cancellation, and returns `SearchEvidence`. `TurnEngine` records search evidence, provider names, cancellation, failure phase, and final state in the turn artifact.

Provider routing is partially governed action. `LLMProviderProfileStore` owns provider profiles, cloud eligibility, endpoint validation, selection, encrypted API keys, and secret-key rotation. `RoutedLLM` uses explicit cloud requests, configured local fallback, cloud escalation policy, and failure classification before trying another provider. Runtime context records provider attempt evidence.

Memory lifecycle actions are governed through services. `/memory` exposes policy, inspection, confirm, correct, dispute, forget, and curation status through `MemoryService`. Operations use revision checks and lifecycle events. Desktop requests those actions through backend/Tauri APIs.

Settings and provider configuration are explicit backend actions. Operator configuration writes are limited to allowlisted fields. Secret values are masked in responses. Provider profile edits reject built-in profile edits, compatibility-profile edits, invalid endpoints, and deletion of selected provider profiles.

Prompt and artifact boundaries reserve action evidence. `PromptEnvelope` has `tool` authority and `tool_result` content type. Renderers mark tool results as untrusted context. `TurnArtifact` records `tools_invoked`, `action_proposals`, `authorization_decisions`, `approval_records`, `action_execution_results`, `action_cancellations`, `delegated_runs`, search evidence, runtime context, retrieved memory evidence, failure state, and phase timings.

The shared action contract is wired. `backend/app/actions/contracts.py` defines `CapabilityDescriptor`, `ModelActionProposal`, `AuthorizationContext`, `AuthorizationDecision`, `ApprovalAuditRecord`, `ExecutionResultRecord`, `ActionCancellationRecord`, `ActionEvidence`, and `CapabilityRegistry`. Descriptors declare an approval mode of `turn_boundary` or `same_turn`. The registry validates effect classes, readiness states, availability states, authorization rules, timeout/cancellation/result schema metadata, unavailable explanations, sorted snapshots, duplicate capability IDs, untrusted metadata claims, execution boundaries, and JSON Schema validation without remote schema fetching. Authorization denies unregistered capabilities, arguments the input schema rejects, unavailable readiness, unavailable capabilities, denied rules, and unapproved capabilities that require approval.

`backend/app/actions/catalog.py` builds thirteen descriptors for search, memory lifecycle, provider configuration, and operator configuration from a `CapabilityObservation` of live state: enabled search providers, memory-service and curation presence, provider secret-store lock state and per-profile `readiness_state`, and `.env` presence. `CapabilityService` re-observes on every catalog read and proposal, so readiness and availability are observations rather than static claims.

`backend/app/actions/boundaries.py` declares the execution boundary rules: allowed storage roots limited to the existing `data/`, `cache/`, `reports/`, `models/`, and `runtimes/` roots, a wall-clock timeout ceiling, a cancellation contract, and a result-size bound. `run_bounded` enforces the deadline, the cancellation signal, and the result bound, and `ExecutionBoundary.resolve_path` refuses paths that escape the declared roots. The registry refuses to register a `privileged_execution` capability that does not declare these boundaries.

`backend/app/services/capability_service.py` owns proposal, authorization, approval, execution, cancellation, and audit. `same_turn` capabilities execute inside the HTTP request through `/actions`; approval-required proposals park in a bounded in-memory store, and approval re-runs the authorization ladder against freshly observed state before executing. A decided proposal is retained so a repeated decision is refused rather than reported as missing. Secret-bearing arguments are masked at record time.

`TurnEngine` expresses the search confirmation handshake in this vocabulary. A search plan becomes a `ModelActionProposal` against `search-public-web` or `search-private-web`; a private plan produces an `approval_required` decision carrying an approval ID, and the user's confirmation, refusal, or silence on the next turn becomes an approval record, a denial, or a cancellation. `TurnContext.action_evidence` carries the records, and `_persist_artifact` writes proposals, authorization decisions, approval records, execution results, and cancellations into the turn artifact. Conversational behavior, prompts, and outcome strings are unchanged.

`backend/app/actions/boundaries.py` also declares the process and root isolation rules that file, workspace, shell, MCP, plugin, skill-script, and agent capabilities must satisfy before they can be registered. `ProcessBoundary` requires an explicit argv allowlist, an explicit environment allowlist rather than a wildcard, and a working root drawn from the declared storage roots, and it scrubs every environment key it did not allowlist so a parent-process secret cannot reach a child. The registry refuses a `privileged_execution` descriptor that omits these, and refuses any process-bearing capability that is not cancellable. Extension tool, skill-script, stdio MCP, and ACP capabilities now register these boundaries and execute through the shared action service.

The `/memory`, `/config/llm`, and `/config/operator` mutation routes now authorize and execute on one path. `CapabilityService.execute_operator_action` mints the proposal, authorizes it with `caller="operator_api"`, records an approval record only for approval-gated direct requests, records the execution result, and re-raises the owning service's typed error so route status codes and conflict payloads are unchanged. An operator request carries its own authority, so availability and readiness are recorded but do not gate: the owning service reports those conditions with more fidelity than a descriptor explanation can. Operator-configuration keys are surfaced for discovery rather than enforced in the input schema, because the service rejects unknown keys per field and reports them. Provider profile writes and provider selection changes are direct `allow` local writes; provider deletion, credential-store key rotation, and provider connectivity tests remain approval-gated. `backend/app/actions/catalog.py` classifies `memory-policy-update` and `extension-state-update` as direct `allow` local writes as well: both mutate only `data/`-rooted local storage (`data/memory/semantic/memory.sqlite` and the `extension_overlay` table in `data/operator.sqlite`), so approval added no evidence a local write already carries. `operator-config-write` remains approval-gated because it writes `.env` at the repo root, outside the `data/` boundary this reclassification covers.

Action evidence is durable. `backend/app/artifacts/storage.py` appends each record to `data/actions/action-log.jsonl` and fsyncs it, independent of any conversation session; the bounded in-memory audit remains only as the read path for `GET /actions/audit`. API-initiated actions can occur without an active session, so the action log is the durable evidence record for direct operator actions.

The desktop exposes the governed action loop. `desktop/src/components/actions-panel.js` renders capability discovery with live availability and its unavailable explanation, pending approvals with approve, deny, and cancel controls, execution status, and the audit list. It proxies through `desktop/src-tauri/src/backend.rs` and `lib.rs` commands, builds DOM without `innerHTML`, never calls the backend directly, and never infers whether a proposal can be approved from its status string — it submits and renders the backend's answer.

Explicit ACP sessions produce `delegated_runs` through `TurnEngine.run_extension`. Agent invocation routes through the governed capability path via `agent-invoke-{profile_id}` capability descriptors built from `AgentRegistry.to_capability_records()`.

Runtime test infrastructure validates the governed action path without live external services. `backend/tests/fixtures/search_providers.py` provides mock DDGS, SearXNG, and Tavily responses with configurable failure modes. `backend/tests/fixtures/action_governance.py` provides helpers for testing the full governed path (proposal, authorization, execution) with mock providers. `scripts/validate_backend.py` gained a `--mock` flag for the `runtime` subcommand to run mock-based tests alongside live ones.

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
- `backend/app/artifacts/storage.py`
- `desktop/src/components/actions-panel.js`
- `desktop/src/components/memory-panel.js`
- `desktop/src/api-client.js`
- `desktop/src/main.js`
- `desktop/src-tauri/src/backend.rs`
- `desktop/src-tauri/src/lib.rs`
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
- `backend/tests/unit/services/test_action_evidence_log.py`
- `desktop/tests/static.test.mjs`
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
- `backend/tests/fixtures/search_providers.py`
- `backend/tests/fixtures/action_governance.py`

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration` when action behavior crosses service/API boundaries
- `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families services --devices ...` for live external-provider validation claims
- `backend/.venv/Scripts/python scripts/validate_backend.py runtime --mock` for mock-based governed action tests
- `npm --prefix desktop test` for desktop action/config/memory/search contract changes
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml` for Tauri bridge changes; the static desktop suite matches command and route names as strings and never compiles them

Validation results (linux-amd64):
- `backend/.venv/bin/python scripts/validate_backend.py unit`: PASS, 1455 passed.
- `backend/.venv/bin/python scripts/validate_backend.py integration`: PASS, 17 passed, including actual local MCP and ACP SDK peers.
- `npm --prefix desktop test`: PASS.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS.

Validation results (windows-amd64):
- `backend\.venv\Scripts\python -m pytest backend\tests\unit\services\test_capability_service.py backend\tests\unit\api\test_llm_config_routes.py backend\tests\unit\services\test_llm_provider_profiles.py`: PASS, 51 passed. Covers provider profile write authorization, LLM config routes, and provider profile storage.
- `backend\.venv\Scripts\python -m pytest backend\tests\unit\actions\test_action_contracts.py backend\tests\unit\services\test_capability_service.py backend\tests\unit\services\test_extension_service.py backend\tests\unit\api\test_extension_routes.py backend\tests\unit\services\test_memory_service.py backend\tests\unit\api\test_memory_routes.py backend\tests\unit\api\test_action_routes.py`: PASS, 113 passed. Covers the `memory-policy-update` and `extension-state-update` reclassification to `allow`.
- `backend\.venv\Scripts\python scripts\validate_backend.py unit`: PASS, 1449 passed, 8 skipped. `backend/tests/unit/extensions/test_mcp_oauth.py::TestMcpOAuthTokenStore::test_file_permissions` is now skipped on `os.name == "nt"`, matching the existing Linux/POSIX-only skip convention used elsewhere in this suite; it asserts POSIX `0600` file-mode bits that Windows does not report the same way.

Protocol tests required execution outside the restricted runner because its asyncio
subprocess/thread I/O stalled. Live native desktop behavior, remote deployment,
and other host classes remain unverified. The declared process controls are not
an OS sandbox.

## Follow-up

- Continue the reclassification pass for the remaining capabilities not yet covered by the `data/`-write criterion: catalog inspection, health checks, credential entry for operator-selected local storage, and read-only discovery where no private data leaves the host. Keep evidence recording for governed actions, but require interrupting approval only for external writes, destructive local changes, privileged process execution, private-context transmission, and delegated external agent authority.
- Define any session-scoped or capability-scoped grant mechanism only after the full reclassification proves repeated approval prompts remain a concrete operator problem. Grants must be explicit, bounded, revocable, and visible in action evidence.
- Validate the fully revised posture through capability-service tests and desktop action/extension/operator flows before marking this ADR implemented.
