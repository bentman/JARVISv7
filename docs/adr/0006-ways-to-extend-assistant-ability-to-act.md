# 0006 - Ways to Extend Assistant Ability to Act

## Status

Accepted, living.

## Context

JARVISv7 grows through distinct extension shapes. Settings, instructions, prompts, skills, MCP connections, hooks, plugins, providers, integrations, tools, and agents each serve a different function.

The sixth project promise is reusable ways to extend the assistant. Extensions feel natural to use while passing through the same interaction, memory, artifact, and action boundaries defined by ADR 0002 through ADR 0005.

Current v7 has foundations for this: scoped settings, personality profiles, provider profiles, search providers, prompt authority boundaries, action evidence, and memory artifacts. The next extension layer is a general extension registry, skill runtime, MCP connection manager, hook runner, plugin package lifecycle, and ACP agent/client bridge.

Current public practice points to the same split. MCP standardizes stateless external context, tool, prompt, and extension connections. ACP, in this ADR, means Agent Client Protocol v2: a development-target coding-agent/client interoperability protocol for initialization, sessions, updates, cancellation, permission requests, filesystem and terminal mediation, authentication, MCP configuration, and extensibility. Agent Skills use a portable `SKILL.md` directory shape with optional scripts, references, and assets. Provider tool systems distinguish hosted tools, local tools, function tools, MCP tools, and agents-as-tools.

## Decision

JARVISv7 will define extensions by function first, then route executable effects through the governed capability loop from ADR 0005.

The extension shapes are:

- settings: scoped operator choices and defaults
- instructions/personality: behavior and style guidance, never hidden authority
- reusable prompts: user-invoked templates for recurring starts
- skills: portable procedural bundles, not direct authority by themselves
- tools/capabilities: executable actions with schema, readiness, authorization, result, and artifact evidence
- MCP connections: external resources, prompts, and tools exposed through a host-controlled connection boundary
- ACP agents/clients: agent process and client-session interoperability for delegated assistants and future TUI/client surfaces
- hooks: deterministic lifecycle actions tied to visible events
- plugins: installable packages that bundle one or more extension shapes
- providers/connectors: named model, service, or external-account relationships with readiness, credentials, and permission boundaries

No extension shape gets a parallel execution path. If it reads private data, sends data outward, mutates state, runs code, delegates to an agent, or calls a service, it must become or invoke a capability record and use the shared authorization, approval, cancellation, artifact, and memory flow.

Prefer modern protocol boundaries:

- Use MCP for external tool/resource/prompt connections.
- Use ACP for agent/client session control, delegated agent workers, permission requests, progress updates, cancellation, and future TUI interoperability.
- Use skills for portable procedural knowledge and reusable task methods.
- Use plugins only for packaging, installation, trust, versioning, and lifecycle.

## Current Design

Settings are implemented through `Settings`, `SETTING_ENV_CLASSIFICATION`, and the operator-config route. Operator writes are allowlisted and secrets are masked.

Personality profiles are implemented as structured YAML under `config/personality/`. The schema rejects authority fields such as tool policy, routing policy, memory policy, hidden instructions, and safety overrides. Prompt rendering preserves provenance and authority labels.

Provider profiles are implemented through a local operator SQLite store with profile validation, endpoint normalization, encrypted secrets, readiness state, local fallback, and governed cloud escalation.

Search providers are implemented as optional external-read capabilities. Search planning rejects secrets, confirms private outbound search, executes bounded provider attempts, supports cancellation, and records evidence in turn artifacts.

Prompt and artifact structures reserve extension boundaries. `PromptEnvelope` includes authority labels and tool-result content types. `TurnArtifact` records tools invoked, search evidence, memory evidence, runtime context, failure state, and timings.

The current `backend/app/core/capabilities.py` describes hardware/runtime capability flags. It is not a general extension or model-callable capability registry.

## Extension Rules

Settings change how JARVIS operates. They are scoped, typed, inspectable, and stored through existing config paths.

Instructions and personalities shape behavior. Access, safety policy, memory rules, and tool selection remain owned by application policy and capability records.

Reusable prompts help the user begin recurring work. They are templates.

Skills teach procedure. A skill may include instructions, scripts, examples, templates, references, and assets. Loading a skill uses progressive disclosure: metadata for discovery, `SKILL.md` on activation, supporting files only when needed. Any script or external action used by a skill runs through a governed capability before execution.

MCP connections expose external resources, prompts, tools, and opt-in extensions. MCP server metadata, annotations, and descriptions are declarations by that server. The host controls transport, credentials, per-request protocol metadata, resource exposure, elicitation, schema conversion, filtering, approval, errors, health, and disconnection. New v7 design uses explicit tool parameters, resource URIs, server configuration, and direct provider APIs; deprecated MCP roots and sampling are compatibility shims.

ACP agents and clients expose a session protocol. An ACP bridge maps initialize/auth/session/prompt/update/permission/cancel events into the same JARVIS session, approval, artifact, and memory model. ACP agent memory writes, tool execution, and file access run through approved capability paths.

Hooks run deterministic behavior at known lifecycle events. They need event names, scope, effect class, timeout, failure behavior, and visibility.

Plugins are packaging. Installing a plugin may add prompts, skills, MCP definitions, settings, hooks, UI contributions, tools, or agents, but each contained extension keeps its own function and governance.

Providers and connectors represent relationships with model runtimes, services, or external accounts. They need readiness, credential status, health, permission scope, and clear failure states.

## Consequences

Benefits:

- Extension work can proceed without inventing a new trust model per feature.
- MCP, ACP, skills, hooks, plugins, prompts, and tools remain distinguishable.
- Low-risk extensions stay ergonomic because governance is tied to effect, not label.
- Desktop, CLI/script, daemon, and future TUI clients can share one capability and approval model.
- External metadata cannot grant itself authority.

Costs:

- A real extension system requires shared registry, lifecycle, authorization, and artifact infrastructure before broad tool use is enabled.
- Provider-native tool and MCP features may need wrapping before they fit v7's evidence model.
- Skill and plugin imports need provenance tracking, otherwise user-authored code can look application-owned.
- ACP integration adds process/session state that must be kept aligned with the one interaction loop.
- Hook behavior can become surprising unless event names, effects, and failure paths stay small and visible.

## Remaining Work

- Define one extension registry or catalog shape for prompts, skills, MCP connections, hooks, plugins, providers, connectors, tools, and agents.
- Define stable IDs, versions, source/provenance, trust status, enabled state, health state, dependency state, collision rules, and retirement behavior.
- Build the governed capability registry from ADR 0005 before exposing model-callable extensions broadly.
- Add skill import/loading using `SKILL.md`, progressive disclosure, provenance, compatibility metadata, and optional script/reference/asset handling.
- Treat `allowed-tools` or similar skill metadata as requested capability use, not application permission.
- Add MCP connection management for stdio and Streamable HTTP first. Keep HTTP+SSE as compatibility support only when required.
- Preserve MCP tool schemas and content blocks as faithfully as possible, including JSON Schema 2020-12 where supported. Report unsupported schema features, and keep server annotations separate from permission.
- Add MCP discovery, per-request protocol metadata, health probing, bounded timeouts, cancellation, credential handling, tool filtering, resource exposure, elicitation, and per-call approval mapping.
- Treat MCP roots and sampling as deprecated compatibility features. Prefer explicit tool parameters, resource URIs, server configuration, and direct provider APIs for new design.
- Add an ACP bridge for agent subprocess/session integration and future TUI/client interoperability.
- Map ACP permission requests, session updates, terminal/tool chunks, cancellation, and stop reasons into JARVIS approvals, artifacts, and turn/session state.
- Define hook lifecycle events and effect classes before adding a hook runner.
- Define plugin install/enable/disable/update/uninstall behavior as packaging lifecycle, with contained extensions registered separately.
- Keep non-agent interaction functional when skills, MCP, plugins, hooks, or agents are disabled.

## Implementation Path

Add extension support as metadata and discovery before execution:

1. Keep existing settings, personality, provider-profile, and search-provider paths as the first extension-like examples.
2. Add an extension catalog under `backend/app/` only when a second extension family needs shared identity, provenance, trust, health, or enablement.
3. Add prompt/template discovery before skill execution.
4. Add skill loading from `SKILL.md` as procedural metadata before allowing scripts or model-callable skill use.
5. Add MCP discovery and health before MCP tool invocation; route invocation through ADR 0005 capability records.
6. Add plugin lifecycle only as packaging around registered prompts, skills, MCP definitions, hooks, providers, tools, or agents.
7. Add focused tests for catalog loading, provenance, collision handling, disabled-state behavior, and no-capability execution leakage.

Dependencies: executable extensions depend on the ADR 0005 capability registry, provenance/trust metadata, health checks, disabled-state behavior, approval records, and artifact recording.

Targets: extension catalog, prompt/template discovery, skill loader, MCP connection manager, plugin lifecycle, ACP bridge boundary, API/desktop surfaces, and focused tests.

Exit evidence: unit tests for catalog loading, provenance, collisions, disabled state, health, schema handling, and no execution leakage; service/API tests for each executable extension family before model-callable exposure.

## Guidance

When adding an extension, identify its function first. Use the smallest owning mechanism: setting, prompt, skill, tool, MCP connection, hook, plugin, provider, connector, or agent.

When adding MCP, keep JARVIS as the host. Server metadata helps discovery and model presentation, but application policy decides trust, approval, resource exposure, credentials, and execution.

When adding ACP, use it as the agent/client boundary. ACP carries sessions, updates, permission requests, cancellation, and structured user elicitation through JARVIS memory, artifact, and approval boundaries.

When adding skills, keep them portable. Use `SKILL.md` with concise metadata and body instructions, place large supporting material in `references/`, put executable helpers in `scripts/`, and route execution through governed capabilities.

When adding plugins, treat them as bundles. Register every contained prompt, skill, MCP connection, hook, tool, provider, connector, or agent with its own identity and policy.

## Evidence

Implementation:

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
- `backend/app/services/llm_provider_profiles.py`
- `backend/app/services/llm_provider_service.py`
- `backend/app/api/routes/llm_config.py`
- `backend/app/api/schemas/llm_config.py`
- `backend/app/cognition/search_policy.py`
- `backend/app/services/search_service.py`
- `backend/app/runtimes/internetsearch/`
- `backend/app/conversation/engine.py`
- `backend/app/artifacts/turn_artifact.py`
- `backend/app/core/capabilities.py`
- `desktop/src/components/settings-panel.js`
- `desktop/src/components/llm-provider-settings.js`
- `desktop/src/components/search-evidence.js`
- `desktop/src/api-client.js`
- `desktop/src-tauri/src/backend.rs`

Tests:

- `backend/tests/unit/core/test_settings.py`
- `backend/tests/unit/personality/test_personality.py`
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
- `backend/tests/unit/routing/test_provider_router.py`

External practice reviewed:

- Agent Client Protocol v2: [overview](https://github.com/agentclientprotocol/agent-client-protocol/blob/main/docs/protocol/v2/overview.mdx) for JSON-RPC methods/notifications, initialization, sessions, updates, permission requests, cancellation, client-managed environment access, and extensibility.
- Model Context Protocol: [2026-07-28 stateless core, per-request capability metadata, resources, prompts, tools, elicitation, extensions, JSON-RPC messages, and security principles](https://modelcontextprotocol.io/specification/2026-07-28), plus [deprecated roots, sampling, logging, DCR, and HTTP+SSE guidance](https://modelcontextprotocol.io/specification/2026-07-28/deprecated).
- OpenAI Agents SDK: [MCP transport choices and approval flows](https://openai.github.io/openai-agents-python/mcp/), plus [hosted/local tools, function tools, and agents-as-tools](https://openai.github.io/openai-agents-python/tools/).
- Open Agent Skills: [`SKILL.md` frontmatter, optional `scripts/`, `references/`, `assets/`, and progressive disclosure](https://openagentskills.dev/docs/specification).
- Agent Client Protocol ecosystem: [compatible agents](https://agentclientprotocol.com/get-started/agents), [registry](https://agentclientprotocol.com/get-started/registry), and [registry repository](https://github.com/agentclientprotocol/registry) showing ACP-compatible coding-agent metadata distribution and authentication checks.
