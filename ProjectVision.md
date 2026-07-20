# JARVISv7 ProjectVision

## Vision

JARVISv7 is a local-first, voice-first personal assistant designed for real conversational interaction on user-owned hardware.

It should feel less like a chat window and more like a capable presence: available, interruptible, aware of its limits, consistent in personality, and able to grow without losing the integrity of its original interaction model.

The user should be able to speak naturally. JARVIS should listen, understand, respond, speak back, recover when interrupted, remember what it is allowed to remember, and clearly explain when something is unavailable or has failed.

Text remains important, but it is not a separate product. It is another doorway into the same assistant.

The long-term vision is not a pile of AI features. It is a coherent assistant whose capabilities emerge in the right order, each resting on foundations that are already trustworthy.

---

## The Shape of JARVIS

JARVIS is:

- voice-first
- desktop-first, while remaining compatible with useful CLI surfaces
- local-first by default
- hardware-aware from the moment it starts
- cross-platform by design
- deterministic in orchestration
- explicit in memory, policy, and action
- interruptible
- personality-driven
- extensible through reusable capability shapes
- agent-capable only after the underlying assistant is dependable

JARVIS is not:

- a text chatbot with speech controls attached
- a cloud service disguised as a local assistant
- a collection of unrelated integrations
- a prompt-driven command shell with hidden state
- a system that confuses skills, tools, plugins, MCP servers, and agents
- a system that advertises capability before it can prove capability

---

## The First Promise: Know the Machine

Before JARVIS can listen, reason, remember, or act, it must know where it is running and what that machine can honestly support.

The assistant begins by understanding the host: its operating system, architecture, compute devices, memory limits, available acceleration, installed runtimes, model artifacts, and service readiness.

That knowledge must not be guessed independently by every subsystem. It becomes shared truth.

From that truth, JARVIS can determine what should be installed, what can be loaded, what can run locally, what must degrade, and what should remain unavailable.

This is the first stable foundation because every later promise depends on it.

A system that does not know what it can do cannot be trusted when it says it is ready.

---

## The Second Promise: One Honest Interaction Loop

Once the machine is understood, JARVIS must prove one complete interaction loop.

The user invokes the assistant. JARVIS listens. Speech becomes text. The request enters a single cognition path. A response is formed in the active personality. Speech is produced when available. The user may interrupt. The system returns to a clear, recoverable state.

Voice and text must share this same underlying path. They may enter at different points, but they must not become separate products with different rules, memory, or behavior.

The interaction must remain explicit enough that the system can always answer:

- what state it is in
- what it heard
- what context it used
- what it attempted
- what failed
- what it retained
- what happens next

This loop is the heart of JARVIS. Everything else must strengthen it rather than route around it.

---

## The Third Promise: A Mind with Boundaries

JARVIS should reason, but reasoning must not become invisible control.

Models interpret, synthesize, and propose. The application owns state, permissions, retries, interruption, approvals, actions, handoffs, and failure recovery.

The model remains a worker inside a larger system. It does not become the system.

Personality, instructions, memory, available capabilities, policies, plans, results, and artifacts remain outside the model so they can be inspected, changed, compared, and governed.

This gives JARVIS a mind that can be expressive without becoming opaque.

---

## The Fourth Promise: Memory with Meaning

JARVIS should remember, but not everything called memory serves the same purpose.

Memory should develop in layers, each introduced only after the layer beneath it is stable.

### The Present Moment

The current turn needs temporary context: the user request, active state, selected personality, relevant capability facts, retrieved information, and intermediate results.

This context exists to complete the turn. It should disappear unless deliberately promoted.

### The Active Conversation

A session needs bounded working memory so related turns can remain coherent.

This memory should preserve immediate continuity without becoming an ever-growing transcript. It may be summarized, replaced, or allowed to expire.

### The Event That Happened

Episodic memory preserves selected events across sessions: what occurred, when it occurred, and why it may matter later.

It should be written under explicit policy, retain provenance, and remain correctable.

### The Fact That Remains Useful

Semantic memory preserves durable facts and concepts independently of the exact conversation that produced them.

It must distinguish fact from inference, preserve source and confidence, tolerate correction, and avoid silently converting every statement into truth.

### The Way Work Is Done

Procedural memory captures reusable methods.

The preferred portable shape for this is the skill: a bounded body of instructions, optional scripts, examples, templates, and supporting resources that teaches the assistant how to perform a class of work.

Procedures should be reusable and inspectable rather than buried in old conversations.

### The User and Assistant Profile

Preferences, permissions, personality, voice choices, defaults, and interaction settings belong to explicit profile and configuration state.

They should be directly editable rather than inferred repeatedly from conversation.

### The Evidence of What Happened

Artifacts, traces, outputs, and audit records preserve enough evidence to reconstruct important actions and outcomes.

They are not automatically memory for future reasoning. They become context only through deliberate retrieval.

Across every layer, the rule is the same: retrieval does not imply permission to retain, and cache is not memory authority.

---

## The Fifth Promise: A Governed Ability to Act

JARVIS becomes more useful when it can act, but action must arrive only after interaction, state, memory, and policy are dependable.

A capability is not real merely because code exists for it. It becomes part of the assistant only when it can be discovered, authorized, invoked, observed, cancelled, failed safely, and explained afterward.

Tools are the basic action shape. A tool has a clear identity, a structured input, a meaningful result, known side effects, permission requirements, failure behavior, and an audit trail.

The origin of a tool may vary. It may be built in, supplied by a plugin, exposed through MCP, or provided by another trusted integration. Its execution contract should remain consistent.

JARVIS should distinguish reading from writing, reversible from destructive action, local from remote effect, and routine execution from operations that require confirmation.

The assistant should never acquire authority merely because a prompt asked for it.

---

## The Sixth Promise: Reusable Ways to Extend the Assistant

Once the foundation can reason, remember, and act safely, JARVIS can grow through familiar reusable shapes rather than inventing new categories for every feature.

### Settings and Configuration

Settings define preferences and operating choices at sensible scopes: product, user, host, workspace, session, and capability.

Detected facts should not be overridden as if they were preferences. Secrets should remain separate from shareable configuration.

### Instructions

Instructions define persistent behavioral constraints and conventions.

They may apply to the whole product, a user, a project, a domain, or an agent. They guide behavior but do not replace deterministic policy.

### Reusable Prompts

Prompts are discoverable, user-invoked templates for recurring requests and workflows.

They help the user begin a task consistently without pretending to be autonomous capability.

### Skills

Skills are portable procedural bundles, following established shapes such as the Agent Skills ecosystem and directories such as skills.sh.

A skill explains how to perform a bounded kind of work and may include scripts, examples, templates, or reference material. It may use tools, but it is not itself a tool.

Skills are the preferred way to carry reusable procedural knowledge across assistants, projects, and environments.

### MCP Connections

Model Context Protocol provides a standard shape for connecting external capability.

An MCP server may expose resources, prompts, and tools, but it does not receive blanket trust. JARVIS remains the host and controls discovery, connection lifecycle, consent, authorization, isolation, errors, and disconnection.

MCP is a connection boundary, not an agent.

### Hooks

Hooks are deterministic actions tied to known lifecycle events.

They are useful when something must happen regardless of model choice, such as validation, formatting, policy checks, logging, or cleanup.

Because hooks may execute local behavior, they must remain visible and governed.

### Plugins

Plugins are installable packages that may bundle several extension shapes: skills, prompts, tools, MCP definitions, agents, hooks, settings, and user interface contributions.

A plugin is packaging and lifecycle. It is not a synonym for every capability it contains.

### Connectors and Providers

Connectors represent authenticated relationships with external systems. Providers represent interchangeable sources of models or runtime services.

Both should expose clear readiness, health, credentials, permissions, and failure boundaries.

These shapes allow JARVIS to grow by composition rather than by accumulating special cases.

---

## The Seventh Promise: Agents Built on an Assistant, Not Instead of One

Agents should appear only after the assistant already has stable interaction, cognition, memory, tools, permissions, artifacts, and recovery.

An agent is a role-scoped reasoning and delegation unit with a defined purpose, available capabilities, memory scope, permission boundary, invocation mode, and completion contract.

Agents may be selected directly by the user or delegated by another trusted coordinator. They may use skills, tools, MCP connections, resources, and models. They must not bypass the same policy and evidence boundaries that govern ordinary turns.

An agent should not become a second application architecture.

It composes the assistant’s existing foundations:

- instructions provide role and constraints
- skills provide reusable procedure
- tools provide action
- MCP provides external capability
- memory provides continuity
- policy provides authority
- artifacts provide evidence
- hooks provide deterministic lifecycle behavior
- plugins provide distribution

Non-agent interaction must remain fully functional even if every agent feature is disabled.

---

## The Experience This Should Create

When these layers arrive in the right order, JARVIS should feel immediate, dependable, private, understandable, interruptible, and personal.

The user should not need to think about architecture. They should simply experience an assistant that:

- knows what the machine can support
- tells the truth about readiness and failure
- listens and responds through one coherent interaction model
- preserves continuity without becoming invasive
- remembers with purpose and consent
- acts only through visible authority
- gains new abilities through recognizable, reusable extensions
- delegates only when the underlying foundations are trustworthy
- remains understandable as it becomes more capable

The defining quality is not the number of features.

It is coherence.

---

## Growth Order

JARVIS should continue to evolve in this sequence:

1. truthful host knowledge and readiness
2. one complete voice-first interaction loop
3. explicit state, cognition, personality, and recovery
4. meaningful layers of memory
5. governed tools and external action
6. reusable skills, prompts, instructions, MCP connections, hooks, and plugins
7. policy-controlled agents and delegation
8. broader autonomy only after the earlier layers remain dependable under real use

Later layers may influence earlier ones, but they must not be allowed to weaken them.

---

## Evidence and Governance

Project vision defines the intended shape and the invariants that should survive implementation change.

The repository must keep separate records for separate purposes:

- `ProjectVision.md` defines direction and enduring shape
- `SYSTEM_INVENTORY.md` records capabilities observable in the current repository
- `CHANGE_LOG.md` records completed changes supported by evidence
- `repo_tree.md` guides where repository content belongs

Implementation is complete only when the intended outcome works in the real product path on the hardware classes it claims to support.

Documentation, tests, logs, and reports support that conclusion. They do not substitute for it.

---

## Definition of Success

JARVISv7 succeeds when it behaves like a real local assistant rather than a text system surrounded by AI features.

It understands the machine before it promises capability. It speaks and listens through one coherent loop. It reasons without owning hidden control. It remembers through explicit layers. It acts through governed capability. It grows through reusable extension shapes. It delegates only after the foundation is ready.

The assistant may become broad, but it should never become vague.

That is the foundation.
Everything else builds from it.
