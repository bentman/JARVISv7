# 0006 - Ways to Extend Assistant Ability to Act

Date: 2026-09-01
Status: Accepted
Related: 0002, 0003, 0004, 0005, 0007, 0008

## Context and Problem Statement

JARVISv7 needs reusable ways to extend what the assistant can know, configure, invoke, and do without creating a separate trust model for every new feature.

At the time of this decision, operator settings, personality profiles, model provider profiles, search providers, prompt authority boundaries, action records, and turn artifacts provided foundations for a general extension system.

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

This ADR is partially implemented. The extension catalog, governed runtime, model-selected operations, MCP/skill/local-tool workflows, and readable run evidence are built. MCP code follow-ups are complete with automated validation. Hook/plugin workflows and native interaction validation remain incomplete.

### Catalog and declarative lifecycle

`backend/app/extensions/` owns descriptors, discovery, lifecycle, and storage. Descriptors carry stable family/ID identity, provenance, trust, state, readiness, dependencies, collisions, and untrusted metadata claims. The catalog observes current definitions and dependencies; `data/operator.sqlite` persists operator overlays and lifecycle events.

Application defaults live under `config/extensions/`; operator definitions live under `data/extensions/`. Application definitions take precedence and cannot be overwritten by operator additions. `config/extensions/README.md` describes the family contracts. Settings, personality, provider, search, and prompt surfaces participate in the catalog; ADR 0003 owns prompt authority, ADR 0004 owns memory boundaries, and ADR 0005 supplies governed execution. ACP adapter definitions declare process boundaries here; ADR 0007 owns their agent runtime behavior.

`ExtensionService` and `ExtensionRuntimeService` expose catalog detail and governed definition/state operations through `backend/app/api/routes/extensions.py`. Editable operator manifests round-trip name, version, enablement, dependencies, metadata, and definition fields. Atomic writes and content fingerprints distinguish creation from update and refuse stale edits. Plugin-installed children and application definitions do not claim standalone operator editability.

Definition edit/delete closes associated connections and invalidates cached discovery. `ExtensionService.set_state` owns teardown after a successful overlay transition away from enabled, through the session closer injected in `backend/app/api/app.py`. Both the operator route and capability handler use this service. A rejected update leaves the connection running; unconfirmed teardown raises an error after the state write, without rolling it back.

### Governed operations and assistant integration

`ExtensionRuntimeService` registers operations through ADR 0005. Approvals bind a definition fingerprint and are revalidated before execution. `ExtensionRuns` persists progress, input requests, results, and interrupted-run state without replaying effects after restart.

Dedicated operator invocation uses `CapabilityService.invoke_operator_capability`: a specific operator request runs without self-approval, while preserving execution boundaries, cancellation, elicitation, and evidence. Model proposals use the ordinary approval ladder. Uncertain effects remain `outcome_unknown` in both run and action records.

`backend/app/cognition/tool_policy.py`, `LLMBase.generate_with_tools`, and `TurnEngine` offer eligible extension operations within the context budget. Results return as untrusted tool context. Model-selected approval is resolved through the conversation; one capability executes per turn. Operations requiring nested operator input are directed to the Extensions panel. Agent/ACP selection is owned by ADR 0007.

### MCP connections

`backend/app/extensions/mcp.py` implements SDK-backed stdio and streamable HTTP connections, paginated discovery, schema-preserving tool/resource/prompt records, allowlists, cancellation, and host callbacks. Absent or empty allowlists mean unrestricted access within the connection's other controls. Stdio definitions require explicit command, argv/environment allowlists, and working root.

Both transports attach to ADR 0005's shared `SessionManager`. A stdio process stays open across discovery, tool calls, resource reads, and prompt fetches. Host elicitation context is rebound for each call. SDK connection-closed errors trigger cleanup and eviction; ordinary tool errors do not evict a healthy connection. The failed call is not replayed automatically; later use can open a replacement.

MCP uses the SDK's close path for both graceful and forceful termination. The manager awaits that single attempt, allowing the SDK's subprocess termination escalation to finish. Unconfirmed teardown remains tracked and subsequent Disconnect attempts remain unconfirmed; the adapter has no separate forceful retry beneath that path.

`extension-mcp-disconnect`, exposed through `POST /extensions/{extension_id}/disconnect`, ends the held connection while preserving its definition, enablement, and credentials. Confirmed disconnection permits reopening on next use. An unconfirmed close raises instead of reporting success. Runtime detail reports `connected` separately from the cached discovery snapshot; a retained, unconfirmed resource remains connected in that accounting even though further calls are blocked.

Discovery snapshots persist across backend restarts so operations remain discoverable. Restored health starts as unknown. Desktop shows “not connected” when live connection accounting is false, rather than presenting cached ready health as current.

Operation classification is `external_read` for discovery, resource reads, and prompt fetches on either transport. Tool annotations refine classification: boolean `destructiveHint: true` selects `destructive_action`; otherwise boolean `readOnlyHint: true` selects `external_read`. Missing or malformed hints retain the transport default (`privileged_execution` for stdio, `external_write` for HTTP). Destructive claims take precedence over conflicting read-only claims. All MCP tool capabilities retain `requires_approval` for model proposals because server metadata cannot grant authority. Specific operator requests execute directly, and stdio process boundaries remain enforced regardless of classification.

### Credentials and authorization

`backend/app/extensions/mcp_oauth.py` implements authorization-code flow, state-bound single-use verifiers, resource-bound token requests, endpoint discovery or explicit endpoints, local callback handling, and token refresh. Tokens persist in the encrypted operator secret store. `ExtensionRuntimeService.mcp_credentials` resolves credentials when opening the connection; missing OAuth authorization is refused. A stdio credential reference must be included in the process environment allowlist.

The desktop provides credential storage and OAuth authorize/reauthorize/complete/status flows through dedicated backend routes. Add/Edit forms carry credential references and OAuth configuration, preserve unedited fields, and refuse inline secrets.

“Forget authorization” removes the local stored OAuth token and pending flow and closes the cached connection so its bearer header cannot be reused. It does not revoke authorization at the remote server. Unconfirmed teardown raises a partial-failure error through the existing route: local authorization was removed, but the connection may still be running. Repeated requests remain unconfirmed while the shared manager retains that resource and blocks new work. The desktop refreshes authorization and connection detail on both success and failure, preserving the error instead of showing an unconditional success notice.

### Operator workflows and other families

`desktop/src/components/extensions-panel.js`, `desktop/src/api-client.js`, `desktop/src/main.js`, and the Tauri bindings provide:

- MCP Add/Edit/Remove for stdio and HTTP, discovery, grouped Tools/Resources/Prompts, invocation, Disconnect, credentials, and OAuth controls. Edits preserve hidden manifest fields and use fingerprints; transport is fixed at creation.
- Skill Import/Edit/Remove with progressive body disclosure and provenance-based editability. Skill authority-bearing fields are rejected; requested tools are metadata, and scripts execute as governed processes.
- Local Tool Add/Edit/Remove for fixed argv commands with explicit process boundaries. Current tools accept no invocation-time argument schema.
- Run identity, masked requested inputs, progress, readable event/failure summaries, cancellation, structured elicitation, model-proposal decisions, and explicit unknown-outcome warnings. Text tool results, prompt messages, and text/image resources render from their actual wrapped result. Discovery shows counts and artifacts are listed when present; full results, unsupported content, events, and correlation IDs remain in Run details. Records created before operation metadata was retained still render their status and existing evidence.
- Preserved drafts, scroll, and keyed control focus across panel refreshes; source, revision, and internal identifiers remain available through detail disclosure.

Native `invoke_extension` is async and dispatches the blocking backend request through `tauri::async_runtime::spawn_blocking`. Actual nested elicitation and cancellation inside the native Tauri application remain unverified.

`backend/app/extensions/hooks.py` supplies closed lifecycle event names, event recording, and governed capability dispatch. `backend/app/extensions/plugins.py` supplies bounded local installation, bundle hashing, and child-definition validation. Their dedicated operator workflows remain incomplete.

## Confirmation

Coverage tied to the implemented contracts:

- `backend/tests/integration/test_extension_runtime.py`: real stdio reuse and process death, Disconnect/reopen, a server that ignores SIGTERM, current-call elicitation ownership, operator execution versus model approval, state teardown through route and capability paths, rejected updates, failed/repeated Disconnect, unknown outcomes, credential invalidation, and definition/skill lifecycle.
- `backend/tests/integration/test_mcp_sdk.py`: SDK peer behavior.
- `backend/tests/unit/extensions/`: catalog, definitions, family runners, MCP and OAuth contracts.
- `backend/tests/unit/services/test_extension_service.py`: extension service behavior.
- `desktop/tests/static.test.mjs`: form round-trips and handler wiring, wrapped-result rendering, Disconnect refresh, connection status, and unknown-outcome presentation.

Recorded validation:

- Windows-amd64: `backend\.venv\Scripts\python scripts/validate_backend.py integration`: PASS, 60 passed. Unit validator and Tauri build evidence are recorded in ADR 0005.
- Windows-amd64: `npm --prefix desktop test`: PASS, including repeated OAuth partial-failure refresh, named runs, requested inputs, readable tool output/events, and full result disclosure.
- `test_oauth_forget_closes_the_live_session_so_a_stale_credential_cannot_keep_being_used` covers successful, failed, and absent connections through the production route and real SessionManager. Repeated failed requests preserve token deletion, clear pending flows, retain the resource, and refuse new work. An in-memory substitution that ignored close confirmation made the test fail with `DID NOT RAISE HTTPException`; production files were not changed for that negative check.
- `test_mcp_tool_hints_classify_effects_without_authorizing_model_calls` covers both transports, absent/malformed/conflicting hints, model approval, direct operator execution, and masked run metadata.
- Live backend and browser checks exercised stdio creation/discovery and resource text preview. A seeded token in the real encrypted store demonstrated Forget authorization and status refresh; this did not test an external authorization-server round trip.
- Real-process tests cover termination and reuse; synthetic handlers cover unconfirmed teardown and credential invalidation. These are distinct evidence boundaries.

Native interaction validation belongs to ADR 0008 and was excluded from this closeout. Remote deployment and other host classes remain unverified.

## Follow-up

- Verify invocation, nested elicitation, answering input, cancellation, Disconnect, and session failure (`outcome_unknown`) recovery in the actual native Tauri application. ADR 0008 owns native interaction validation.
- Add Hook creation/editing by event, effect, target, and arguments, with event history, failure visibility, and disable controls.
- Add local Plugin install/inspect/enable/disable/remove/retire workflows. Implement any missing bundle-removal contract before exposing removal. Remote sources and arbitrary install scripts require a separate decision.
- Complete backend validator and desktop contract evidence for the unfinished workflows before marking the ADR implemented.
