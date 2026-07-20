# JARVISv7 ProjectVision

## Vision

JARVISv7 is a local-first, voice-first personal assistant designed for real conversational interaction on user-owned hardware. It is not a chatbot with voice added later. It is a real-time conversation system with text as a secondary ingress and control surface.

The target experience is closer to J.A.R.V.I.S. than a browser chat application:

- the user can speak naturally
- the system listens, transcribes, reasons, responds, and speaks back
- the user can interrupt
- the system preserves continuity without hiding state inside the model
- the assistant has a defined, inspectable personality
- failures are explicit and degrade cleanly
- capabilities can expand without replacing the stable conversational foundation

JARVISv7 must be useful in a minimal conversational loop first, then grow toward richer memory, reusable skills, governed tool use, external integrations, plugins, and opt-in agent behavior.

---

## Product Identity

JARVISv7 is:

- voice-first
- desktop-first, with CLI-compatible capability surfaces where useful
- hardware-aware from process start
- cross-platform by design
- local-first by default
- deterministic in orchestration
- explicit in cognition, memory, policy, and execution
- interruptible
- personality-driven
- extensible through reusable, inspectable capability shapes
- agent-capable when the foundation is stable

JARVISv7 is not:

- a text chat system with optional voice controls
- a cloud-first assistant that happens to run locally
- a collection of disconnected AI features
- a personality-less command shell with speech attached
- a system that hides durable state inside prompts or model sessions
- a system that treats plugins, skills, tools, MCP servers, and agents as interchangeable concepts
- a system that works on one hardware class and retrofits others later

---

## Primary Goal

Build a usable voice-first assistant whose core interaction loop works end-to-end in the real runtime across supported hardware:

1. profile the host
2. provision and verify the correct runtime stack
3. emit evidence-backed capability and readiness facts
4. accept voice or text input through one interaction model
5. assemble explicit context from personality, memory, policy, and available capabilities
6. reason through a selected local runtime by default
7. act only through governed capabilities
8. return a response aligned to the configured personality
9. speak locally when TTS is available
10. allow interruption and coherent continuation
11. persist enough evidence to reconstruct what happened
12. expose failures and degraded operation clearly

This loop is the root acceptance path. Higher-level capabilities must compose with it rather than create parallel application architectures.

---

## Core Invariants

### 1. Hardware Truth Comes First

The system must profile the execution environment before selecting runtimes or advertising capability.

Provisioning translates hardware facts into installable package sets through one authority. Readiness verifies that packages, libraries, execution providers, services, and model artifacts are actually usable.

Downstream systems consume shared capability and readiness facts. They do not invent hardware policy independently.

### 2. Voice Is the Root Interaction Mode

Voice defines the primary interaction lifecycle. Text is a secondary ingress into the same conversation and cognition path.

The product must remain usable when a voice component is unavailable, but fallback behavior must not create a separate text-product architecture.

### 3. Local-First Is the Default Execution Posture

Local execution is preferred for:

- speech recognition
- speech generation
- language-model reasoning
- wake-word detection
- memory
- orchestration
- artifacts and traces
- configuration and policy

Remote capability may be added only as an explicit, inspectable, policy-controlled option. It must never be silently selected or represented as available before it works.

### 4. Orchestration Is Deterministic

Models provide interpretation and reasoning. They do not own application control flow.

State transitions, retries, interruption, approvals, tool execution, handoffs, and failure handling remain explicit and reconstructable.

### 5. Cognition Is Externalized

The model is a stateless worker unless context is explicitly supplied.

Personality, memory, instructions, plans, capabilities, tool results, agent state, and artifacts remain outside the model and are independently inspectable.

### 6. Memory Has Distinct Scopes

Memory is not one undifferentiated database. Each memory class has a separate purpose, lifetime, authority, and write policy.

No durable memory write is implicit. Retrieval does not imply permission to retain. Cache is not durable memory authority.

### 7. Capability Is Explicitly Declared

A capability is usable only when it can be discovered, authorized, invoked, observed, and failed safely.

Installed files or provider classes alone do not establish product capability.

### 8. Personality Is a Core System Dimension

Personality is structured, configurable, and applied consistently across text and voice. It shapes expression but never overrides truth, safety, policy, permissions, or deterministic orchestration.

### 9. Extension Is Layered, Not Entangled

Instructions, prompts, skills, tools, MCP servers, hooks, plugins, and agents are different extension shapes. Each must have a narrow contract and compose through stable boundaries.

### 10. Evidence Controls Completion

Live behavior on the targeted host and product path is decisive. Tests, logs, configuration, and documentation support that evidence but do not replace it.

---

## Stable Foundation Shape

The stable foundation is the capability stack on which all later assistant and agent behavior depends.

### 1. Host Capability and Readiness

Purpose:

- detect host and device capabilities
- resolve required packages and runtime artifacts
- verify actual runtime readiness
- expose truthful available, degraded, and unavailable states

This foundation informs model, STT, TTS, wake, concurrency, and degraded-mode selection.

### 2. Runtime Substrate

Purpose:

- provide local STT, TTS, LLM, and wake execution
- select device and model from readiness evidence and user policy
- manage model artifacts and executable sidecars
- expose consistent lifecycle, health, and failure boundaries

Current runtime shape:

- ONNX Whisper for STT
- Kokoro ONNX for TTS
- local llama.cpp as the preferred LLM runtime
- Ollama as a local fallback
- openWakeWord for wake detection

Runtime families may evolve, but selection must remain evidence-based and local-first.

### 3. Canonical Interaction and Session Model

A session groups related turns for continuity, interruption recovery, active preferences, and bounded working context.

A turn is one explicit interaction attempt. Voice and text enter the same lifecycle.

Canonical states conceptually include:

- startup and profiling
- idle
- listening and transcribing
- reasoning
- acting
- responding and speaking
- interrupted and recovering
- failed

The exact state vocabulary may evolve. Explicit state ownership may not.

### 4. Cognition and Context Assembly

Purpose:

- assemble the active instructions, personality, memory, retrieved context, user input, and capability facts
- invoke the selected model runtime
- constrain outputs through policy and response boundaries
- keep planning and action requests separate from action execution

Cognition must not silently gain authority from prompt text.

### 5. Memory System

The memory foundation should distinguish at least these shapes:

#### Turn Context

Ephemeral information required to complete the current turn. It expires with the turn unless explicitly promoted.

#### Working Memory

Bounded in-session context used for immediate continuity. It is replaceable, summarizable, and subject to strict size and relevance limits.

#### Session Memory

Structured session timeline, decisions, interruptions, and closeout facts used to preserve continuity across related turns.

#### Episodic Memory

Durable records of user interactions or events that may be recalled across sessions under explicit write and retrieval policy.

#### Semantic Memory

Durable facts and concepts separated from the original event wording. Semantic memory requires provenance, conflict handling, and correction paths.

#### Procedural Memory

Reusable knowledge about how to perform tasks. Skills are the primary portable shape for procedural memory; procedures should not be hidden inside conversation history.

#### Preference and Profile Memory

Explicit user and assistant settings such as personality, voice, defaults, permissions, and interaction preferences. These are configuration-backed and directly editable.

#### Artifact and Audit Memory

Turn artifacts, traces, outputs, and evidence used for reconstruction, debugging, evaluation, and governance. These records are not automatically injected into model context.

Memory writes must identify source, scope, retention, sensitivity, and authority. Redis or similar infrastructure may accelerate retrieval but does not become durable memory authority.

### 6. Personality and User Experience Policy

Purpose:

- define assistant identity and interaction style
- govern tone, brevity, formality, acknowledgments, interruption style, and spoken presentation
- keep behavior consistent across modalities
- allow selectable profiles without prompt residue or hidden state

### 7. Policy, Permissions, and Consent

Purpose:

- define what the assistant may read, write, execute, transmit, remember, and delegate
- distinguish read-only, reversible, destructive, local, and remote operations
- require user confirmation where risk or external effect warrants it
- keep credentials and secrets outside shareable capability definitions

Policy applies equally to built-in capabilities and installed extensions.

### 8. Artifacts, Observability, and Recovery

Every important interaction should leave enough structured evidence to explain:

- what the user requested
- what context and capability facts were used
- what state transitions occurred
- which external actions were attempted
- what results or errors occurred
- what was retained
- why the final response or failure was produced

Observability is part of product behavior, not only developer diagnostics.

### 9. Product Surfaces

The desktop shell is the durable user-facing home of JARVISv7. CLI surfaces may expose the same capability contracts for setup, diagnostics, automation, or coding-agent use.

Neither surface owns core orchestration. Both are adapters over stable backend capability boundaries.

---

## Extension and Customization Shapes

The remaining assistant should grow through recognized reusable shapes rather than project-specific substitutes.

### General Settings and Configuration

Configuration should be layered by scope:

- product defaults
- host and hardware-derived facts
- user settings
- workspace or project settings
- session overrides
- capability-specific settings
- secrets and credentials

Later scopes may override earlier configurable values, but detected facts and security boundaries must not be falsified by ordinary preference settings.

Settings should remain discoverable, validated, exportable where safe, and separable from secrets.

### Instructions

Instructions define durable behavioral constraints and conventions.

Useful scopes include:

- system or product instructions
- user instructions
- project/workspace instructions
- path or domain-specific instructions
- agent-specific instructions

Instructions are generally persistent context. They are not executable tools and should not become a substitute for deterministic policy.

### Reusable Prompts

Reusable prompts are user-invoked templates for repeatable requests or workflows. They should be easy to discover, parameterize, and invoke without pretending to be autonomous capabilities.

### Skills

Skills are portable procedural capability bundles. The preferred shape follows the open Agent Skills ecosystem used across current coding agents:

- a skill directory
- a `SKILL.md` entry point with identity and discovery metadata
- task instructions
- optional scripts, examples, templates, and supporting resources
- progressive loading so only relevant skill content enters context

Skills teach the assistant how to perform a bounded class of work. They may use tools, but they are not tools themselves.

JARVISv7 should be able to consume compatible skills from established ecosystems such as Agent Skills and directories such as skills.sh after review and trust evaluation.

### Tools

Tools are schema-defined executable capabilities.

Each tool shape should expose:

- stable identity and description
- structured input contract
- structured or typed result contract where practical
- capability and permission requirements
- side-effect classification
- timeout, cancellation, and failure behavior
- audit evidence

Tools may be built in, provided by plugins, exposed through MCP, or contributed by another trusted integration. The execution boundary should remain consistent regardless of origin.

### MCP Connections

Model Context Protocol should be treated as the standard external capability connection shape.

JARVISv7 acts as the host and controls:

- server discovery and connection lifecycle
- capability negotiation
- resource exposure
- prompt availability
- tool authorization
- user consent
- isolation between servers
- logging, errors, cancellation, and disconnection

MCP primitives retain distinct meaning:

- resources provide application-managed context
- prompts provide user-selectable templates or workflows
- tools provide model-discoverable executable actions

An MCP server is an integration boundary, not an agent and not a blanket trust grant.

### Hooks

Hooks are deterministic lifecycle actions triggered by explicit events such as startup, before or after tool execution, after file changes, before completion, or during shutdown.

Hooks are appropriate for validation, formatting, policy checks, logging, or cleanup that must occur regardless of model choice. They must be visible, bounded, and governed because they may execute local commands.

### Agents

An agent is a role-scoped reasoning and delegation unit, not simply a prompt or tool collection.

A reusable agent shape should define:

- identity and purpose
- instructions
- allowed models or runtime posture
- available tools, skills, MCP connections, and resources
- memory scope
- permission and approval boundaries
- invocation mode: user-selected, delegated, or disabled
- handoff and completion contract
- output contract and trace requirements

Agents compose the stable turn, memory, policy, runtime, and capability foundations. They do not replace those foundations.

Non-agent conversation must continue to work unchanged. Agent behavior remains explicit, opt-in, policy-gated, and traceable.

### Plugins

Plugins are installable packages that bundle one or more extension shapes, such as:

- skills
- agents
- reusable prompts or commands
- hooks
- MCP server definitions
- supporting scripts or resources

A plugin manifest should identify publisher, version, contents, compatibility, requested permissions, and trust status.

Installation does not imply activation or approval. Plugin contents must be inspectable before execution, individually enableable where practical, and removable without damaging the core assistant.

### Resources and Connectors

Resources expose contextual data without automatically granting action authority. Connectors establish authenticated access to external services, accounts, repositories, calendars, messages, databases, or devices.

Connectors should declare accessible resources and tools separately so read access, write access, and automation can be governed independently.

### Models and Providers

Model and provider settings should describe selectable reasoning capability, not own product orchestration.

The shape should accommodate:

- local model catalogs and tiers
- runtime and device compatibility
- context and modality support
- generation defaults
- readiness and validation state
- explicit remote providers if later implemented

A provider must not appear selectable until its execution path works and its data-handling policy is clear.

### Marketplace and Distribution

Discovery may include local catalogs, organization catalogs, trusted registries, and public ecosystems.

Distribution must preserve:

- provenance
- versioning
- review status
- compatibility
- permissions
- update policy
- rollback and removal

Popularity is discovery evidence, not trust evidence.

---

## Composition Model

The extension shapes combine in a deliberate order:

1. settings select preferences and enabled capabilities
2. instructions constrain persistent behavior
3. prompts initiate repeatable user-directed workflows
4. skills provide procedural knowledge
5. resources provide contextual data
6. tools provide executable actions
7. MCP connects external resources, prompts, and tools
8. hooks enforce deterministic lifecycle behavior
9. agents compose selected instructions, skills, memory, and capabilities for specialized work
10. plugins package and distribute compatible combinations of these parts

No layer should silently inherit authority from a higher layer. An agent cannot bypass tool permissions; a skill cannot bypass policy; a plugin cannot bypass installation review; an MCP server cannot access unrelated context by default.

---

## Interruption and Recovery Shape

Interruption is a first-class interaction behavior.

When interruption is accepted:

- active speech stops at the nearest safe boundary
- the event is recorded
- the current turn remains reconstructable
- enough session context is preserved for coherent continuation
- the system transitions to an explicit next state

Unsupported overlap or barge-in behavior must degrade to a defined stop-and-reinvoke path rather than corrupting the session.

---

## Acceptance Model

### Foundation Acceptance

The foundation is accepted only when the real product path can:

1. profile the host
2. provision and verify the runtime stack
3. expose truthful readiness and degradation
4. start a session
5. accept voice or text input
6. assemble explicit personality and memory context
7. invoke the selected local model path
8. produce and optionally speak a response
9. handle interruption and failure cleanly
10. persist reconstructable artifacts

### Extension Acceptance

An extension shape is accepted only when it can be:

- discovered
- inspected
- enabled or disabled
- authorized
- invoked through a stable contract
- observed while running
- failed or cancelled safely
- removed without destabilizing the foundation

### Validation Hierarchy

1. live behavior on every targeted host and product surface
2. capability and readiness correctness
3. policy and permission correctness
4. targeted functional tests
5. integration and regression tests
6. logs, traces, and artifacts
7. documentation

---

## Implementation Philosophy

JARVISv7 should be built through thin vertical slices that preserve the primary interaction path.

Build order should follow dependency truth:

- establish host capability, provisioning, and readiness
- prove local runtimes and acceleration paths
- prove the canonical conversational loop
- establish session, memory, personality, artifacts, and recovery
- preserve the desktop as a thin durable shell
- add extension shapes one at a time through stable boundaries
- add agent composition only after skills, tools, permissions, memory scopes, and execution evidence are trustworthy

Avoid parallel frameworks that duplicate conversation, memory, tool, or runtime authority.

---

## User Experience Goals

JARVISv7 should feel:

- immediate
- dependable
- local
- private
- responsive
- understandable
- interruptible
- personal
- extensible without becoming unpredictable

The user should be able to understand:

- what runtime and hardware profile is active
- what the assistant heard
- what state the assistant is in
- what memory is being used or written
- what tools, skills, agents, plugins, or MCP servers are active
- what action is being proposed or executed
- what permission or confirmation is required
- whether the system is degraded or failed

---

## Governance Alignment

Repository documents have separate purposes:

- `ProjectVision.md` defines the intended product shape and core invariants
- `SYSTEM_INVENTORY.md` records capabilities observable in the current repository
- `CHANGE_LOG.md` records surviving implemented change history with evidence
- `repo_tree.md` answers where repository content belongs

Vision guides implementation but does not override runtime truth. Inventory and change history must not claim planned or removed capability.

---

## Definition of Success

JARVISv7 succeeds when it behaves as a real local assistant with a stable, inspectable foundation and reusable extension model.

The foundation succeeds when:

- hardware truth drives provisioning and runtime selection
- local voice and reasoning work through one canonical interaction path
- personality, memory, policy, and context are explicit
- interruption and degraded behavior are reliable
- the desktop is a durable adapter over backend capability
- important actions and failures are reconstructable
- supported x64 and ARM64 paths are validated honestly

The broader vision succeeds when the same foundation can safely host:

- layered settings and instructions
- reusable prompts and portable skills
- governed tools and external resources
- MCP integrations
- deterministic hooks
- inspectable plugins
- specialized, opt-in agents
- desktop and CLI interaction surfaces

That is the shape of JARVISv7: one stable local assistant foundation, extended through explicit reusable capability forms rather than disconnected features.
