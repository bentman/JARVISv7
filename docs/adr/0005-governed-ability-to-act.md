# 0005 - Governed Ability to Act

Date: 2026-09-01
Status: Accepted
Related: 0002, 0003, 0004, 0006, 0007, 0008

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
- Preserve ADR 0002's turn ownership, ADR 0003's model/application authority boundary, and ADR 0004's memory lifecycle while action capability grows.

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

Operator-initiated UI workflows are already user requests. Adding a local MCP connection, storing a credential in the local operator secret store, importing an operator skill, changing an extension state, or editing a local profile should not ask the operator to approve their own request when the effect is local and non-destructive. The application still records proposal, authorization, and execution evidence internally. User-visible approval appears only when the requested operation crosses a risk boundary: external write, destructive local change, privileged process execution, private-context transmission, delegated external agent authority, cloud transmission, purchase, publication, or another hard-to-reverse effect.

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

This ADR is partially implemented. The shared action mechanics are in place and the approval-posture reclassification described in the Decision Outcome is complete for every capability the catalog currently declares. What remains is the operator/audit presentation that keeps governed-action records inspectable while dedicated extension and agent workflows use the same action service instead of making the raw Actions panel the normal user path.

`backend/app/actions/contracts.py` owns the posture. `APPROVAL_EFFECT_CLASSES` names the classes that require an interrupting decision - `external_write`, `cloud_model`, `privileged_execution`, and `destructive_action` - and `default_authorization` maps an effect class to its rule. `backend/app/actions/catalog.py` and `backend/app/services/extension_runtime_service.py` both derive their descriptors from it, so the built-in catalog and extension bindings cannot drift apart. Exactly two capabilities override it, each because the effect class alone cannot express the reason: `search-private-web` is an outbound read that carries the user's own context off the machine, and plugin installation writes only under `data/` but places new executable definitions on the host that then register privileged capabilities.

Search is the clearest implemented governed action path. `SearchIntentResolver` detects explicit search intent, rejects secrets, asks for confirmation before private outbound queries, limits query count, and emits a structured `SearchPlan`. `SearchService` executes provider attempts, records sources and limitations, supports cancellation, and returns `SearchEvidence`. `TurnEngine` records search evidence, provider names, cancellation, failure phase, and final state in the turn artifact.

Provider routing is partially governed action. `LLMProviderProfileStore` owns provider profiles, cloud eligibility, endpoint validation, selection, encrypted API keys, and secret-key rotation. `RoutedLLM` uses explicit cloud requests, configured local fallback, cloud escalation policy, and failure classification before trying another provider. Runtime context records provider attempt evidence.

Memory lifecycle actions are governed through services. `/memory` exposes policy, inspection, confirm, correct, dispute, forget, and curation status through `MemoryService`. Operations use revision checks and lifecycle events. Desktop requests those actions through backend/Tauri APIs.

Settings and provider configuration are explicit backend actions. Operator configuration writes are limited to allowlisted fields. Secret values are masked in responses. Provider profile edits reject built-in profile edits, compatibility-profile edits, invalid endpoints, and deletion of selected provider profiles.

Prompt and artifact boundaries reserve action evidence. `PromptEnvelope` has `tool` authority and `tool_result` content type. Renderers mark tool results as untrusted context. `TurnArtifact` records `tools_invoked`, `action_proposals`, `authorization_decisions`, `approval_records`, `action_execution_results`, `action_cancellations`, `delegated_runs`, search evidence, runtime context, retrieved memory evidence, failure state, and phase timings.

The shared action contract is wired. `backend/app/actions/contracts.py` defines `CapabilityDescriptor`, `ModelActionProposal`, `AuthorizationContext`, `AuthorizationDecision`, `ApprovalAuditRecord`, `ExecutionResultRecord`, `ActionCancellationRecord`, `ActionEvidence`, and `CapabilityRegistry`. Descriptors declare an approval mode of `turn_boundary` or `same_turn`. The registry validates effect classes, readiness states, availability states, authorization rules, timeout/cancellation/result schema metadata, unavailable explanations, sorted snapshots, duplicate capability IDs, untrusted metadata claims, execution boundaries, and JSON Schema validation without remote schema fetching. Authorization denies unregistered capabilities, arguments the input schema rejects, unavailable readiness, unavailable capabilities, denied rules, and unapproved capabilities that require approval.

`backend/app/actions/catalog.py` builds thirteen descriptors for search, memory lifecycle, provider configuration, and operator configuration from a `CapabilityObservation` of live state: enabled search providers, memory-service and curation presence, provider secret-store lock state and per-profile `readiness_state`, and `.env` presence. `CapabilityService` re-observes on every catalog read and proposal, so readiness and availability are observations rather than static claims.

`backend/app/actions/boundaries.py` declares the execution boundary rules: allowed storage roots limited to the existing `data/`, `cache/`, `reports/`, `models/`, and `runtimes/` roots, a wall-clock timeout ceiling, a cancellation contract, and a result-size bound. `run_bounded` enforces the deadline, the cancellation signal, and the result bound, and `ExecutionBoundary.resolve_path` refuses paths that escape the declared roots. The registry refuses to register a `privileged_execution` capability that does not declare these boundaries.

`backend/app/services/capability_service.py` owns proposal, authorization, approval, execution, cancellation, and audit. Only a parked proposal retains its `AuthorizationContext`; a proposal that is denied or executed in the same call drops it when the call returns, so the store stays bounded by the pending TTL rather than by process lifetime. `same_turn` capabilities execute inside the HTTP request through `/actions`; approval-required proposals park in a bounded in-memory store, and approval re-runs the authorization ladder against freshly observed state before executing. A decided proposal is retained so a repeated decision is refused rather than reported as missing. Secret-bearing arguments are masked at record time.

`TurnEngine` expresses the search confirmation handshake in this vocabulary. A search plan becomes a `ModelActionProposal` against `search-public-web` or `search-private-web`; a private plan produces an `approval_required` decision carrying an approval ID, and the user's confirmation, refusal, or silence on the next turn becomes an approval record, a denial, or a cancellation. `TurnContext.action_evidence` carries the records, and `_persist_artifact` writes proposals, authorization decisions, approval records, execution results, and cancellations into the turn artifact. Conversational behavior, prompts, and outcome strings are unchanged.

`backend/app/actions/boundaries.py` also declares the process and root isolation rules that file, workspace, shell, MCP, plugin, skill-script, and agent capabilities must satisfy before they can be registered. `ProcessBoundary` requires an explicit argv allowlist, an explicit environment allowlist rather than a wildcard, and a working root drawn from the declared storage roots, and it scrubs every environment key it did not allowlist so a parent-process secret cannot reach a child. The registry refuses a `privileged_execution` descriptor that omits these, and refuses any process-bearing capability that is not cancellable. Extension tool, skill-script, stdio MCP, and ACP capabilities register these boundaries and execute through the shared action service.

The `/memory`, `/config/llm`, and `/config/operator` mutation routes authorize and execute on one path. `CapabilityService.execute_operator_action` mints the proposal, authorizes it with `caller="operator_api"`, records an approval record only for approval-gated direct requests, records the execution result, and re-raises the owning service's typed error so route status codes and conflict payloads are unchanged. An operator request carries its own authority, so availability and readiness are recorded but do not gate: the owning service reports those conditions with more fidelity than a descriptor explanation can. Operator-configuration keys are surfaced for discovery rather than enforced in the input schema, because the service rejects unknown keys per field and reports them. Local reads, local writes, and outbound reads run directly and record evidence: provider profile writes, provider selection, memory confirm/dispute/correct, `memory-policy-update`, `extension-state-update`, `extension-credential-write`, `extension-input-answer`, remote MCP discovery, and `operator-config-write`. `operator-config-write` writes `.env` at the repo root rather than under `data/`, but it accepts only the allowlisted `OPERATOR_FIELD_SPECS` keys, rejects the rest per field with a reason, masks secret values at record time, and is reversible; an interrupting approval adds no evidence the recorded local write does not already carry. Approval still gates memory forget, provider profile deletion, credential-store key rotation, remote MCP tool calls, plugin installation, and every `privileged_execution` capability.

`provider-connectivity-test` is a governed action rather than a declared-only descriptor. `POST /config/llm/profiles/{profile_id}/test` executes through `execute_operator_action`, so a provider health check leaves the same proposal, decision, and execution record as any other action; its availability follows provider-store presence rather than the presence of a cloud profile, because a local-only host can test a local endpoint.

Re-observation is cheap enough to stay on the hot path. `refresh` runs on every catalog read, proposal, approval, and direct operator action. A schema's validity is a property of the schema, not of the observation, so `validate_schema` memoizes that check on the encoded schema: `refresh` measures 0.98 ms and `catalog` 1.52 ms per call, while readiness and availability stay freshly observed.

The declared timeout means one thing on both paths. `bounded_deadline` in `backend/app/actions/boundaries.py` arms an operation's deadline, `run_bounded` uses it for proposals, and `CapabilityService.execute_operator_action` arms it for direct operator actions too, so timeout evidence comes from the shared cancellation signal.

Action evidence is bounded as well as durable. `append_action_event` rotates `data/actions/action-log.jsonl` to `action-log.1.jsonl` past `ACTION_LOG_MAX_BYTES`, and `read_action_events` reads the archive before the live file, so the log cannot grow without limit and a roll keeps the older evidence instead of truncating it.

One malformed descriptor does not take the governed loop offline. `CapabilityService.refresh` registers descriptors individually, records the ones the registry refuses as `{capability_id, reason}` problems, and serves the rest; `GET /actions/capabilities` returns those problems beside the catalog so a refused capability is explained rather than hidden.

Agent profiles are an observation, not a startup snapshot. `AgentRegistry` re-reads `config/agents/` when the directory's file set or mtimes change, loads each profile independently, and reports the ones it cannot parse through `errors()`; `observe_capabilities` carries those into `CapabilityObservation.agent_errors` and `refresh` merges them into the catalog's `problems`. A profile that does not declare the `direct` invocation mode - the only mode the current runtime executes - is served as `misconfigured` with that explanation instead of as a capability that always fails.

`CapabilityService.bind_handler_provider` binds executors for descriptors another source already owns, re-read on every refresh. It exists so a capability whose descriptor is rebuilt from live observation cannot be served without its executor; `backend/app/agents/registry.py` builds the `agent-invoke-*` descriptors and ADR 0007 owns what they execute, and `build_extension_handlers` binds `extension-state-update` to `ExtensionService.set_state` with the optional `expected_revision` and `reason` the route already accepted.

Every capability the operator surface offers is drivable through either a bound handler or a named route owner. `build_capability_handlers` binds `provider-connectivity-test`. The two route-owned exceptions are declared explicitly: `extension-input-answer` and `extension-credential-write` register with no generic executor, because one needs a live run's pending request and the other carries a secret value that must not travel through generic proposal arguments; their `execution_owner` names the route that drives them.

Action evidence is durable. `backend/app/artifacts/storage.py` appends each record to `data/actions/action-log.jsonl` and fsyncs it, independent of any conversation session; the bounded in-memory audit remains only as the read path for `GET /actions/audit`. API-initiated actions can occur without an active session, so the action log is the durable evidence record for direct operator actions.

The desktop exposes the governed action loop. `desktop/src/components/actions-panel.js` renders capability discovery with live availability and its unavailable explanation, pending approvals with approve, deny, and cancel controls, execution status, the audit list, and the catalog's registration problems. An operator can also originate an action: a capability the backend reports as `executable`, `available`, and not `turn_boundary` offers a control that builds one typed input per declared `input_schema` property and sends the coerced arguments through `POST /actions/propose`. `proposeTriggerLabel` names that control `Run` for an `allow` capability and `Propose` only for one whose `authorization_rule` is `requires_approval`, since an `allow` capability executes immediately and has no decision to name as a proposal; either way, submitting selects the resulting record so its outcome is visible immediately. Audit rows select their proposal, so a completed action stays inspectable after it leaves the pending list. A capability with no proposable executor names its `execution_owner` instead of reading as broken. It proxies through `desktop/src-tauri/src/backend.rs` and `lib.rs` commands, builds DOM without `innerHTML`, never calls the backend directly, and never infers whether a proposal can be approved from its status string — it submits and renders the backend's answer.

Explicit ACP sessions produce `delegated_runs` through `TurnEngine.run_extension`. Agent invocation uses this loop through `agent-invoke-{profile_id}` descriptors; ADR 0007 owns that path.

`desktop/src/components/actions-panel.js` presents `allow` and `requires_approval` capabilities differently. `formatCapabilityApproval` returns no approval text for an `allow` capability and `"requires approval"` for one whose `authorization_rule` is `requires_approval`, and `proposeTriggerLabel` names the control `Run` for the former and `Propose` for the latter. Capability classification remains backend-owned: `memory-policy-update`, `extension-state-update`, `extension-credential-write`, and `extension-definition-write` are `allow`. Dedicated workflows in ADR 0006 and ADR 0007 may originate those same capabilities without making the Actions panel the normal operator path.

`backend/tests/unit/actions/test_action_catalog.py` proves the reclassification directly against `build_descriptors` rather than against individual routes: every capability whose effect class is `local_read`, `local_write`, or `external_read` is `allow` except the one named override (`search-private-web`), and the destructive/private-context capabilities that must still gate stay `requires_approval`. This is a regression guard - a future capability added to `catalog.py` with a local/read effect class fails the test unless its authorization is explicitly overridden with a stated reason, the same way `search-private-web` and plugin installation already are.

Runtime test infrastructure validates the governed action path without live external services. `backend/tests/fixtures/search_providers.py` provides mock DDGS, SearXNG, and Tavily responses with configurable failure modes. `backend/tests/fixtures/action_governance.py` provides helpers for testing the full governed path (proposal, authorization, execution) with mock providers. `scripts/validate_backend.py` gained a `--mock` flag for the `runtime` subcommand to run mock-based tests alongside live ones.

## Confirmation

Implementation files:
- `backend/app/actions/contracts.py`
- `backend/app/api/routes/llm_config.py`
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
- `backend/tests/unit/actions/test_action_catalog.py`
- `backend/tests/unit/actions/test_action_contracts.py`
- `backend/tests/unit/actions/test_action_boundaries.py`
- `backend/tests/unit/services/test_capability_service.py`
- `backend/tests/unit/api/test_action_routes.py`
- `backend/tests/unit/api/test_llm_config_routes.py`
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
- `backend/.venv/bin/python scripts/validate_backend.py unit`: PASS, 1482 passed.
- `backend/.venv/bin/python scripts/validate_backend.py integration`: PASS, 17 passed, including actual local MCP and ACP SDK peers.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS.
- `backend/.venv/bin/python -m ruff check backend/app backend/tests scripts`: PASS, `All checks passed!`.
- `backend/.venv/bin/python scripts/run_backend.py --host 127.0.0.1 --port 8736` on shipped defaults: PASS. `GET /readiness` -> `status: ready`, `builtin:managed-llama-cpp`, `gpu.cuda`; `POST /task/text` -> `WORKING`; `POST /agents/invoke` -> real agent response; `GET /actions/capabilities` -> 17 capabilities, `problems: []`.
- `npm --prefix desktop run tauri build -- --no-bundle`: PASS. `Built application at: desktop/src-tauri/target/release/jarvisv7-desktop`; the binary launches a WebKitGTK window under WSLg.

Validation results (windows-amd64):
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers `formatCapabilityApproval` and `proposeTriggerLabel` for both `allow` and `requires_approval` capabilities, and the rendered `Run`/`Propose` control split in `actions-panel.js`.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side source changed for this validation scope.
- `backend\.venv\Scripts\python -m pytest backend\tests\unit\services\test_capability_service.py backend\tests\unit\api\test_llm_config_routes.py backend\tests\unit\services\test_llm_provider_profiles.py`: PASS, 51 passed. Covers provider profile write authorization, LLM config routes, and provider profile storage.
- `backend\.venv\Scripts\python -m pytest backend\tests\unit\actions\test_action_contracts.py backend\tests\unit\services\test_capability_service.py backend\tests\unit\services\test_extension_service.py backend\tests\unit\api\test_extension_routes.py backend\tests\unit\services\test_memory_service.py backend\tests\unit\api\test_memory_routes.py backend\tests\unit\api\test_action_routes.py`: PASS, 113 passed. Covers the `memory-policy-update` and `extension-state-update` reclassification to `allow`.
- `backend\.venv\Scripts\python -m pytest backend\tests\unit\actions backend\tests\unit\services\test_capability_service.py backend\tests\unit\services\test_extension_service.py backend\tests\unit\api\test_action_routes.py backend\tests\unit\api\test_extension_routes.py backend\tests\integration\test_extension_runtime.py`: PASS, 195 passed, 1 skipped. Covers `test_action_catalog.py`'s reclassification proof for `extension-definition-write`, `extension-definition-delete`, `extension-skill-write`, and `extension-skill-delete`, and the existing operator-owned MCP/skill create-remove integration flows.
- `backend\.venv\Scripts\python scripts\validate_backend.py unit`: PASS, 1521 passed, 7 skipped.

The posture was driven end to end against a live backend on `127.0.0.1:8765` (`linux-amd64`):

- `GET /actions/capabilities`: 17 capabilities, `problems` empty; `operator-config-write`,
  `provider-connectivity-test`, `extension-state-update`, and `agent-invoke-summarizer` report
  `allow`, and every `same_turn` capability except the two endpoint-only extension entries
  reports `executable: true`.
- `POST /actions/propose` for `operator-config-write`: executed directly, no approval,
  `{"written": ["USE_DDGS"], "rejected": []}`. `.env` was returned to its shipped value
  through the same route afterwards.
- `POST /actions/propose` for `provider-secret-rotate`: parked as `awaiting_approval`, appeared
  in `GET /actions/pending`, executed on `POST /actions/{id}/decision`, and a second decision
  on the same proposal returned `409`.
- `POST /actions/propose` for `provider-connectivity-test` and `extension-state-update`: both
  executed through application-owned executors.
- `POST /config/llm/profiles/{id}/test`: recorded a proposal, decision, and execution result.
- A secret submitted as `TAVILY_API_KEY` appears zero times in `data/actions/action-log.jsonl`
  and zero times in `GET /actions/audit`.

The governed loop was exercised on an assistant that actually serves. The default startup path
depends on these readiness guarantees:

- `.env.example` keeps `LLAMA_CPP_MANAGED` present but blank, preserving
  `Settings.effective_llama_cpp_managed`'s fallback to `use_local_model`.
- `backend/app/models/llm_profiles.py` owns `server_origin` and `openai_api_base`, which
  `local_llm_startup.py`, `local_llm_sidecar.py`, and
  `backend/app/runtimes/llm/local_runtime.py` all use, so sidecar probes do not rebuild an
  OpenAI API base as a server root.
- `GET /readiness` degrades when any of `REQUIRED_FAMILIES` is unready.

With shipped defaults, `backend/.venv/bin/python scripts/run_backend.py`
reports `status: ready` with `builtin:managed-llama-cpp` on `gpu.cuda`, `POST /task/text`
returns real model output, `POST /agents/invoke` returns a real agent response, and
`GET /actions/capabilities` serves 17 capabilities with no problems.

Live, with no restart between steps: a malformed `config/agents/*.yaml` was reported under
`problems` with its validation reason while every other capability stayed `available`; a profile
declaring only `as_tool` was served `misconfigured` and its invocation denied with that reason;
a `strict` profile registered as an approval-gated local write, parked, and appeared in
`GET /actions/pending`; and removing the scratch files cleared `problems` on the next read.

Protocol tests required execution outside the restricted runner because its asyncio
subprocess/thread I/O stalled. The desktop binary was launched but its window was not driven
or captured from this host; the panel's rendered DOM and the propose interaction are covered
by `desktop/tests/static.test.mjs` instead. The `windows-amd64` results above record the local
re-run.
Native visible desktop validation remains the open evidence gap. The declared process controls
are not an OS sandbox.

## Follow-up

- Complete the governed-action audit/debug presentation in the Actions surface. Proposal, authorization decision, approval record, execution result, cancellation, descriptor problem, unavailable-state, and definition-fingerprint evidence must remain inspectable without becoming the primary operator workflow for extension or agent families. Raw IDs and backend record fields should sit behind explicit detail/audit controls with operator-readable summaries.
- Keep the generic schema-driven action runner as an audit/debug and fallback surface only. Dedicated extension workflows belong to ADR 0006, and dedicated agent/ACP workflows belong to ADR 0007; those workflows must call the same ADR 0005 capability records instead of bypassing the action service.
- Mark this ADR implemented once current backend closeout evidence and desktop action tests prove direct `allow` actions run without self-approval, approval-required actions park, approve, deny, and cancel correctly, and action evidence remains available while dedicated extension and agent workflows provide the normal operator path. Native operator layout and interaction validation belongs to ADR 0008.
