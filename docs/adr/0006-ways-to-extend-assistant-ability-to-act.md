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
credential storage was never gated by the capability-console ceremony.

The Extensions panel now has its own Add MCP Connection flow, so `extension-definition-write` and
`extension-definition-delete` are no longer reachable only through ADR 0005's Actions panel.
`desktop/src/components/extensions-panel.js` renders an "Add MCP connection" form at the top of the
catalog list - display name, connection ID, and URL - that proposes `extension-definition-write`
with `family: "mcp"` and a `streamable_http` definition through the same governed capability path
`saveSkill` already used for operator skills; `extensionLocalIdValid` rejects a malformed connection
ID before it is proposed, matching the backend's `SAFE_LOCAL_ID` pattern. A connection whose
provenance shows it is operator-owned (`isOperatorOwnedProvenance`) gets a "Remove connection"
control next to its credential form, which proposes `extension-definition-delete`. This covers the
common case; adding an operator-owned `stdio` connection still requires editing YAML, since a form
for arbitrary local command execution needs its own careful design and is not part of this
increment.

`removeMcpConnection` and `removeSkill` both now check the resolved proposal's `status` before
reporting success, matching `saveSkill`'s existing behavior: a governed capability can resolve with
`{status: "failure", execution: {error}}` without throwing, and both removal paths previously
treated any non-thrown resolution as a successful delete. `removeSkill` carried the same gap before
this change; it is fixed alongside `removeMcpConnection` rather than left as a second copy of the
same defect.

The Extensions panel also has an Import Skill flow now, closing the last gap in the operator-owned
skill lifecycle: `saveSkill` already covered editing an existing skill and `removeSkill` covered
deletion, but creating a brand-new skill had no entry point other than hand-authoring a file under
`data/extensions/skill`. `importSkill` proposes the same `extension-skill-write` capability
`saveSkill` uses, through a dedicated form (skill ID, body) rendered at the top of the Extensions
catalog next to Add MCP Connection, so its error and success messaging land next to the form the
operator is using rather than in the (possibly unrelated) detail column `saveSkill`'s edit errors
target. `extensionLocalIdValid` (renamed from the MCP-specific `mcpConnectionIdValid`, since the
`SAFE_LOCAL_ID` pattern it checks is shared across every extension family) rejects a malformed skill
ID before it is proposed.

Discover Tools and Resources and Refresh Health are the same action for an MCP connection, not two
separate ones: `_mcp` in `backend/app/services/extension_runtime_service.py` only refreshes a
connection's cached health and discovered tool/resource/prompt list when the invoked operation name
is `discover`, and `discover` is the one operation every MCP connection registers. The desktop
previously rendered that operation with its raw name ("discover") and a generic "Invoke" button
alongside every other schema-derived operation form, and after invoking it, the display of health and
discovered operations stayed stale until the extension was deselected and reselected -
`invoke()` refreshed the run list but never the runtime detail a successful "discover" had just
changed. `operationDisplayName` and `operationSubmitLabel` now name that one operation "Discover
tools and resources" / "Discover" instead of leaving it to read as an unlabeled schema form, and
`invoke()` re-fetches `getExtensionRuntime` after any invocation that actually ran (not one still
`awaiting_approval`) against the currently selected extension, so a successful discovery is visible
immediately.

Discovered tools, resources, and prompts now render as separate operator concepts instead of one
flat "Operations" list. `_mcp` in `backend/app/services/extension_runtime_service.py` already names
each discovered operation `tool:<name>`, `resource:<uri>`, or `prompt:<name>`; `operationKind` reads
that prefix (checking the exact family word before the first colon, so a bare non-MCP operation
name such as ACP's `prompt` or the tool family's `run` is never miscategorized) and
`operationShortLabel` strips it for display, so a discovered `tool:get_forecast` reads as
`get_forecast` under a "Tools" heading rather than as a raw capability-shaped string. `renderDetail`
groups an extension's operations by kind and renders "Tools", "Resources", and "Prompts" sections in
that order, each only when it has entries; `discover` keeps its own unlabeled "Discover tools and
resources" control rather than sitting under a generic heading, and any operation that matches
neither pattern (every non-MCP extension family) renders exactly as before, under "Operations".

The catalog list and detail columns now keep their scroll position across a re-render.
`renderPanel` rebuilds the whole panel through `container.replaceChildren` on every state change,
including the run-poll tick that fires roughly once a second while the panel is open; nothing
previously captured or restored `scrollTop`, so a scrolled catalog list snapped back to the top on
every poll tick whenever a run was active. `listColumn` and `detailColumn` now carry a
`data-scroll-key`, and `renderPanel` captures each keyed element's `scrollTop` from the outgoing
tree and reapplies it to the incoming one, the same capture-then-restore shape the existing
`data-draft-key` mechanism already uses for form values. The `window.setInterval` callback in
`createExtensionsPanel`'s `show()` (not `renderPanel` itself) checks `document.activeElement` and
returns before calling `controller.refreshRuns()` when focus is on an input, textarea, or select, so
that specific trigger already cannot fire a poll re-render at all while a form field is focused.

Focus on a non-form control - a catalog row, a state-transition button, "Show body", or "Remove
connection" - is now preserved the same way: `renderPanel` reads `document.activeElement`'s
`data-focus-key` before `replaceChildren` and refocuses the element carrying the same key afterward,
searching the fresh tree with `querySelectorAll("[data-focus-key]")` rather than assuming the old node
reference is still attached to anything. Catalog rows key on `row:<extension_id>`, state-transition
buttons on `state:<extension_id>:<next>`, "Show body" on `show-body:<extension_id>`, and "Remove
connection" on `remove-connection:<extension_id>`. This closes the case named in Follow-up as the
narrower remainder: an operator who clicks a state-transition button triggers `setState` ->
`refreshCatalog()`, the very re-render that would otherwise drop focus off the control they just
used.

`config/extensions/README.md` no longer says desktop/native OAuth is follow-up work: the Extensions
panel has driven that flow (status, authorize, code exchange) since the OAuth work landed earlier in
this ADR, and the note describing it as outstanding had gone stale. Checking that claim against the
desktop's actual OAuth controls also surfaced that this ADR's own Follow-up overstated a different
gap: "Connect, Reconnect, and Disconnect remain missing" was true for Disconnect (no backend concept
exists for it) but not for Connect/Reconnect, which already exists as the OAuth authorize/reauthorize
control for OAuth-configured connections. Both are corrected below rather than left as two more stale
claims sitting next to the one just found.

A resource is read and a prompt is fetched, not "invoked" the way a tool is - `operationSubmitLabel`
now says "Read" for a `resource:` operation and "Get prompt" for a `prompt:` operation instead of the
generic "Invoke" every operation used before, the same function already responsible for the
"Discover" verb it gives `discover`. This is a labeling change only: a resource's operation schema
was already empty (its identity is the URI already in its name, not a fillable argument) and a
prompt's schema already renders as a small set of plain text fields from its declared arguments, so
neither needed the open-JSON-form treatment the Follow-up's "not an open form"
language was written to guard against - the generic form already behaved correctly for both, it just
described every action with the same word regardless of what it actually did.

A run's heading no longer shows its raw run id. `ExtensionRuns.create` in
`backend/app/extensions/runs.py` names a run with `uuid4().hex` - a backend correlation identifier
with no operator meaning - and `renderDetail`'s run list rendered `${run.status} · ${run.run_id}` as
the primary heading for every run, the same pattern already fixed once for the extension-level facts
block. `formatRunStarted` replaces the raw id with the run's `started_at` timestamp formatted through
`toLocaleTimeString`, falling back to the raw value if it does not parse as a date rather than
producing "Invalid Date". The run id and `proposal_id` (also backend-only; a run's payload carries no
operator-facing operation name to show instead) now render inside a "Run details" disclosure per run,
the same disclosure shape the extension-level Source/Revision fields already use, so they stay
reachable for audit without sitting in the heading every run renders.

Source and revision no longer sit in an extension's primary facts. `source` is a raw file or
module path (`data/extensions/mcp/weather.yaml`, `backend/app/services/operator_config_service.py`)
and `revision` is an optimistic-concurrency counter used only to detect a conflicting write - neither
is operator-meaningful state, and both were rendered unconditionally in `renderDetail`'s main `<dl>`
alongside identifier, family, provenance, trust, readiness, and availability. They now render inside
a `<details>` labeled "Details" appended after the primary facts, the same disclosure shape this file
already uses for a loaded extension body, so an operator reads identity and status at a glance and
opens the same control to see the backend/audit-shaped fields underneath.

Three modules remain adjacent to but distinct from the extension catalog. `backend/app/core/capabilities.py` only describes hardware/runtime capability flags. `backend/app/actions/catalog.py` builds ADR 0005 governed capability descriptors from observed runtime state. `backend/app/models/catalog.py` is the model artifact catalog. None of them carries extension provenance, trust status, enablement, or dependency state.

The Add MCP Connection form now accepts an allowed tools, resources, and prompts list for the
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
Store credential submit button now carry the same `data-focus-key` mechanism as the catalog row and
state-transition controls, closing the remaining gap named in Follow-up: a click on one of these
buttons is itself the action that triggers the re-render: a skill import, an add, or a credential save
call back into `refreshCatalog()` or `selectExtension()`, while an operation invocation instead goes
through `invoke()`, which refreshes runs and (for the selected extension) runtime detail directly and
calls `emit()` - so without a focus key the click that starts the action was also the click that lost
focus off it. Each button keys on its
own stable identity - `add-mcp:submit`, `import-skill:submit`, `credential-submit:<extension_id>`, and
`operation-submit:<extension_id>:<capability_id>` - rather than sharing one key across forms.

A completed "Get prompt" run now renders its result as role-labeled message text instead of the same
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
token per line via the new `parseCommandLines`, `argv_allowlist` and `env_passthrough` as
comma-separated lists via the existing `parseAllowlist`, and `working_root` as a constrained
`<select>` - and nothing else, since the backend does not accept or use a per-tool timeout, output
setting, or argument schema despite earlier Follow-up wording suggesting it might. `subprocess` is not
a form field either, even though it is a required part of `process`: every tool registers with
`effect_class` `privileged_execution` (`extension_runtime_service.py`'s `_operations_for`), and
`boundaries.py`'s `require_boundaries` rejects a `privileged_execution` capability whose process
boundary declares `subprocess: false` - so it is not an operator choice, only a fixed fact, and
`addLocalTool` always sends `subprocess: true` regardless of any caller input. An earlier version of
this form exposed a "Runs as a subprocess" checkbox; unchecking it produced an operator-visible
failure on every submit, since the backend rejects `subprocess: false` unconditionally for this
effect class - the checkbox has been removed rather than left offering a choice with only one
non-failing answer. A "Remove tool" control exists in a tool's detail view, gated on
`isOperatorOwnedProvenance` the same way "Remove connection" and skill removal are. Edit Local Tool is
not implemented: like Edit MCP Connection, it has no backend route to read a stored definition back,
only `body_available` for `prompt`/`skill` families.

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
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers `addMcpConnection` proposing `extension-definition-write` with a `streamable_http` definition, `removeMcpConnection` proposing `extension-definition-delete`, `extensionLocalIdValid` refusing a malformed connection ID before it reaches the backend, a refused add and a refused delete each surfacing the backend's reason (for both the connection and the pre-existing skill-delete path), the "Remove connection" control gating on `isOperatorOwnedProvenance`, and a DOM-level render of the Add MCP Connection form asserting its human labels (`Display name`, `Connection ID`, `Add connection`) and that submitting it reaches `extension-definition-write` with typed arguments.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers `importSkill` proposing `extension-skill-write` with a fresh skill ID and body, a malformed skill ID refused before it reaches the backend, a refused import surfacing the backend's reason, and a DOM-level render of the Import Skill form asserting its `Skill ID (e.g. changelog-writer)` label and body placeholder, and that submitting it reaches `extension-skill-write` with typed arguments.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers a completed invocation on the selected extension refreshing its runtime detail, an `awaiting_approval` invocation leaving the runtime untouched, and `operationDisplayName`/`operationSubmitLabel` naming the `discover` operation "Discover tools and resources" / "Discover" while leaving every other operation's raw name and "Invoke" label unchanged.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers `operationKind` grouping `tool:`/`resource:`/`prompt:`-prefixed operations correctly while refusing to miscategorize a bare non-MCP operation name such as ACP's `prompt` or the tool family's `run`, `operationShortLabel` stripping the group prefix for display, and a DOM-level render of a discovered connection's detail asserting three separate "Tools"/"Resources"/"Prompts" headings with short (unprefixed) operation labels underneath each.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers the catalog list and detail columns keeping a manually-set `scrollTop` across a `refreshRuns()`-triggered re-render, the same trigger run polling uses every second while the panel is open.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers a rendered extension detail's raw source path and revision counter being absent from the primary facts block and present only inside a "Details" disclosure.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers `operationSubmitLabel` returning "Read" for a `resource:` operation, "Get prompt" for a `prompt:` operation, "Discover" for `discover`, and "Invoke" for a `tool:` or non-MCP operation, and a DOM-level render asserting all four submit verbs appear in the correct order alongside their grouped headings.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers a focused catalog row, and separately a state-transition button, "Show body", and "Remove connection", each regaining focus on a freshly rendered element (not the stale reference) after a `refreshCatalog()`-triggered re-render - four distinct rendering branches proven individually rather than inferred from the row case alone.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers `formatRunStarted` producing a locale time string, falling back to the raw value for an unparseable timestamp, and returning "—" for a missing one; and a DOM-level render asserting a run's raw id is absent from its status-led heading and reachable only behind a "Run details" disclosure alongside its proposal id.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers `parseAllowlist` trimming and dropping empty comma-separated items, `addMcpConnection` adding `tool_allowlist`/`resource_allowlist`/`prompt_allowlist` to the proposed definition only for fields with a non-empty value, and a DOM-level render of the Add MCP Connection form asserting the three new allowlist inputs' placeholders and that filling in one of them reaches `extension-definition-write` with that allowlist in the definition.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers the Add MCP Connection submit button, the Import Skill submit button, the Store credential submit button, and an operation's submit button each regaining focus on a freshly rendered element after a `refreshCatalog()`-triggered re-render, extending the earlier catalog-row/state-button/Show-body/Remove-connection proof to the four submit buttons named in Follow-up as the remaining gap.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers `formatPromptMessages` extracting role/text pairs from a prompt-shaped result, refusing to misread a tool-shaped `{content: [...]}` result as a prompt result, returning null for an empty messages array, falling back to null for non-text prompt content, and a DOM-level render asserting a prompt run's result appears as role-labeled message text while a tool run's result in the same run list still falls back to its raw JSON block.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers `parseCommandLines` splitting one argv token per line and dropping blank lines, `addLocalTool` proposing `extension-definition-write` with a `tool` definition shaped as `{command, process: {subprocess, argv_allowlist, env_passthrough, working_root}}`, a malformed tool ID refused before it reaches the backend, a refused add and a refused delete each surfacing the backend's reason, "Remove tool" gating on `isOperatorOwnedProvenance`, and a DOM-level render of the Add Local Tool form asserting its command/argv-allowlist/working-root controls and that submitting it reaches `extension-definition-write` with typed, argv-shaped arguments. Separately confirmed by direct backend parsing (`parse_definition_manifest` and `ProcessBoundary.from_mapping(...).validate_argv(...)`) that the desktop's produced payload shape is accepted, not just internally self-consistent.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.
- `npm --prefix desktop test`: PASS. Output: `desktop static, advanced-control, memory, action, extension, and agent behavior checks passed`. Covers `addLocalTool` sending `process.subprocess: true` even when a caller passes `subprocess: false`, since it is a fixed fact about every tool's `privileged_execution` effect class rather than a value the function reads from its argument at all - a correction after the form's now-removed "Runs as a subprocess" checkbox was found to offer an unchecked state that boundaries.py unconditionally rejects.
- `cargo check --manifest-path desktop/src-tauri/Cargo.toml`: PASS. No Tauri-side change; this increment is desktop-JS only.

Protocol tests required execution outside the restricted runner because its asyncio
subprocess/thread I/O stalled. Live native desktop behavior, remote deployment,
and other host classes remain unverified. The declared process controls are not
an OS sandbox.

## Follow-up

Human-familiar extension surfaces:
- Replace the generic capability-console path with family-specific Advanced Controls sections. Operators should see Add, Edit, Connect, Discover, Run, Disable, Remove, and Retire workflows, not capability IDs such as `extension-definition-write` or raw JSON definition forms.
- Source and revision sit behind a "Details" disclosure in the extension detail view, and a run's id/proposal id sit behind a "Run details" disclosure with its heading now showing a start time instead - both instead of the primary facts/heading. What remains: authorization decisions and fingerprint values still have no rendering at all in the desktop (not even behind a disclosure), and a run's own status/events/result are not yet reorganized beyond the heading and disclosure split just made.
- Scroll position (catalog list and detail columns), draft form values, and focus on a non-form control are all preserved across refreshes and run polling; selection was already preserved because `selectedExtensionId` only changes on an explicit user action. The non-form controls covered now include a catalog row, a state-transition button, "Show body", "Remove connection", and the four submit buttons that themselves trigger the re-render that would otherwise unfocus them (an operation's submit button, and the Add MCP Connection, Import Skill, and Store credential forms' own submit buttons).

MCP connections:
- Add MCP Connection exists for `streamable_http` connections (display name, connection ID, URL). Extend it to `stdio` connections (command, argv allowlist, environment passthrough, working root) and add an Edit MCP Connection flow so an existing connection's fields can change without deleting and re-adding it.
- Allowed tools/resources/prompts are now fields on the connection form itself, sent only when non-empty so a blank field still means unrestricted rather than deny-all. Credential type and OAuth configuration remain out of the form; they are configured only after the connection exists, through the separate credential form and OAuth flow already in the detail view.
- Discover Tools and Resources / Refresh Health exists as the "Discover" control on a selected connection's `discover` operation, and a completed invocation now refreshes the displayed health and discovered list immediately. Connect / Reconnect already exists, but only for OAuth-configured connections, where it is the authorize/reauthorize control; a non-OAuth connection has no explicit connect step because invoking any operation against it connects implicitly. Disconnect has no backend concept to attach to yet: a connection is not held open between operations (each invocation opens and closes its own peer), and there is no revoke/clear-authorization route for an OAuth connection either. Remove already exists as "Remove connection", gated on operator provenance the same way skill removal is.
- Discovered tools, resources, and prompts render under separate "Tools"/"Resources"/"Prompts" headings with the internal `tool:`/`resource:`/`prompt:` prefix stripped from their display label. Tools render operation forms from schema with per-field inputs and a JSON-parse validation error; resources submit as "Read" and prompts as "Get prompt" instead of the generic "Invoke", matching what each operation's already-correct schema (empty for a resource, a small fixed field set for a prompt) actually does. A "Get prompt" result now renders as role-labeled message text instead of raw JSON, detected by its distinct `{messages: [...]}` shape rather than needing the run to record which operation produced it. What remains is presentational only: a resource still renders as a bare submit button rather than a URI/content-preview view.

Skills and tools:
- Import Skill, Edit Skill, and Remove Skill exist for operator-owned skills; application-owned skills remain read-only. Show Instructions is covered by the existing generic "Show body" control; Requested Capabilities already renders as its own detail block.
- Add Local Tool and Remove Local Tool exist, the latter gated on operator provenance like MCP connection and skill removal. The add form's labeled command (one argv token per line), argv allowlist, environment passthrough, and working root fields match what the backend actually validates for a `tool` definition. A per-tool timeout, output setting, and argument schema are not form fields because the backend does not accept or use them today: `run` always executes with a fixed 60-second timeout and an empty input schema, regardless of the definition. `subprocess` is also not a form field, even though it is a required part of the `process` mapping: every tool registers as `privileged_execution`, and the backend unconditionally rejects `subprocess: false` for that effect class, so it is sent as a fixed `true` rather than offered as a choice with only one non-failing answer. Edit Local Tool does not exist, for the same reason Edit MCP Connection does not: there is no backend route to read a stored definition back for editing.

Hooks and plugins:
- Provide Add Hook and Edit Hook flows organized by event, matcher, handler type, and effect. Show last run, failure, and disable controls in the hook detail view.
- Provide Install Local Plugin, Inspect Plugin Contents, Enable/Disable, Remove, and Retire flows. Remote plugin sources and arbitrary install scripts remain out of scope unless a later ADR approves them.

Assistant integration and validation:
- Keep model-selected extension use behind the same backend capability selection and evidence path, but display results to the operator as the named tool/resource/prompt that ran.
- Validate the revised surfaces with focused backend tests, `npm --prefix desktop test`, `cargo check --manifest-path desktop/src-tauri/Cargo.toml`, and a native visible `windows-amd64` desktop run that exercises the MCP, skill, tool, hook, and plugin workflows.
