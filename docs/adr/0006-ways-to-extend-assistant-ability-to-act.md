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

## Considered Options

- Treat each extension family as a separate feature with its own lifecycle and permission model.
- Treat every extension as a tool.
- Treat plugins as the primary architecture boundary.
- Define extensions by function, then route executable effects through the governed capability loop.

## Decision Outcome

Chosen option: `Define extensions by function, then route executable effects through the governed capability loop`.

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

This ADR is partially implemented.

Implemented foundations:
- Operator settings are scoped and classified through `backend/app/core/settings.py`, `backend/app/api/routes/config.py`, and `backend/app/api/schemas/config.py`. Operator writes are allowlisted, and secrets are masked.
- Personality profiles are structured YAML under `config/personality/`. `backend/app/personality/schema.py`, `backend/app/personality/loader.py`, and `backend/app/personality/policy.py` reject authority-bearing fields such as tool policy, routing policy, memory policy, hidden instructions, and safety overrides.
- Personality selection is exposed through backend routes and schemas in `backend/app/api/routes/personality.py` and `backend/app/api/schemas/personality.py`.
- Prompt boundaries exist through `backend/app/cognition/prompt_envelope.py`, `backend/app/cognition/prompt_assembler.py`, `backend/app/cognition/prompt_renderer.py`, and `backend/app/cognition/prompt_chat_renderer.py`. Prompt segments carry authority labels, content type, and trust state.
- Provider profiles are implemented through `backend/app/services/llm_provider_profiles.py`, `backend/app/services/llm_provider_service.py`, `backend/app/api/routes/llm_config.py`, and `backend/app/api/schemas/llm_config.py`.
- Search providers are implemented as governed external-read behavior through `backend/app/cognition/search_policy.py`, `backend/app/services/search_service.py`, and `backend/app/runtimes/internetsearch/`.
- Action governance records exist in `backend/app/actions/contracts.py`: capability descriptors, availability/readiness/effect classes, model proposals, authorization decisions, approval records, execution results, metadata claims, and collision checks.
- Turn artifacts in `backend/app/artifacts/turn_artifact.py` reserve evidence fields for tools invoked, action proposals, authorization decisions, approval records, action execution results, cancellations, delegated runs, search evidence, memory evidence, runtime context, and failure state.
- Desktop surfaces call backend APIs for settings, provider profiles, search evidence, and personality selection through `desktop/src/api-client.js`, `desktop/src/components/settings-panel.js`, `desktop/src/components/llm-provider-settings.js`, `desktop/src/components/search-evidence.js`, `desktop/src/main.js`, and `desktop/src-tauri/src/backend.rs`.

Not implemented yet:
- A general extension catalog or registry covering prompts, skills, MCP connections, hooks, plugins, providers, connectors, tools, and agents.
- Prompt/template discovery as reusable user-invoked starts.
- Skill import/loading from `SKILL.md`, progressive disclosure, provenance, compatibility metadata, optional scripts, references, and assets.
- MCP connection management, discovery, health, schema preservation, resource exposure, elicitation, credential handling, cancellation, filtering, and per-call approval mapping.
- ACP bridge behavior for agent subprocess/session integration, permission requests, progress updates, terminal/tool chunks, cancellation, and stop reasons.
- Hook lifecycle events, effect classes, runner behavior, timeouts, visibility, and failure handling.
- Plugin install, enable, disable, update, uninstall, bundled extension registration, and trust/version lifecycle.
- Backend API and desktop surfaces for a unified extension catalog.

`backend/app/core/capabilities.py` is not this extension registry. It only describes hardware/runtime capability flags.

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
- `backend/app/core/capabilities.py`
- `desktop/src/api-client.js`
- `desktop/src/components/settings-panel.js`
- `desktop/src/components/llm-provider-settings.js`
- `desktop/src/components/search-evidence.js`
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
- `backend/tests/unit/artifacts/test_turn_artifact.py`
- `backend/tests/unit/actions/test_action_contracts.py`
- `backend/tests/unit/routing/test_provider_router.py`

Known absence checks:
- No source directory or file currently implements a unified extension registry/catalog.
- No source directory or file currently implements MCP connection management.
- No source directory or file currently implements ACP bridge behavior.
- No source directory or file currently implements skill loading.
- No source directory or file currently implements hook lifecycle execution.
- No source directory or file currently implements plugin lifecycle management beyond Tauri's desktop dependency plugin mechanism.
- `backend/tests/unit/api/test_routes.py` includes a route-surface guard that agent routes are absent from OpenAPI.

## Follow-up

Gaps required to complete this ADR:
- Define and implement one backend-owned extension catalog with stable IDs, versions, source/provenance, trust status, enabled state, health state, dependency state, collision behavior, and retirement behavior.
- Register existing extension-like families in that catalog where useful: settings, personality profiles, provider profiles, search providers, prompt templates, and governed action descriptors.
- Complete ADR 0005's governed capability execution path before exposing broad model-callable extensions.
- Add prompt/template discovery before skill execution.
- Add skill loading from `SKILL.md` with progressive disclosure and provenance before allowing scripts or model-callable skill use.
- Treat skill metadata such as requested tools as requested capability use, not as application permission.
- Add MCP connection management for explicit server configuration, tool/resource/prompt discovery, schema preservation, health, credentials, cancellation, filtering, resource exposure, elicitation, and approval mapping.
- Add ACP bridge behavior only through the JARVIS session, approval, artifact, and memory model.
- Define hook lifecycle events and effect classes before adding a hook runner.
- Define plugin lifecycle as packaging around separately registered contained extensions.
- Add backend API, desktop surfaces, and focused tests for catalog loading, provenance, collision handling, disabled/unavailable state, health, schema handling, and no execution leakage.
- Keep normal interaction functional when skills, MCP connections, plugins, hooks, or delegated agents are disabled.
