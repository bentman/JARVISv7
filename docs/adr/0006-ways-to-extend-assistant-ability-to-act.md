# 0006 - Ways to Extend Assistant Ability to Act

Date: 2026-09-01
Status: Implemented
Related: 0003, 0005, 0008, 0010, 0012, 0013

## Context and Problem Statement

JARVISv7 needs reusable ways to extend what the assistant can know, configure, invoke, and do without creating a separate trust model for every new feature.

At the time of this decision, operator settings, personality profiles, model provider profiles, search providers, prompt authority boundaries, action records, and turn artifacts provided foundations for a general extension system.

Extension families may include reusable prompts, skills, MCP connections, hooks, plugins, connectors, and adapter definitions used by delegated agents. Some of those only shape context or operator choice; others can read private data, send data outward, mutate state, run code, or delegate work. The architecture needs one way to classify those surfaces and one governed execution path for anything with side effects.

This ADR owns the extension taxonomy, cataloging, declarative lifecycle, and the governed operation path shared by every family. Family-specific protocol behavior belongs to the ADR that owns that family.

## Decision Drivers

- Keep extension labels distinct by function so settings, prompts, skills, tools, providers, hooks, plugins, MCP connections, and agent adapter definitions do not collapse into one vague abstraction.
- Preserve ADR 0003's authority boundaries and ADR 0005's governed action model.
- Make low-risk extension surfaces ergonomic while routing executable or externally visible effects through explicit capability records.
- Track provenance, trust, readiness, enablement, health, dependency state, and collisions before broad model-callable extension exposure.
- Keep the desktop a thin surface over backend-owned policy, registry, execution, artifacts, and API contracts.

## Decision Outcome

JARVISv7 defines extension shapes by function first:

- settings: scoped operator choices and defaults
- instructions/personality: behavior and style guidance
- reusable prompts: templates for recurring work starts
- skills: portable procedural bundles
- tools/capabilities: executable actions with schema, readiness, authorization, result, and artifact evidence
- MCP connections: external resources, prompts, and tools exposed through a host-controlled connection boundary
- ACP adapter definitions: declarative process-boundary records used by agent runtimes
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
- Hook behavior can become surprising unless event names, effects, and failure paths stay small and visible.

## Implementation

### Catalog and declarative lifecycle

`backend/app/extensions/` owns descriptors, discovery, lifecycle, and storage. Descriptors carry stable family/ID identity, provenance, trust, state, readiness, dependencies, collisions, and untrusted metadata claims. The catalog observes current definitions and dependencies; `data/operator.sqlite` persists operator overlays and lifecycle events.

Application defaults live under `config/extensions/`; operator definitions live under `data/extensions/`. Application definitions take precedence and cannot be overwritten by operator additions. `config/extensions/README.md` describes the family contracts. Settings, personality, provider, search, and prompt surfaces participate in the catalog.

`ExtensionService` and `ExtensionRuntimeService` expose catalog detail and governed definition/state operations through `backend/app/api/routes/extensions.py`. Editable operator manifests round-trip name, version, enablement, dependencies, metadata, and definition fields. Atomic writes and content fingerprints distinguish creation from update and refuse stale edits. Plugin-installed children and application definitions do not claim standalone operator editability.

Definition edit/delete closes associated connections and invalidates cached discovery. `ExtensionService.set_state` owns teardown after a successful overlay transition away from enabled, through the session closer injected in `backend/app/api/app.py`. Both the operator route and capability handler use this service. A rejected update leaves the connection running; unconfirmed teardown raises an error after the state write, without rolling it back.

### Governed operations and assistant integration

`ExtensionRuntimeService` registers operations through ADR 0005. Approvals bind a definition fingerprint and are revalidated before execution. `ExtensionRuns` persists progress, input requests, results, and interrupted-run state without replaying effects after restart. Extension run records retain operation identity, display name, and arguments masked by the existing action policy.

Dedicated operator invocation uses `CapabilityService.invoke_operator_capability`: a specific operator request runs without self-approval, while preserving execution boundaries, cancellation, elicitation, and evidence. Model proposals use the ordinary approval ladder. Uncertain effects remain `outcome_unknown` in both run and action records.

`backend/app/cognition/tool_policy.py`, `LLMBase.generate_with_tools`, and `TurnEngine` offer eligible extension operations within the context budget. Results return as untrusted tool context. Model-selected approval is resolved through the conversation; one capability executes per turn. Operations requiring nested operator input are directed to the Extensions panel.

### Skills and local tools

Skills are portable procedural bundles with provenance-based editability. Skill authority-bearing fields are rejected; requested tools are metadata, and scripts execute as governed processes under ADR 0005 boundaries.

Local tools are fixed-argv commands with explicit process boundaries. Current tools accept no invocation-time argument schema.

### Boundaries owned elsewhere

ADR 0003 owns prompt authority. ADR 0005 owns governed execution and evidence. ADR 0010 and ADR 0011 own MCP connection and authorization behavior. ADR 0012 owns hook and plugin workflows; `backend/app/extensions/hooks.py` and `backend/app/extensions/plugins.py` supply scaffolding that ADR 0012 has not yet decided operator workflows for. ADR 0013 owns ACP adapter runtime behavior for the adapter definitions declared here. ADR 0008 owns operator-facing extension workflows.

## Confirmation

Implementation files:
- `backend/app/extensions/contracts.py`
- `backend/app/extensions/catalog.py`
- `backend/app/extensions/discovery.py`
- `backend/app/extensions/lifecycle.py`
- `backend/app/extensions/store.py`
- `backend/app/extensions/runs.py`
- `backend/app/extensions/skills.py`
- `backend/app/extensions/prompts.py`
- `backend/app/services/extension_service.py`
- `backend/app/services/extension_runtime_service.py`
- `backend/app/cognition/tool_policy.py`
- `backend/app/api/routes/extensions.py`
- `config/extensions/README.md`

Test coverage:
- `backend/tests/unit/extensions/test_extension_catalog.py`
- `backend/tests/unit/extensions/test_extension_contracts.py`
- `backend/tests/unit/extensions/test_skill_loading.py`
- `backend/tests/unit/extensions/test_prompt_templates.py`
- `backend/tests/unit/services/test_extension_service.py`
- `backend/tests/integration/test_extension_runtime.py` for definition and skill lifecycle, rejected updates, state teardown, tool-policy offering, and run evidence

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration` when catalog, lifecycle, or governed-operation behavior changes

## Follow-up

None for this ADR.

Future extension families, changes to the taxonomy, or a change to how a family reaches the governed execution path should update this ADR when they preserve the same extension architecture, or create/supersede an ADR when they change it.
