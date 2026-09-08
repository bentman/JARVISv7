# 0006 - Ways to Extend Assistant Ability to Act

Date: 2026-09-01
Status: Accepted
Related: 0002, 0003, 0004, 0005, 0007

## Context and Problem Statement

JARVISv7 needs reusable ways to extend what the assistant can know, configure, invoke, and do without creating a separate trust model for every new feature.

The project already has several extension-like surfaces: operator settings, personality profiles, model provider profiles, search providers, prompt authority boundaries, action contract records, and turn artifacts. Those are useful foundations, but they do not yet form one general extension system.

Future extension families may include reusable prompts, skills, MCP connections, hooks, plugins, connectors, and delegated agents. Some of those only shape context or operator choice; others can read private data, send data outward, mutate state, run code, or delegate work. The architecture needs one way to classify those surfaces and one governed execution path for anything with side effects.

## Decision Drivers

- Keep extension labels distinct by function so settings, prompts, skills, tools, providers, hooks, plugins, MCP connections, and agents do not collapse into one vague abstraction.
- Preserve ADR 0002's single interaction loop, ADR 0003's authority boundaries, ADR 0004's memory boundaries, and ADR 0005's governed action model.
- Make low-risk extension surfaces ergonomic while routing executable or externally visible effects through explicit capability records.
- Track provenance, trust, readiness, enablement, health, dependency state, and collisions before broad model-callable extension exposure.
- Keep the desktop a thin surface over backend-owned policy, registry, execution, artifacts, and API contracts.

## Decision Outcome

JARVISv7 will define extension shapes by function first:

- settings: scoped operator choices and defaults
- instructions/personality: behavior and style guidance
- reusable prompts: templates for recurring work starts
- skills: portable procedural bundles
- tools/capabilities: executable actions with schema, readiness, authorization, result, and artifact evidence
- MCP connections: external resources, prompts, and tools exposed through a host-controlled connection boundary
- ACP agents/clients: agent process and client-session interoperability for delegated assistants and future client surfaces
- hooks: deterministic lifecycle actions tied to visible events
- plugins: installable packages that bundle one or more extension shapes
- providers/connectors: named model, service, or external-account relationships with readiness, credentials, and permission boundaries

No extension shape gets a parallel execution path. If it reads private data, sends data outward, mutates state, runs code, delegates to an agent, or calls a service, it must become or invoke a governed capability record and use the shared authorization, approval, cancellation, artifact, and memory flow.

## Consequences

Positive:
- Extension work can proceed without inventing a new trust model per feature.
- MCP, ACP, skills, hooks, plugins, prompts, settings, providers, and tools remain distinguishable.
- External metadata can support discovery without granting itself authority.
- Desktop, scripts, daemon flows, and future clients can share backend-owned policy and artifacts.

Negative:
- A real extension system requires shared registry, lifecycle, authorization, and artifact infrastructure before broad tool use is enabled.
- Provider-native tool and MCP features may need wrapping before they fit v7's evidence model.
- Skill and plugin imports require provenance tracking so user-authored or external code does not look application-owned.
- ACP integration adds process and session state that must stay aligned with the single interaction loop.
- Hook behavior can become surprising unless event names, effects, and failure paths stay small and visible.

## Implementation

This ADR is partially implemented. The backend extension catalog, governed runtime, MCP
authorization path, turn-engine capability selection, and raw desktop surfaces exist. The operator
experience is not complete because extension families are still exposed through internal capability
names and schema forms instead of human-familiar workflows.

Implemented foundations:
- Operator settings are scoped and classified through `backend/app/core/settings.py`. `backend/app/services/operator_config_service.py` owns the operator field allowlist and secret masking; `backend/app/api/routes/config.py` and `backend/app/api/schemas/config.py` are the route surface over it. Operator writes are allowlisted, and secrets are masked.
- Personality profiles are structured YAML under `config/personality/`. `backend/app/personality/schema.py`, `backend/app/personality/loader.py`, and `backend/app/personality/policy.py` reject authority-bearing fields such as tool policy, routing policy, memory policy, hidden instructions, and safety overrides.
- Personality selection is exposed through backend routes and schemas in `backend/app/api/routes/personality.py` and `backend/app/api/schemas/personality.py`.
- Prompt boundaries exist through `backend/app/cognition/prompt_envelope.py`, `backend/app/cognition/prompt_assembler.py`, `backend/app/cognition/prompt_renderer.py`, and `backend/app/cognition/prompt_chat_renderer.py`. Prompt segments carry authority labels, content type, and trust state.
- Provider profiles are implemented through `backend/app/services/llm_provider_profiles.py`, `backend/app/services/llm_provider_service.py`, `backend/app/api/routes/llm_config.py`, and `backend/app/api/schemas/llm_config.py`.
- Search providers are implemented as governed external-read behavior through `backend/app/cognition/search_policy.py`, `backend/app/services/search_service.py`, and `backend/app/runtimes/internetsearch/`.
- Action governance records exist in `backend/app/actions/contracts.py`: capability descriptors, availability/readiness/effect classes, approval modes, model proposals, authorization decisions, approval records, execution results, action cancellation records, the action evidence accumulator, metadata claims, and collision checks. `CapabilityRegistry` enforces execution boundaries and JSON Schema validity at registration, and refuses any descriptor that fails them.
- Turn artifacts carry action, search, memory, runtime, and failure evidence. `TurnEngine.run_extension` admits explicit ACP requests through the existing turn lock and writes `delegated_runs`; remote output is retained as evidence without automatic memory promotion.
- Desktop surfaces call backend APIs for settings, provider profiles, search evidence, personality selection, and governed action discovery, approval, execution status, cancellation, and audit through `desktop/src/api-client.js`, `desktop/src/components/settings-panel.js`, `desktop/src/components/llm-provider-settings.js`, `desktop/src/components/search-evidence.js`, `desktop/src/components/actions-panel.js`, `desktop/src/main.js`, and `desktop/src-tauri/src/backend.rs`.
- The shared governed execution path this ADR depends on is built. ADR 0005 supplies one authorization ladder, an approval flow with declared modes, durable action evidence, and boundary rules the registry enforces before a capability can be registered. Every remaining extension shape attaches to that path rather than defining its own.

- One backend-owned extension catalog exists in `backend/app/extensions/`. `ExtensionDescriptor` carries a stable `<family>:<local_id>` identifier, version, source, provenance, trust status, state, readiness, availability, dependencies, collisions, and untrusted metadata claims. Built-in and declarative families register alongside settings, personality profiles, provider profiles, search providers, prompt templates, skills, and governed action descriptors.
- The catalog observes each family live and persists only what an operator decided and the catalog cannot re-derive. `extension_overlay` and `extension_event` in `data/operator.sqlite` hold enabled state, trust, and the retirement audit trail behind a schema migration; health, dependencies, version, provenance, and collisions are derived per read so a stale row cannot claim to be healthy.
- Enabling, disabling, or retiring an extension is a governed action. It routes through the ADR 0005 capability executor as `extension-state-update`, so it produces the same proposal, approval, and execution evidence as every other operator mutation.
- Prompt templates are discoverable through `backend/app/extensions/prompts.py` and `config/prompts/`. A template may only declare `user` or `session` authority, so a reusable prompt cannot become hidden policy.
- Declarative extension defaults are tracked under `config/extensions/{acp,mcp,hooks,plugins,skills,tools}` and operator additions are untracked under `data/extensions/{family}`. Discovery gives application defaults precedence for duplicate family/IDs and records application versus operator provenance and trust. Skills support both roots with progressive disclosure; the tracked `inspect-extensions` skill is instruction-only, while operator skills remain external.
- A skill's `requested_tools` is recorded as an untrusted metadata claim, never a grant, and a skill declaring any authority-bearing field is rejected. Declared scripts resolve only through governed process execution.
- Hook and plugin lifecycles and runners exist in `backend/app/extensions/{hooks,plugins}.py`: closed hook event names, effect classes reused from ADR 0005, application-owned `record_event`, governed capability dispatch, bounded plugin installation, bundle hashing, and child-definition validation.
- MCP connection management exists in `backend/app/extensions/mcp.py` with official SDK transport, discovery, schema-preserving records, health, credential references, allowlists, elicitation, cancellation, and host authorization callbacks. ACP subprocess sessions exist in `backend/app/extensions/acp.py` with official SDK permission callbacks, progress/session events, cancellation, process boundaries, and cleanup. What this ADR owns is the governed process boundary those sessions run behind; ADR 0007 owns Agent Client Protocol conformance.
- Backend API and desktop surfaces exist through `backend/app/api/routes/extensions.py` and `desktop/src/components/extensions-panel.js`, covering catalog discovery, load errors, detail, progressive body disclosure, and state changes.

- `ExtensionRuntimeService` registers extension operations with the shared capability service. Approvals bind a definition fingerprint; changed definitions require a new proposal. `ExtensionRuns` persists run state and marks interrupted work after restart without replaying effects.
- The current desktop exposes invocation, approvals, run progress, cancellation, credentials, and structured elicitation through raw extension detail surfaces. Approval requests run off the native UI thread so nested input remains usable, but these controls are implementation-facing and need the operator-familiar follow-up below.

Declarative definitions and their initial tracked defaults are documented in
`config/extensions/README.md`. The disabled application hook default records
no events until explicitly enabled. ACP bridge execution is implemented behind
the governed process/action boundary.

A local inbound bridge exists in `backend/app/extensions/acp_server.py`. It accepts client connections over loopback TCP using JSON-RPC 2.0, manages session lifecycle with configurable maximum sessions and timeouts, and routes incoming messages through `TurnEngine.run_text_turn()`, so an external client enters the same single interaction loop as every other surface. Start, stop, status, and session-list endpoints are exposed through `backend/app/api/routes/acp_server.py`. It is a local bridge; protocol conformance for external agent clients belongs to ADR 0007.

MCP credentials support the OAuth 2.0 authorization code flow and resolve on the live connection
path. `backend/app/extensions/mcp_oauth.py` provides `McpOAuthConfig`, `McpOAuthFlow`
(authorization URL generation, code exchange, token refresh, local callback server), and
authorization-server discovery. The code verifier is held against the state it was minted with and
consumed once, so it never travels through the browser and an unknown or replayed state cannot
redeem a code. Authorization and token requests carry the RFC 8707 `resource` parameter, binding a
token to one MCP server. When a connection declares no `authorization_url` and `token_url`, they are
discovered through RFC 9728 protected-resource metadata and RFC 8414 authorization-server metadata;
an explicit endpoint overrides discovery. Tokens persist in the application's encrypted operator
secret store and refresh when expired.

`ExtensionRuntimeService.mcp_credentials` is the single host-owned credential resolver for MCP.
An OAuth connection resolves a bearer token there; a connection with no stored authorization is
refused rather than connected unauthenticated. Because `ProcessBoundary.scrub_environment` is an
allowlist, a stdio credential absent from the connection's `env_passthrough` is refused rather than
silently dropped into an unauthenticated server start.

Operator-owned declarative definitions are created and removed through governed actions rather
than by hand-editing YAML. `extension-definition-write` and `extension-definition-delete` route
through the ADR 0005 executor and write into `data/extensions/{family}`, the location discovery
already reads, so provenance, trust, precedence, and collision reporting are unchanged. A
definition is parsed and family-validated before it reaches disk, so a malformed connection is
refused with its reason instead of persisted; an application definition of the same family and id
keeps precedence and is never overwritten.

MCP discovery snapshots persist in `mcp_discovery_snapshot` behind a schema migration, so
discovered tools, resources, and prompts remain proposable after a restart instead of silently
retracting until rediscovery. Stored health is not replayed as a live claim: a snapshot restored
from disk reports `unknown` until the connection is contacted again.

The turn engine selects extension capabilities natively. `LLMBase.generate_with_tools` offers
eligible operations to the model; `backend/app/cognition/tool_policy.py` bounds the offer to what
fits the context window and grounds a result back as an untrusted `tool_result` segment. Selection
is offered only for operations the ladder could allow: available, ready, non-denied, extension-owned
operations. ACP operations are excluded because they execute through `TurnEngine.run_extension`,
which re-acquires the single turn lock ADR 0002 owns.

`CapabilityService.execute_authorized` is the turn-scoped entry point. It re-runs the ADR 0005
ladder against current state, re-checks the definition fingerprint bound at approval, and executes
through the same `_run` implementation the operator API uses, so there is one execution path and one
evidence trail. The operator API keeps refusing `turn_boundary` capabilities: that guard protects
the API edge, where no turn lock, turn artifact, or conversational approval channel exists.

Approval is conversational. A capability whose effect class requires it is proposed, parked, and
described to the user; a confirming reply on the next turn records the approval and executes, a
declining reply records the denial, and any other reply lapses the approval as a turn-boundary
cancellation. The parked capability travels with its approval reference, so no resolver assumes
which capability was parked. One capability runs per turn; a second round is an agent loop, which
ADR 0007 owns. An extension that blocks for operator input is refused inside a turn and directed to
the Extensions panel rather than stalling the turn until its deadline.

The desktop drives the OAuth connection flow without ever handling a secret. `GET`, `authorize`,
and `complete` routes under `/extensions/{id}/oauth` report configuration and authorization state,
return the authorization URL, and exchange the code. The verifier and state stay on the backend, and
a completion whose state does not match the request it answers is refused. The Extensions panel
shows authorization state, opens the authorization page, and accepts the returned code. The MCP
credential form no longer sits behind discovered operations, so a server that demands authorization
before it will answer discovery can still be credentialed. Cancelling a run is confirmed.

An OAuth block could not previously be declared at all: the definition parser's secret-key heuristic
rejected `authorization_url` and `token_url`. Keys ending in `_url` name a public endpoint and are
no longer treated as secret-bearing, while an inline `client_secret` is still refused and must use a
credential reference.

Operator-owned skills are imported, edited, and removed through `extension-skill-write` and
`extension-skill-delete`. The manifest is parsed before it is written, so a skill declaring an
authority-bearing field is refused with its reason rather than landing on disk, and an application
skill of the same id is never overwritten. The desktop gates skill editing on provenance, because an
operator skill is external-trust by design; trust does not indicate ownership.

`extension-credential-write` already executes through its own dedicated route (`POST
/extensions/{id}/credentials`) with no proposal or approval step at all, so operator-requested
credential storage was never gated by the capability-console ceremony. `extension-definition-write`
and `extension-definition-delete` have no dedicated route yet; ADR 0005's Actions panel is still the
only way to reach them, but that panel no longer labels an `allow` capability `Propose` awaiting
`approved here` - it now reads `Run`, with nothing implying a decision that never happens. That fixes
the approval-prompt appearance this ADR's Follow-up calls out; the still-open work is the dedicated
Add MCP Connection/Edit MCP Connection flow itself, so `extension-definition-write` has a home other
than the shared Actions panel.

Three modules remain adjacent to but distinct from the extension catalog. `backend/app/core/capabilities.py` only describes hardware/runtime capability flags. `backend/app/actions/catalog.py` builds ADR 0005 governed capability descriptors from observed runtime state. `backend/app/models/catalog.py` is the model artifact catalog. None of them carries extension provenance, trust status, enablement, or dependency state.

## Confirmation

Implementation evidence:

- `ProjectVision.md`
- `backend/app/core/settings.py`
- `backend/app/api/routes/config.py`
- `backend/app/api/schemas/config.py`
- `backend/app/personality/schema.py`
- `backend/app/personality/loader.py`
- `backend/app/personality/policy.py`
- `backend/app/api/routes/personality.py`
- `backend/app/api/schemas/personality.py`
- `config/personality/README.md`
- `backend/app/cognition/prompt_envelope.py`
- `backend/app/cognition/prompt_assembler.py`
- `backend/app/cognition/prompt_renderer.py`
- `backend/app/cognition/prompt_chat_renderer.py`
- `backend/app/cognition/tool_policy.py`
- `backend/app/runtimes/llm/base.py`
- `backend/app/routing/provider_router.py`
- `backend/app/services/llm_provider_profiles.py`
- `backend/app/services/llm_provider_service.py`
- `backend/app/api/routes/llm_config.py`
- `backend/app/api/schemas/llm_config.py`
- `backend/app/cognition/search_policy.py`
- `backend/app/services/search_service.py`
- `backend/app/runtimes/internetsearch/`
- `backend/app/conversation/engine.py`
- `backend/app/artifacts/turn_artifact.py`
- `backend/app/actions/contracts.py`
- `backend/app/actions/boundaries.py`
- `backend/app/extensions/contracts.py`
- `backend/app/extensions/catalog.py`
- `backend/app/extensions/lifecycle.py`
- `backend/app/extensions/prompts.py`
- `backend/app/extensions/skills.py`
- `backend/app/extensions/store.py`
- `backend/app/services/extension_service.py`
- `backend/app/api/routes/extensions.py`
- `backend/app/api/schemas/extensions.py`
- `config/prompts/`
- `backend/app/actions/catalog.py`
- `backend/app/services/capability_service.py`
- `backend/app/services/operator_config_service.py`
- `backend/app/api/routes/actions.py`
- `backend/app/api/schemas/actions.py`
- `backend/app/core/capabilities.py`
- `backend/app/models/catalog.py`
- `desktop/src/api-client.js`
- `desktop/src/components/settings-panel.js`
- `desktop/src/components/llm-provider-settings.js`
- `desktop/src/components/search-evidence.js`
- `desktop/src/components/actions-panel.js`
- `desktop/src/components/extensions-panel.js`
- `desktop/src/main.js`
- `desktop/src-tauri/src/backend.rs`

Validation evidence:

- `backend/tests/unit/core/test_settings.py`
- `backend/tests/unit/personality/test_personality.py`
- `backend/tests/unit/api/test_routes.py`
- `backend/tests/unit/api/test_llm_config_routes.py`
- `backend/tests/unit/services/test_llm_provider_profiles.py`
- `backend/tests/unit/services/test_llm_provider_service.py`
- `backend/tests/unit/cognition/test_prompt_assembler.py`
- `backend/tests/unit/cognition/test_search_policy.py`
- `backend/tests/unit/services/test_search_service.py`
- `backend/tests/unit/runtimes/internetsearch/test_search_runtime.py`
- `backend/tests/unit/runtimes/internetsearch/test_page_reader.py`
- `backend/tests/unit/conversation/test_search_turn.py`
- `backend/tests/unit/conversation/test_engine.py`
- `backend/tests/unit/conversation/test_tool_turn.py`
- `backend/tests/unit/artifacts/test_turn_artifact.py`
- `backend/tests/unit/actions/test_action_contracts.py`
- `backend/tests/unit/actions/test_action_boundaries.py`
- `backend/tests/unit/extensions/test_extension_contracts.py`
- `backend/tests/unit/extensions/test_extension_catalog.py`
- `backend/tests/unit/extensions/test_prompt_templates.py`
- `backend/tests/unit/extensions/test_skill_loading.py`
- `backend/tests/unit/services/test_extension_service.py`
- `backend/tests/unit/api/test_extension_routes.py`
- `backend/tests/unit/conversation/test_extensions_disabled.py`
- `backend/tests/unit/services/test_capability_service.py`
- `backend/tests/unit/services/test_action_evidence_log.py`
- `backend/tests/unit/api/test_action_routes.py`
- `backend/tests/unit/routing/test_provider_router.py`
- `backend/tests/unit/extensions/test_acp_server.py`
- `backend/tests/unit/extensions/test_mcp_oauth.py`
- `backend/tests/integration/test_extension_runtime.py`
- `backend/tests/integration/test_mcp_http_auth.py`

Validation results (linux-amd64):
- `backend/.venv/bin/python scripts/validate_backend.py unit`: PASS, 1525 passed.
- `backend/.venv/bin/python scripts/validate_backend.py integration`: PASS, 28 passed, including actual local MCP and ACP SDK peers and a bearer-protected streamable-HTTP MCP server.
- `npm --prefix desktop test`: PASS.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS.

Validation results (windows-amd64):
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers the `Run`/`Propose` label split in `actions-panel.js` that removes the self-approval appearance from `allow` capabilities, including `extension-definition-write`.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change.

Protocol tests required execution outside the restricted runner because its asyncio
subprocess/thread I/O stalled. Live native desktop behavior, remote deployment,
and other host classes remain unverified. The declared process controls are not
an OS sandbox.

## Follow-up

Human-familiar extension surfaces:
- Replace the generic capability-console path with family-specific Advanced Controls sections. Operators should see Add, Edit, Connect, Discover, Run, Disable, Remove, and Retire workflows, not capability IDs such as `extension-definition-write` or raw JSON definition forms.
- Keep proposal, authorization, revision, fingerprint, and execution records as backend/audit internals. Surface them only in an explicit detail/audit view.
- Preserve scroll position, selection, focus, and draft form values across refreshes and run polling.

MCP connections:
- Provide Add MCP Connection and Edit MCP Connection flows with fields for display name, transport, command or URL, allowed tools/resources/prompts, credential type, OAuth configuration, and test/discovery behavior.
- Show Connect, Reconnect, Disconnect, Discover Tools and Resources, Refresh Health, and Remove as explicit actions on a selected MCP connection.
- Present discovered tools, resources, and prompts as separate operator concepts. Resources and prompts should be attachable or inspectable; tools should render operation forms from schema with human labels and validation errors.
- Credential storage already runs with no approval prompt (`POST /extensions/{id}/credentials`), and ADR 0005's Actions panel no longer labels `extension-definition-write`/`extension-definition-delete` as a self-approval ritual. What remains is giving those two capabilities a dedicated Add/Edit MCP Connection home so the Actions panel is no longer the only way to reach them.

Skills and tools:
- Provide Import Skill, Edit Skill, Remove Skill, Show Instructions, and Requested Capabilities flows for operator-owned skills. Application-owned skills remain read-only.
- Provide Add Local Tool and Edit Local Tool flows for governed command tools with labeled command, argument, environment, root, timeout, schema, and output settings. Keep scripts executable only through a registered governed tool.

Hooks and plugins:
- Provide Add Hook and Edit Hook flows organized by event, matcher, handler type, and effect. Show last run, failure, and disable controls in the hook detail view.
- Provide Install Local Plugin, Inspect Plugin Contents, Enable/Disable, Remove, and Retire flows. Remote plugin sources and arbitrary install scripts remain out of scope unless a later ADR approves them.

Assistant integration and validation:
- Keep model-selected extension use behind the same backend capability selection and evidence path, but display results to the operator as the named tool/resource/prompt that ran.
- Update `config/extensions/README.md` so it no longer says desktop/native OAuth is follow-up once the operator flow is actually usable.
- Validate the revised surfaces with focused backend tests, `npm --prefix desktop test`, `cargo check --manifest-path desktop/src-tauri/Cargo.toml`, and a native visible `windows-amd64` desktop run that exercises the MCP, skill, tool, hook, and plugin workflows.
