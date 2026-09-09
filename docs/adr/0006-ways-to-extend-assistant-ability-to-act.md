# 0006 - Ways to Extend Assistant Ability to Act

Date: 2026-09-01
Status: Accepted
Related: 0002, 0003, 0004, 0005, 0007, 0008

## Context and Problem Statement

JARVISv7 needs reusable ways to extend what the assistant can know, configure, invoke, and do without creating a separate trust model for every new feature.

The project already has several extension-like surfaces: operator settings, personality profiles, model provider profiles, search providers, prompt authority boundaries, action contract records, and turn artifacts. Those are useful foundations, but they do not yet form one general extension system.

Future extension families may include reusable prompts, skills, MCP connections, hooks, plugins, connectors, and adapter definitions used by delegated agents. Some of those only shape context or operator choice; others can read private data, send data outward, mutate state, run code, or delegate work. The architecture needs one way to classify those surfaces and one governed execution path for anything with side effects.

This ADR owns extension-family cataloging, lifecycle, runtime operations, and non-agent operator workflows; ADR 0007 owns agent identity, agent runtime adapters, and Agent Client Protocol behavior.

## Decision Drivers

- Keep extension labels distinct by function so settings, prompts, skills, tools, providers, hooks, plugins, MCP connections, and agent adapter definitions do not collapse into one vague abstraction.
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
- ACP adapter definitions: declarative process-boundary records used by ADR 0007 agent runtimes
- hooks: deterministic lifecycle actions tied to visible events
- plugins: installable packages that bundle one or more extension shapes
- providers/connectors: named model, service, or external-account relationships with readiness, credentials, and permission boundaries

No extension shape gets a parallel execution path. If it reads private data, sends data outward, mutates state, runs code, delegates to an agent, or calls a service, it must become or invoke a governed capability record and use the shared authorization, approval, cancellation, artifact, and memory flow.

## Consequences

Positive:
- Extension work can proceed without inventing a new trust model per feature.
- MCP, ACP adapter definitions, skills, hooks, plugins, prompts, settings, providers, and tools remain distinguishable.
- External metadata can support discovery without granting itself authority.
- Desktop, scripts, daemon flows, and future clients can share backend-owned policy and artifacts.

Negative:
- A real extension system requires shared registry, lifecycle, authorization, and artifact infrastructure before broad tool use is enabled.
- Provider-native tool and MCP features may need wrapping before they fit v7's evidence model.
- Skill and plugin imports require provenance tracking so user-authored or external code does not look application-owned.
- ACP adapter definitions add process state that must stay aligned with ADR 0007 agent runtime behavior.
- Hook behavior can become surprising unless event names, effects, and failure paths stay small and visible.

## Implementation

This ADR is partially implemented. The backend extension catalog, governed runtime, MCP
authorization path, turn-engine capability selection, and desktop extension surface exist. Skills
and local tools have complete human-familiar Add/Edit/Remove workflows. MCP connections have
Add/Edit/Remove too, backed by the same read/edit contract for operator-owned declarative
definitions, but only for `streamable_http` transport with display-name/URL/allowlist fields;
`stdio` connections and credential/OAuth configuration remain outside both forms. The operator
experience is not complete because hooks and plugins still have no workflow of their own - the
generic capability-console path remains their only reachable surface - and some other operations
(extension run display, resource content, `stdio` MCP connections, MCP credential/OAuth fields)
still show internal capability names or raw JSON instead of complete human-familiar treatment.

Implemented foundations:
- Operator settings are scoped and classified through `backend/app/core/settings.py`. `backend/app/services/operator_config_service.py` owns the operator field allowlist and secret masking; `backend/app/api/routes/config.py` and `backend/app/api/schemas/config.py` are the route surface over it. Operator writes are allowlisted, and secrets are masked.
- Personality profiles are structured YAML under `config/personality/`. `backend/app/personality/schema.py`, `backend/app/personality/loader.py`, and `backend/app/personality/policy.py` reject authority-bearing fields such as tool policy, routing policy, memory policy, hidden instructions, and safety overrides.
- Personality selection is exposed through backend routes and schemas in `backend/app/api/routes/personality.py` and `backend/app/api/schemas/personality.py`.
- Prompt boundaries exist through `backend/app/cognition/prompt_envelope.py`, `backend/app/cognition/prompt_assembler.py`, `backend/app/cognition/prompt_renderer.py`, and `backend/app/cognition/prompt_chat_renderer.py`. Prompt segments carry authority labels, content type, and trust state.
- Provider profiles are implemented through `backend/app/services/llm_provider_profiles.py`, `backend/app/services/llm_provider_service.py`, `backend/app/api/routes/llm_config.py`, and `backend/app/api/schemas/llm_config.py`.
- Search providers are implemented as governed external-read behavior through `backend/app/cognition/search_policy.py`, `backend/app/services/search_service.py`, and `backend/app/runtimes/internetsearch/`.
- Action governance records exist in `backend/app/actions/contracts.py`: capability descriptors, availability/readiness/effect classes, approval modes, model proposals, authorization decisions, approval records, execution results, action cancellation records, the action evidence accumulator, metadata claims, and collision checks. `CapabilityRegistry` enforces execution boundaries and JSON Schema validity at registration, and refuses any descriptor that fails them.
- Turn artifacts carry action, search, memory, runtime, and failure evidence used by extension operations. Agent delegation evidence belongs to ADR 0007.
- Desktop surfaces call backend APIs for settings, provider profiles, search evidence, personality selection, and governed action discovery, approval, execution status, cancellation, and audit through `desktop/src/api-client.js`, `desktop/src/components/settings-panel.js`, `desktop/src/components/llm-provider-settings.js`, `desktop/src/components/search-evidence.js`, `desktop/src/components/actions-panel.js`, `desktop/src/main.js`, and `desktop/src-tauri/src/backend.rs`.
- The shared governed execution path this ADR depends on is built. ADR 0005 supplies one authorization ladder, an approval flow with declared modes, durable action evidence, and boundary rules the registry enforces before a capability can be registered. Every remaining extension shape attaches to that path rather than defining its own.

- One backend-owned extension catalog exists in `backend/app/extensions/`. `ExtensionDescriptor` carries a stable `<family>:<local_id>` identifier, version, source, provenance, trust status, state, readiness, availability, dependencies, collisions, and untrusted metadata claims. Built-in and declarative families register alongside settings, personality profiles, provider profiles, search providers, prompt templates, skills, and governed action descriptors.
- The catalog observes each family live and persists only what an operator decided and the catalog cannot re-derive. `extension_overlay` and `extension_event` in `data/operator.sqlite` hold enabled state, trust, and the retirement audit trail behind a schema migration; health, dependencies, version, provenance, and collisions are derived per read so a stale row cannot claim to be healthy.
- Enabling, disabling, or retiring an extension is a governed action. It routes through the ADR 0005 capability executor as `extension-state-update`, so it produces the same proposal, approval, and execution evidence as every other operator mutation.
- Prompt templates are discoverable through `backend/app/extensions/prompts.py` and `config/prompts/`. A template may only declare `user` or `session` authority, so a reusable prompt cannot become hidden policy.
- Declarative extension defaults are tracked under `config/extensions/{acp,mcp,hooks,plugins,skills,tools}` and operator additions are untracked under `data/extensions/{family}`. Discovery gives application defaults precedence for duplicate family/IDs and records application versus operator provenance and trust. Skills support both roots with progressive disclosure; the tracked `inspect-extensions` skill is instruction-only, while operator skills remain external.
- A skill's `requested_tools` is recorded as an untrusted metadata claim, never a grant, and a skill declaring any authority-bearing field is rejected. Declared scripts resolve only through governed process execution.
- Hook and plugin lifecycles and runners exist in `backend/app/extensions/{hooks,plugins}.py`: closed hook event names, effect classes reused from ADR 0005, application-owned `record_event`, governed capability dispatch, bounded plugin installation, bundle hashing, and child-definition validation.
- MCP connection management exists in `backend/app/extensions/mcp.py` with official SDK transport, discovery, schema-preserving records, health, credential references, allowlists, elicitation, cancellation, and host authorization callbacks. ACP adapter definitions are discovered through the same declarative extension catalog and declare governed process boundaries; ADR 0007 owns using those definitions for Agent Client Protocol session behavior and conformance.
- Backend API and desktop surfaces exist through `backend/app/api/routes/extensions.py` and `desktop/src/components/extensions-panel.js`, covering catalog discovery, load errors, detail, progressive body disclosure, and state changes.

- `ExtensionRuntimeService` registers extension operations with the shared capability service. Approvals bind a definition fingerprint; changed definitions require a new proposal. `ExtensionRuns` persists run state and marks interrupted work after restart without replaying effects.
- The current desktop exposes invocation, approvals, run progress, cancellation, credentials, and structured elicitation through raw extension detail surfaces. Approval requests run off the native UI thread so nested input remains usable, but these controls are implementation-facing and need the operator-familiar follow-up below.

Declarative definitions and their initial tracked defaults are documented in
`config/extensions/README.md`. The disabled application hook default records
no events until explicitly enabled.

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
operations. Agent/ACP execution remains outside model-selected extension tools and belongs to
ADR 0007.

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
credential form is independent of discovered operations, so a server that demands authorization
before discovery can still be credentialed. Cancelling a run is confirmed.

OAuth definition metadata accepts public endpoint keys ending in `_url`, such as
`authorization_url` and `token_url`. Inline `client_secret` remains refused and must use a
credential reference.

Operator-owned skills are imported, edited, and removed through `extension-skill-write` and
`extension-skill-delete`. The manifest is parsed before it is written, so a skill declaring an
authority-bearing field is refused with its reason rather than landing on disk, and an application
skill of the same id is never overwritten. The desktop gates skill editing on provenance, because an
operator skill is external-trust by design; trust does not indicate ownership.

`extension-credential-write` already executes through its own dedicated route (`POST
/extensions/{id}/credentials`) with no proposal or approval step at all, so operator-requested
credential storage was never gated by the capability-console ceremony.

The Extensions panel has its own Add MCP Connection flow for `extension-definition-write` and
`extension-definition-delete`.
`desktop/src/components/extensions-panel.js` renders an "Add MCP connection" form at the top of the
catalog list - display name, connection ID, and URL - that proposes `extension-definition-write`
with `family: "mcp"` and a `streamable_http` definition through the same governed capability path
`saveSkill` already used for operator skills; `extensionLocalIdValid` rejects a malformed connection
ID before it is proposed, matching the backend's `SAFE_LOCAL_ID` pattern. A connection whose
provenance shows it is operator-owned (`isOperatorOwnedProvenance`) gets a "Remove connection"
control next to its credential form, which proposes `extension-definition-delete`. This covers the
common case; adding an operator-owned `stdio` connection still requires editing YAML, since a form
for arbitrary local command execution needs its own careful design.

`removeMcpConnection` and `removeSkill` both check the resolved proposal's `status` before
reporting success, matching `saveSkill`'s behavior. A governed capability can resolve with
`{status: "failure", execution: {error}}` without throwing, so removal paths surface execution
errors instead of treating the proposal call itself as success.

The Extensions panel has an Import Skill flow for creating operator-owned skills. `importSkill`
proposes the same `extension-skill-write` capability
`saveSkill` uses, through a dedicated form (skill ID, body) rendered at the top of the Extensions
catalog next to Add MCP Connection, so its error and success messaging land next to the form the
operator is using rather than in the (possibly unrelated) detail column `saveSkill`'s edit errors
target. `extensionLocalIdValid` (renamed from the MCP-specific `mcpConnectionIdValid`, since the
`SAFE_LOCAL_ID` pattern it checks is shared across every extension family) rejects a malformed skill
ID before it is proposed.

Discover Tools and Resources and Refresh Health are the same action for an MCP connection, not two
separate ones: `_mcp` in `backend/app/services/extension_runtime_service.py` refreshes a connection's
cached health and discovered tool/resource/prompt list when the invoked operation name is
`discover`, and `discover` is the one operation every MCP connection registers. The desktop labels
that operation "Discover tools and resources" / "Discover" through `operationDisplayName` and
`operationSubmitLabel`. `invoke()` re-fetches `getExtensionRuntime` after any invocation that
actually ran (not one still `awaiting_approval`) against the currently selected extension, so a
successful discovery is visible immediately.

Discovered tools, resources, and prompts render as separate operator concepts. `_mcp` in
`backend/app/services/extension_runtime_service.py` names
each discovered operation `tool:<name>`, `resource:<uri>`, or `prompt:<name>`; `operationKind` reads
that prefix (checking the exact family word before the first colon, so a bare non-MCP operation
name such as ACP's `prompt` or the tool family's `run` is never miscategorized) and
`operationShortLabel` strips it for display, so a discovered `tool:get_forecast` reads as
`get_forecast` under a "Tools" heading rather than as a raw capability-shaped string. `renderDetail`
groups an extension's operations by kind and renders "Tools", "Resources", and "Prompts" sections in
that order, each only when it has entries; `discover` keeps its own unlabeled "Discover tools and
resources" control rather than sitting under a generic heading, and any operation that matches
neither pattern (every non-MCP extension family) renders exactly as before, under "Operations".

The catalog list and detail columns keep their scroll position across a re-render.
`renderPanel` rebuilds the whole panel through `container.replaceChildren` on every state change,
including the run-poll tick that fires roughly once a second while the panel is open. `listColumn`
and `detailColumn` carry a
`data-scroll-key`, and `renderPanel` captures each keyed element's `scrollTop` from the outgoing
tree and reapplies it to the incoming one, the same capture-then-restore shape the existing
`data-draft-key` mechanism already uses for form values. The `window.setInterval` callback in
`createExtensionsPanel`'s `show()` (not `renderPanel` itself) checks `document.activeElement` and
returns before calling `controller.refreshRuns()` when focus is on an input, textarea, or select, so
that specific trigger already cannot fire a poll re-render at all while a form field is focused.

Focus on a non-form control - a catalog row, a state-transition button, "Show body", or "Remove
connection" - is preserved the same way: `renderPanel` reads `document.activeElement`'s
`data-focus-key` before `replaceChildren` and refocuses the element carrying the same key afterward,
searching the fresh tree with `querySelectorAll("[data-focus-key]")` rather than assuming the old node
reference is still attached to anything. Catalog rows key on `row:<extension_id>`, state-transition
buttons on `state:<extension_id>:<next>`, "Show body" on `show-body:<extension_id>`, and "Remove
connection" on `remove-connection:<extension_id>`. A state-transition click triggers `setState` ->
`refreshCatalog()`, so the focus key preserves keyboard and screen-reader position across that
operator-requested refresh.

`config/extensions/README.md` describes the desktop OAuth flow as implemented. Connect and
Reconnect exist for OAuth-configured MCP connections through the authorize and reauthorize controls.
Disconnect remains undefined: no backend revoke or clear-authorization route exists, and non-OAuth
connections are not held open between operations.

A resource is read and a prompt is fetched, not "invoked" the way a tool is - `operationSubmitLabel`
returns "Read" for a `resource:` operation and "Get prompt" for a `prompt:` operation, alongside
"Discover" for `discover` and "Invoke" for tool or non-MCP operations. This is a labeling change
only: a resource's operation schema is empty because its identity is the URI already in its name, and
a prompt's schema renders as plain text fields from its declared arguments.

A run's heading shows status and start time instead of its raw run id. `ExtensionRuns.create` in
`backend/app/extensions/runs.py` names a run with `uuid4().hex` - a backend correlation identifier
with no operator meaning. `formatRunStarted` uses the run's `started_at` timestamp formatted through
`toLocaleTimeString`, falling back to the raw value if it does not parse as a date rather than
producing "Invalid Date". The run id and `proposal_id` (also backend-only; a run's payload carries no
operator-facing operation name to show instead) render inside a "Run details" disclosure per run,
the same disclosure shape the extension-level Source/Revision fields already use, so they stay
reachable for audit without sitting in the heading every run renders.

Source and revision sit behind detail disclosure instead of in an extension's primary facts. `source`
is a raw file or
module path (`data/extensions/mcp/weather.yaml`, `backend/app/services/operator_config_service.py`)
and `revision` is an optimistic-concurrency counter used only to detect a conflicting write. Both
render inside a `<details>` labeled "Details" appended after the primary facts, the same disclosure
shape this file
already uses for a loaded extension body, so an operator reads identity and status at a glance and
opens the same control to see the backend/audit-shaped fields underneath.

Three modules remain adjacent to but distinct from the extension catalog. `backend/app/core/capabilities.py` only describes hardware/runtime capability flags. `backend/app/actions/catalog.py` builds ADR 0005 governed capability descriptors from observed runtime state. `backend/app/models/catalog.py` is the model artifact catalog. None of them carries extension provenance, trust status, enablement, or dependency state.

The Add MCP Connection form accepts allowed tools, resources, and prompts lists for the
connection being created, instead of leaving a `streamable_http` connection unrestricted until an
operator edits its stored definition by hand. `backend/app/extensions/mcp.py`'s `_require_allowed`
only rejects an operation when its allowlist is both present and non-empty (`if allowlist and value
not in allowlist`), so an absent or empty list means unrestricted, not "deny all" - `parseAllowlist`
splits each new field's comma-separated text into a trimmed, non-empty array, and `addMcpConnection`
adds `tool_allowlist`/`resource_allowlist`/`prompt_allowlist` to the proposed definition only when
that array is non-empty, so an operator who leaves a field blank still gets today's unrestricted
connection rather than one that can reach nothing. Credential type and OAuth configuration remain
out of the connection form, per Follow-up below.

An operation's submit button, the Add MCP Connection and Import Skill forms' submit buttons, and the
Store credential submit button carry the same `data-focus-key` mechanism as the catalog row and
state-transition controls. A skill import, connection/tool add, or credential save calls back into
`refreshCatalog()` or `selectExtension()`, while an operation invocation goes through `invoke()`,
which refreshes runs and selected runtime detail directly and calls `emit()`. Each button keys on its
own stable identity - `add-mcp:submit`, `import-skill:submit`, `credential-submit:<extension_id>`, and
`operation-submit:<extension_id>:<capability_id>` - rather than sharing one key across forms.

A completed "Get prompt" run renders its result as role-labeled message text instead of the same
raw JSON block every other operation result falls back to. An MCP prompt result's shape
(`{messages: [{role, content: {type: "text", text}}]}`) is structurally distinct from a tool result's
shape (`{content: [...]}`), so `formatPromptMessages` detects it by structure rather than needing the
run to carry which operation produced it, which the run record does not track today. Any message
whose content is not plain text (image, audio, embedded resource) makes the whole result fall back to
raw JSON rather than silently dropping that content.

Add Local Tool exists for governed command tools, the same `extension-definition-write` capability
path as Add MCP Connection rather than a direct write. `backend/app/services/extension_runtime_service.py`
requires a `tool` definition's `command` (a fixed, non-empty argv list - a tool takes no
operator-supplied arguments at invoke time, only the `run` operation with an empty schema) and a
`process` mapping validated by `ProcessBoundary.from_mapping` (`subprocess`, a non-empty
`argv_allowlist`, an explicit `env_passthrough` allowlist with no wildcard, and `working_root` from
the fixed set `data`/`cache`/`reports`/`models`/`runtimes`); the form collects command as one argv
token per line via `parseCommandLines`, `argv_allowlist` and `env_passthrough` as
comma-separated lists via the existing `parseAllowlist`, and `working_root` as a constrained
`<select>`. The backend does not accept or use a per-tool timeout, output setting, or argument
schema. `subprocess` is not a form field, even though it is a required part of `process`: every tool registers with
`effect_class` `privileged_execution` (`extension_runtime_service.py`'s `_operations_for`), and
`boundaries.py`'s `require_boundaries` rejects a `privileged_execution` capability whose process
boundary declares `subprocess: false` - so it is not an operator choice, only a fixed fact, and
`addLocalTool` always sends `subprocess: true` regardless of caller input. A "Remove tool" control
exists in a tool's detail view, gated on
`isOperatorOwnedProvenance` the same way "Remove connection" and skill removal are.

A stored operator-owned declarative definition can be read and edited through a lossless,
concurrency-safe contract, closing the gap that blocked both Edit MCP Connection and Edit Local
Tool.

`ExtensionResponse.definition_available` is true only when a family is in `DEFINITION_FAMILIES`
(`mcp`, `acp`, `hook`, `plugin`, `tool`), provenance is exactly `data/extensions`, and trust is
`operator`. The trust check excludes a plugin-installed child: `ExtensionRuntimeService.definitions()`
gives an installed plugin child the same `data/extensions` provenance as a standalone operator
definition but a distinct `external` trust, and its manifest lives inside the plugin bundle
directory rather than the flat family directory `discover_definition_manifests` scans, so it can
never be retrieved through this contract even though it shares the provenance test
`isOperatorOwnedProvenance` uses client-side. An application-owned definition (`config/extensions`)
and every non-declarative family (skill, prompt, settings, provider, search provider, capability,
agent) also never claim a readable definition.

`GET /extensions/{extension_id}/definition` (`ExtensionService.definition`, backed by
`discover_definition_manifests` re-reading the same on-disk YAML `write_definition` writes to)
returns the full editable manifest - `name`, `version`, `enabled`, `dependencies`, `metadata`, and
`definition` - plus a `fingerprint`, so an editor can preserve every field a hand-authored YAML
file may declare instead of silently dropping `dependencies` or `metadata` on save.
`definition_fingerprint` in `backend/app/extensions/discovery.py` hashes a sorted-JSON
serialization of that same field set, not the raw YAML text, so reformatting alone never produces
a false conflict.

`write_definition` now accepts that same field set (`extension-definition-write`'s input schema
gained `dependencies`, `metadata`, and an optional `expected_fingerprint`) and four write-safety
gaps are closed, all guarded by the same `self._lock` `bindings()` already uses: it writes through
`write_text_atomic` (temp file plus `os.replace`, the same helper `backend/app/artifacts/storage.py`
already provides for artifact writes) instead of a direct `path.write_text`, so a crash mid-write
cannot leave a truncated YAML file; `expected_fingerprint` distinguishes create from update rather
than being an optional extra check - a create (no `expected_fingerprint`) is refused if an operator
definition with that id already exists, so reusing an id (a typo, or two operators racing to add the
same connection) cannot silently replace it, and an edit (`expected_fingerprint` given) is refused if
the stored definition no longer matches it or has disappeared, so a stale editor cannot silently
overwrite a concurrent change either; and an edit of an MCP connection now clears its discovery
snapshot the same way `delete_definition` already does, so a connection's changed transport or URL
cannot keep serving a health/tool list captured from what it looked like before the edit.

The unrelated "Edit skill" editor's textarea carried an unconditional `data-draft-key`, so
`renderPanel`'s capture-then-restore step captured the pre-load empty value from the outgoing tree
and reapplied it over the freshly loaded body on the render that first populated `state.body`,
leaving the editor empty after "Show body" until a second render captured the correct in-between
value. The draft key is now assigned only once `state.body` is non-empty, so the outgoing tree has
no matching key on the render that first loads it and there is nothing to restore over the fresh
value - the same prefill hazard any editor built on this pattern, including Edit MCP Connection and
Edit Local Tool, would otherwise inherit.

Edit MCP Connection and Edit Local Tool exist, built on this contract, and `desktop/src/main.js`
wires `getExtensionDefinition` into the mounted Extensions panel's handlers alongside the others -
without that wiring the click-to-load workflow described below returns nothing in the real
application even though every isolated controller and DOM test supplies its own mock handler and
passes regardless. A regression test now extracts every `handlers.<name>` call
`extensions-panel.js` makes and asserts `main.js`'s `createExtensionsPanel` call wires each one by
name, so a future handler that is added to the panel but not mounted fails a test instead of only
failing silently in the running app.

Clicking "Edit connection" (gated on `definition_available`, not the client-side
`isOperatorOwnedProvenance` heuristic "Remove connection" uses) or "Edit tool" calls
`loadDefinition`, and once loaded renders a distinct form - `extensions-edit-connection` /
`extensions-edit-tool`, not the empty Add form reused with stale values - prefilled from the
response. Because this form only renders after the definition has loaded, there is no pre-load
render for the capture-then-restore mechanism to have captured an empty draft from, so it does not
need the conditional-draft-key fix the Edit skill editor required. A connection whose stored
`transport` is not `streamable_http` shows a plain notice directing the operator to edit the YAML
directly instead of rendering a form the Add flow's own field set cannot represent, the same scope
limit Add MCP Connection already has.

Saving calls `updateMcpConnection` / `updateLocalTool`, which build the new `definition` by
spreading the just-loaded definition and overwriting only the fields the form actually edits, rather
than constructing a fresh object from only those fields. `streamableHttpDefinition` and
`toolDefinition` both now take that prior definition as a base argument (an empty object for Add, so
create behavior is unchanged) - an MCP connection's `credential_ref` and `oauth`, and a tool's
`skill_id` and `script`, none of which any form field edits, survive a save instead of silently
disappearing the first time an operator changes a display name or command; an edited allowlist is
still explicitly deleted rather than left over from the base when the operator clears it. The rest
of the write - `dependencies`/`metadata`/`enabled` carried from the loaded definition, plus
`expected_fingerprint` - goes through the existing `extension-definition-write` capability as
before. "Cancel edit" and a successful save both close the form and, on success, reselect the
extension so its detail reflects the saved value.

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
- `backend/app/extensions/discovery.py`
- `backend/app/services/extension_service.py`
- `backend/app/services/extension_runtime_service.py`
- `backend/app/artifacts/storage.py`
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
- `desktop/src-tauri/src/lib.rs`

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
- `backend/tests/unit/extensions/test_mcp_oauth.py`
- `backend/tests/integration/test_extension_runtime.py`
- `backend/tests/integration/test_mcp_http_auth.py`

Validation results (linux-amd64):
- `backend/.venv/bin/python scripts/validate_backend.py unit`: PASS, 1525 passed.
- `backend/.venv/bin/python scripts/validate_backend.py integration`: PASS, 28 passed, including actual local MCP SDK peers and a bearer-protected streamable-HTTP MCP server.
- `npm --prefix desktop test`: PASS.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS.

Validation results (windows-amd64):
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers the `Run`/`Propose` label split in `actions-panel.js`; Add/Remove MCP Connection; Import Skill; Add/Remove Local Tool; malformed local-id refusal; backend refusal messages for create/delete flows; operator-owned provenance gates; allowlist parsing; fixed `process.subprocess: true` for local tools; MCP discovery labels and selected-runtime refresh; Tools/Resources/Prompts grouping; resource/prompt/discover/tool submit verbs; prompt result formatting; extension source/revision and run id/proposal id detail disclosure; scroll preservation; and focus preservation for catalog rows, state-transition buttons, "Show body", "Remove connection", Add MCP Connection, Import Skill, Store credential, and operation submit buttons.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side source changed for this validation scope.
- Direct backend parsing check: PASS. `parse_definition_manifest` and `ProcessBoundary.from_mapping(...).validate_argv(...)` accept the Local Tool payload shape produced by the desktop form.
- `backend/.venv/Scripts/python.exe scripts/validate_backend.py unit`: PASS, 1527 passed, 7 skipped. Covers `definition_available` excluding an application-owned definition, a non-`DEFINITION_FAMILIES` family, and a plugin-installed child (same `data/extensions` provenance as a standalone operator definition, but `external` trust); `ExtensionService.definition` round-tripping `enabled`/`dependencies`/`metadata`/`definition`/`fingerprint` for an `mcp` definition and separately confirming a `tool` definition reads through the same contract; and the `GET /extensions/{extension_id}/definition` route serving that full shape.
- `backend/.venv/Scripts/python.exe scripts/validate_backend.py integration`: PASS, 32 passed. Covers an edit clearing a connection's stale MCP discovery snapshot the same way removal already does, a stale `expected_fingerprint` refusing to overwrite a definition changed by another write, a matching `expected_fingerprint` succeeding, and a write leaving no `.tmp` file behind.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers the Edit skill body-prefill fix with a regression test that fails against the prior unconditional draft key and passes with the conditional one, confirmed by reverting the fix locally and observing the new test fail before restoring it.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. Covers the new `get_extension_definition` Tauri command.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers `updateMcpConnection`/`updateLocalTool` proposing `extension-definition-write` with `dependencies`/`metadata`/`enabled`/`expected_fingerprint` carried from the loaded definition, a backend fingerprint-conflict refusal keeping the edit form open instead of claiming success, `cancelDefinitionEdit` closing the form without proposing anything, and a DOM-level render of both "Edit connection" and "Edit tool" asserting the click-to-load flow renders a distinct prefilled form (not the empty Add form) and that submitting an edited field reaches `extension-definition-write` with the change and the fingerprint.
- `backend/.venv/Scripts/python.exe scripts/validate_backend.py integration`: PASS, 33 passed. Covers a create (no `expected_fingerprint`) reusing an id refused with "already exists" rather than silently replacing the existing operator definition, confirmed against the actual file's untouched content afterward.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers source-level checks that `main.js` wires each named handler used by `extensions-panel.js`, including `getExtensionDefinition`; controller tests that MCP `credential_ref`/`oauth` and tool `skill_id`/`script` survive edits; and Add requests omitting `expected_fingerprint`. These checks establish desktop source and component contracts; native desktop interaction remains unverified.

Protocol tests required execution outside the restricted runner because its asyncio
subprocess/thread I/O stalled. Native operator layout and interaction validation
belongs to ADR 0008. Remote deployment and other host classes remain unverified.
The declared process controls are not an OS sandbox.

## Follow-up

Human-familiar extension surfaces:
- Provide Add and Edit workflows for hooks and plugins, using extension-family terms and keeping capability IDs and raw definition JSON out of the normal path, the same principle MCP/skill/tool workflows already follow.
- Rework extension run display so each run has an operator-readable identity, status, requested input, event/failure summary, result summary, and artifacts for the extension operation that ran. Raw action evidence, authorization records, and definition fingerprints remain ADR 0005 audit/detail evidence.

MCP connections:
- Extend Add/Edit MCP Connection to `stdio` connections with command, argv allowlist, environment passthrough, working root, and credential-reference handling that matches the existing process-boundary contract.
- Add credential reference and OAuth configuration fields to the create/edit flow. Secret values still belong to the dedicated credential route; definition forms should store only references and OAuth metadata.
- Define MCP Disconnect semantics. Non-OAuth connections currently connect only for the duration of an operation, and OAuth connections have authorize/reauthorize but no backend revoke or clear-authorization route.
- Render resource reads as a content-preview view instead of only a bare submit/result path.

Hooks and plugins:
- Provide Add Hook and Edit Hook flows organized by event, effect class, target capability, and action arguments. Show hook event history, failures, and disable controls in the hook detail view.
- Provide Install Local Plugin, Inspect Plugin Contents, Enable/Disable, Remove, and Retire flows. Add any missing backend uninstall/remove contract for installed plugin bundles before exposing a destructive plugin-removal control. Remote plugin sources and arbitrary install scripts remain out of scope unless a later ADR approves them.

Assistant integration and validation:
- Keep model-selected extension use behind the same backend capability selection and evidence path, but display results to the operator as the named tool/resource/prompt that ran.
- Validate extension-family backend and desktop contracts with focused backend tests, `npm --prefix desktop test`, and `cargo check --manifest-path desktop/src-tauri/Cargo.toml`. Native operator layout and interaction validation belongs to ADR 0008.
