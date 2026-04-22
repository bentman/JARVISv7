
# JARVISv7 ProjectVision

## Vision

JARVISv7 is a local-first, voice-first personal assistant designed for real conversational interaction on user-owned hardware. It is not a chatbot with voice added later. It is a real-time conversation engine with text as a fallback surface.

The target experience is closer to J.A.R.V.I.S. than a browser chat app:
- the user can speak naturally
- the system listens, transcribes, reasons, responds, and speaks back
- the user can interrupt
- the system preserves turn continuity
- the assistant has a defined personality
- failures are explicit and degrade cleanly instead of silently collapsing

JARVISv7 must be useful on day one in a minimal conversational loop, then expand toward richer memory, tool use, interruption handling, assistant presence, personality depth, and autonomous agent behavior.

---

## Product Identity

JARVISv7 is:

- voice-first
- desktop-first
- hardware-aware from process start
- cross-platform by design (x64 and ARM64 from the beginning)
- local-first by default
- deterministic in orchestration
- explicit in memory and cognition
- interruptible
- personality-driven
- agent-capable when the foundation is stable
- text-capable, but not text-centered

JARVISv7 is not:

- a text chat system with optional voice buttons
- a detached voice panel experiment
- a cloud-first assistant that happens to run locally
- a collection of disconnected AI features without a primary interaction model
- a personality-less command shell with speech bolted on
- a system that works on one hardware class and retrofits others later

---

## Primary Goal

Build a usable voice-first assistant whose core interaction loop works end-to-end in the real runtime across supported hardware:

1. system profiles hardware at startup
2. system provisions and verifies the correct runtime stack for the detected hardware
3. system emits a capability profile used by all downstream subsystems
4. user invokes the assistant
5. assistant captures audio
6. assistant transcribes locally by default
7. assistant routes the turn through the same cognition and execution engine used by all modalities
8. assistant returns a response aligned to the configured personality
9. assistant speaks back locally when TTS is available
10. user can interrupt and continue naturally
11. all failure modes are visible and recoverable

This loop is the root acceptance path for the system.

If this path does not work in the active runtime on any supported host class, the system is not considered complete regardless of subsystem tests.

---

## Foundational Principle

### Hardware Profiling and Provisioning Come First

The first callable system capability in JARVISv7 is the hardware profiler.

Before UI, before voice capture, before model selection, before orchestration, the system must detect the execution environment and emit a capability flags object.

The second system capability is provisioning. The correct set of packages for the detected hardware must be resolved and installed through a single declarative authority. The profiler determines what gets installed. No developer edits a monolithic requirements file by hand. No voice-family package enters the base install. Hardware-specific packages enter through the profiler-driven provisioning layer.

The third system capability is readiness. Correct packages installed does not imply usable inference. DLLs must load, execution providers must register, model artifacts must be discoverable. Every runtime-selection decision downstream consumes evidence-backed readiness claims.

Hardware-authority rule: hardware-dependent runtime selection starts in the profiler. Config files define catalog and default metadata. Runtime modules execute the selected runtime, model, and device; they do not invent hardware policy locally.

This profile and readiness chain is the root input for:
- model selection
- STT runtime and device selection
- TTS runtime and device selection
- LLM backend selection
- wake word runtime selection
- quantization strategy
- concurrency limits
- degraded-mode policy
- wake-word support
- desktop vs laptop behavior
- power-aware behavior
- personality and runtime presentation constraints where needed

JARVISv7 should not guess what it can do.
It should know.

---

## Core Principles

### 1. Voice Is the Root Mode

Voice is not a late-stage feature.
Voice defines the primary system architecture.

Text input is a fallback and debug path into the same turn engine.

### 2. Hardware-Aware Execution Starts at Boot

JARVISv7 must begin with a hardware profiling pass that detects:
- OS
- CPU and architecture (x64 / ARM64)
- GPU presence and vendor
- CUDA availability
- NPU availability and vendor
- total and available memory
- desktop vs laptop profile where practical

This detection must emit a callable profile object and capability flags object that downstream systems consume directly.

### 3. Cross-Platform from Day One

JARVISv7 must support multiple hardware classes from the start, not retrofit them later. The provisioning model, runtime families, and test harness must all accommodate at minimum Windows x64 and Windows ARM64 before the first voice runtime is written.

Each voice-family runtime (STT, TTS, LLM, Wake) accepts device as a parameter. One runtime family per voice subsystem, with device selection driven by readiness evidence. New hardware acceleration is a device branch inside an existing runtime, not a new runtime family.

### 4. Local-First by Default

JARVISv7 should prefer local execution for:
- STT
- TTS
- reasoning where hardware allows
- memory
- orchestration
- artifacts and trace storage
- wake word detection

Remote providers may be used only through explicit policy and only when local capability is unavailable or intentionally overridden.

### 5. Deterministic Orchestration

LLMs provide reasoning, not control.

Control flow must be explicit and deterministic through a defined conversation and execution state machine.
No hidden assistant behavior should exist only inside a prompt.

### 6. Externalized Cognition

Memory, plans, artifacts, context, and tool traces must live outside the model.
The model is stateless between calls unless context is explicitly supplied.

### 7. Personality Is a Core System Dimension

Personality is not cosmetic.
It is part of the assistant contract.

JARVISv7 must define personality explicitly so that:
- wording style is intentional
- spoken response style is intentional
- pacing and brevity can be tuned
- persona does not drift unpredictably
- tone survives across turns and modalities
- personality settings remain compatible with deterministic orchestration and explicit policies

Personality must be externally configured and inspectable, not left as vague prompt residue.

### 8. Clear Failure States

JARVISv7 must never silently fail with empty output or unexplained states.

Every major subsystem must fail closed and visibly:
- profiler unavailable
- provisioning failed
- readiness unverified
- STT unavailable
- TTS unavailable
- model missing
- provider import failure
- wake-word unavailable
- interrupted response
- execution failure

### 9. Live Runtime Validation Over Narrow Success

A feature is only complete if it works in the actual runtime used by the product on every host class the feature targets.
Passing builds and narrow tests are necessary but not sufficient.

### 10. Agent-Capable Architecture

JARVISv7 should be designed so that role-separated agents can layer on top of the core turn engine when that foundation is stable.

Agents consume the turn engine, tool registry, memory, and LLM runtime — they do not replace them.
Agent behavior is opt-in through explicit policy.
Non-agent turns continue to work unchanged.

This is not a requirement for the initial conversational loop; it is a structural commitment that prevents the architecture from closing off this capability.

---

## Product Outcome

JARVISv7 should feel like a persistent local assistant, not like a web app with AI features.

The user experience target is:
- low-friction invocation
- natural spoken interaction
- immediate system feedback
- visible state transitions
- smooth degradation when a modality is unavailable
- continuity across turns
- recognizable assistant personality
- tool-grounded answers when the assistant needs to act in the world

The user should understand at all times whether JARVISv7 is:
- profiling
- idle
- listening
- transcribing
- thinking
- speaking
- interrupted
- degraded
- failed

---

## First System Capabilities

### Hardware Profiler

The hardware profiler is the first required implementation.

**Purpose:** Detect host capabilities and return a normalized profile object that the rest of the system can call.

**Required Detection Targets:**
- operating system
- architecture (x64 / ARM64)
- CPU model and capabilities
- GPU presence and vendor (NVIDIA, AMD, Intel, Qualcomm, other)
- CUDA availability and version band
- NPU presence and vendor (Qualcomm, Intel, AMD, other)
- total and usable memory
- storage constraints where practical
- desktop vs laptop classification where practical

**Required Output:** A normalized capability object and flags, conceptually:
- `os`, `arch`, `cpu`, `gpu`, `gpu_vendor`, `cuda_available`, `npu_available`, `npu_vendor`, `memory_gb`, `device_class`
- `supports_local_llm`, `supports_gpu_llm`, `supports_cuda_llm`, `supports_local_stt`, `supports_local_tts`, `supports_wake_word`, `supports_realtime_voice`, `supports_desktop_shell`, `requires_degraded_mode`, `qnn_available`, `directml_candidate`

The exact schema can evolve, but the principle cannot:
every major subsystem should consume a shared capability profile rather than inventing its own environment checks.

### Provisioning

The provisioning model is the second required implementation.

**Purpose:** Translate profiler output into the correct set of installed packages for the detected hardware, through one declarative authority.

The provisioning authority lives in the project's standard package metadata. Hardware-family packages are declared as optional extras gated by architecture and vendor. The profiler-driven resolver is the only place that translates hardware facts to package sets. Operators never edit a monolithic requirements file by hand.

Adding a new hardware family should require one new extra declaration and one new resolver branch — nothing else changes.

### Readiness

The readiness rail is the third required implementation.

**Purpose:** Verify that installed packages, DLLs, execution providers, and model artifacts are actually usable before runtime selectors act.

The readiness rail emits evidence-backed claims per voice family (STT, TTS, LLM, Wake) and per device (CPU, CUDA, DirectML, QNN). These claims carry the reasoning behind each selection so failures are traceable without re-running probes.

**Non-Goals of the First Three Capabilities:**
They do not:
- present UI
- load models for inference
- invoke voice runtimes
- choose final personality
- execute assistant turns

They detect, provision, and verify.
That is their contract.

---

## Voice Runtime Strategy

### One Family Per Subsystem, Device as Parameter

JARVISv7 should use one primary runtime family per voice subsystem across all supported hardware. Device (CPU, CUDA, DirectML, QNN) is a parameter of the runtime, not a reason to switch runtime families.

- **STT:** ONNX-based Whisper via `onnxruntime` as the primary cross-platform path. A secondary `onnx-asr` path for alternative model families (Parakeet, Canary, NeMo) when needed.
- **TTS:** Kokoro via `kokoro-onnx` as the primary cross-platform path.
- **LLM:** Local `llama.cpp` as the preferred local runtime, Ollama as tested fallback, cloud providers as explicit policy-gated escalation.
- **Wake:** openWakeWord as the primary runtime (pre-trained "hey jarvis" model, architecture-independent). Porcupine as an optional alternative.

This strategy should be decided before the first voice turn is implemented, and acceleration targets (CUDA, DirectML, QNN) should be exercised — at least at the readiness and probe level — before any turn-engine work begins.

### Acceleration Is Not a Retrofit

GPU, CUDA, NPU, and QNN acceleration must be defined as device slots from day one. The architecture must accommodate them structurally — in manifests, readiness tokens, capability flags, and runtime device enumerations — even when their inference code is activated later.

This prevents the "acceleration as retrofit" pattern where adding hardware support after the fact forces corrections across multiple layers simultaneously.

---

## Personality System

Personality must be a first-class subsystem in JARVIS.

### Purpose

Define how JARVISv7 behaves, not just what it says.

### Personality Scope

Personality should influence:
- tone
- brevity
- assertiveness
- warmth
- humor policy
- formality
- spoken cadence targets
- interruption handling style
- acknowledgment style
- confirmation style
- assistant identity consistency

### Personality Constraints

Personality must not:
- override safety or policy rules
- invent facts
- bypass deterministic orchestration
- produce inconsistent behavior between text and voice
- live only as an opaque system prompt fragment

### Personality Representation

Personality should be externalized and configurable through structured settings, profiles, or policy artifacts.

A minimal conceptual personality profile should look like:
- `profile_id`, `display_name`, `identity_summary`
- `tone`, `brevity`, `formality`, `warmth`, `assertiveness`, `humor_policy`
- `response_style`, `acknowledgment_style`, `interruption_style`
- `voice_pacing`, `voice_energy`
- `safety_overrides`, `enabled`

The exact schema can evolve, but the principle cannot:
personality must be structured enough to persist, compare, validate, and apply consistently across text and voice paths.

### Personality and Voice

Voice output should reflect the same personality profile as text output where possible.

If the chosen TTS runtime supports voice variation, it should map to the configured personality.
If TTS does not support it, the text response style should still remain personality-consistent.

---

## Session Model

A session is the bounded conversational context within which turns are grouped for continuity, memory policy, and interruption recovery.

A session begins when JARVISv7 transitions from `IDLE` into an invocation-handling path for a user interaction.
A session may contain one or more turns.
A session remains active while the assistant is still handling follow-up interaction under continuity policy.
A session ends when the system returns to a clean idle baseline and continuity policy decides no active interaction context remains.

A session is not equivalent to a single HTTP request, a single utterance, or a single UI screen.
It is the interaction container used to group related turns and their artifacts.

---

## Core Interaction Model

JARVISv7 is built around a canonical turn lifecycle.

### Canonical Turn States

- `BOOTSTRAP`
- `PROFILING`
- `IDLE`
- `LISTENING`
- `TRANSCRIBING`
- `REASONING`
- `ACTING`
- `RESPONDING`
- `SPEAKING`
- `INTERRUPTED`
- `RECOVERING`
- `FAILED`

Text and voice both enter this same turn lifecycle.

### Canonical Turn Flow

#### Startup
1. system starts
2. hardware profiler runs
3. provisioning verifies or corrects the installed package set
4. readiness rail verifies DLLs, execution providers, and model artifacts
5. capability flags are emitted
6. runtime profile is selected
7. personality profile is loaded
8. system enters `IDLE`

#### Voice Turn
1. user invokes assistant (wake word or push-to-talk)
2. assistant enters `LISTENING`
3. audio is captured
4. assistant enters `TRANSCRIBING`
5. transcript is produced
6. transcript enters normal cognition/execution path
7. assistant enters `REASONING` / `ACTING`
8. response text is produced in alignment with personality profile
9. assistant enters `RESPONDING`
10. if TTS available, assistant enters `SPEAKING`
11. user may interrupt at any point allowed by policy
12. turn ends in `IDLE`, `RECOVERING`, or `FAILED`

#### Text Turn
1. user submits typed text
2. system bypasses listen/transcribe stages
3. text enters the same cognition/execution path
4. response follows the same response lifecycle and personality rules

Text is therefore a secondary ingress path, not a separate product architecture.

---

## Interruption Policy

Interruption is a first-class system behavior, not a UI afterthought.

### Policy Model

1. **Speech output is interruptible.** If the assistant is in `SPEAKING`, a valid barge-in signal should stop speech output immediately or at the nearest safe boundary supported by the runtime.

2. **Listening has priority over continued speaking when barge-in is accepted.** Once interruption is accepted, the system transitions out of `SPEAKING` and into the next valid capture state according to policy.

3. **The interrupted response must remain traceable.** The turn artifact must record that the response was interrupted, including timing and recovery state.

4. **State preservation is explicit.** The assistant must preserve enough turn/session context to continue coherently after interruption.

5. **Unsafe or unsupported interruption modes degrade cleanly.** If true barge-in is not supported by the current runtime, the system must expose that limitation and fall back to a defined stop-and-reinvoke behavior.

### Initial Implementation Rule

The first acceptable interruption behavior is:
- user interrupts while JARVISv7 is speaking
- speech output stops
- system records the interruption
- system transitions cleanly to the next allowed state without corrupting the session

Perfect conversational overlap is not required initially.
Deterministic interruption behavior is required.

---

## Canonical Turn Artifact

Every turn should produce an explicit artifact, whether voice or text.

A turn artifact should capture at minimum:
- turn id
- session id
- input modality
- hardware profile id or snapshot
- capability flags used for the turn
- active personality profile
- raw audio references, if any
- transcript
- final prompt text used for cognition
- retrieved memory/context references
- tools invoked
- agent trace, if agent orchestration was active
- reasoning/execution trace metadata
- response text
- audio output references, if any
- interruption events
- final state
- explicit failure reason, if any
- timestamps for each major phase

This artifact is the authoritative record of what happened.
Its schema should be fixed early and treated as a compatibility boundary.

---

## Architecture Overview

JARVISv7 should be organized into the following major layers.

### 1. Hardware Intelligence Layer

Responsible for:
- detecting available hardware across architecture classes
- provisioning the correct package set through a single declarative authority
- verifying readiness with evidence-backed claims
- classifying execution environment
- selecting runtime profiles
- emitting capability flags
- exposing a callable hardware profile object to the rest of the system

This layer decides what is realistically available before the assistant attempts work.

Examples:
- CPU-only fallback on any architecture
- GPU-accelerated local inference via CUDA on NVIDIA
- DirectML acceleration on AMD or Intel GPU
- QNN NPU acceleration on Qualcomm ARM64
- degraded voice mode when TTS is unavailable
- text fallback when STT is unavailable

### 2. Personality Layer

Responsible for:
- loading personality definitions
- applying personality policy to responses
- maintaining consistent style across text and voice
- exposing structured personality controls to the conversation engine
- keeping persona explicit and inspectable

This layer shapes assistant identity without owning orchestration.

### 3. Voice Runtime Layer

Responsible for:
- microphone access orchestration
- audio capture lifecycle
- wake word integration
- STT session execution (device-parameterized)
- TTS session execution (device-parameterized)
- interruption and barge-in handling
- audio device management

This layer owns real-time voice execution, not the chat UI.

Each voice-family runtime accepts device as a parameter and delegates device selection to the hardware intelligence layer.

### 4. Conversation Engine

Responsible for:
- turn lifecycle orchestration
- explicit state transitions
- routing between listen, transcribe, reason, act, respond, speak
- interruption recovery
- session continuity

This is the core runtime of JARVIS.

### 5. Cognition Engine

Responsible for:
- prompt assembly (with personality, memory, and retrieval inputs)
- planning
- tool-use decisions
- execution governance
- memory retrieval and writeback
- policy enforcement

The cognition engine must consume personality explicitly, not implicitly.
That means:
- the active personality profile is an input to prompt assembly
- personality rules are applied equally for voice and text turns
- personality never bypasses tool policy, memory policy, or safety policy
- personality must be traceable as part of the turn artifact context

This layer follows explicit cognition principles:
- models are stateless workers
- memory is externalized
- plans and outcomes are explicit
- reasoning is constrained by deterministic orchestration

### 6. Agent Layer

Responsible for:
- role-separated task decomposition, execution, and validation
- typed, non-conversational inter-agent messaging
- persisted coordination via an agent ledger
- training-data curation from successful execution traces
- training-cycle orchestration with regression-gated deployment

The agent layer is an optional orchestration surface that composes the conversation engine, tool registry, memory, and LLM runtime.
It does not replace the turn engine.
Turns that do not opt into agent orchestration continue to work exactly as they did before the agent layer existed.

Agent behavior is policy-gated, explicit, and traceable in turn artifacts.

### 7. Memory System

Responsible for:
- working memory (in-session, bounded)
- episodic memory (cross-session, policy-governed)
- semantic memory (future)
- task and conversation history
- retrieval and summarization
- explicit write policies

Memory exists to support continuity and assistant usefulness, not as a hidden side effect.
Durable memory authority lives in persisted artifacts, not infrastructure.
Infrastructure (Redis) is used for retrieval-cache acceleration only.

### 8. Desktop Shell

Responsible for:
- user-facing interface
- tray and overlay modes
- hotkeys / push-to-talk
- conversation display
- assistant status display (including hardware and LLM selection visibility)
- configuration and diagnostics
- wake word invocation integration

The desktop shell is the home of the assistant, but not the source of orchestration logic.
The shell is a thin adapter over the backend API contract.

### 9. Text Surface

Responsible for:
- typed fallback interaction
- debugging
- explicit task entry when voice is not appropriate
- visibility into cognition/tool results when needed

This must reuse the same conversation engine rather than inventing a separate chat architecture.

---

## Voice-First Functional Requirements

### Must Have

- callable hardware profiler that returns a normalized capability profile
- profiler-driven provisioning that resolves the correct packages per host class
- evidence-backed readiness rail per voice family and device
- cross-platform support (x64 and ARM64) from the first voice runtime
- local-first STT path with device as parameter
- local-first TTS path with device as parameter
- push-to-talk or equivalent explicit invocation path
- wake word detection as a default invocation path
- assistant response through the canonical turn engine
- deterministic state transitions
- explicit error states
- typed fallback
- hardware-aware runtime selection
- personality profile loading and application
- traceable turn artifacts with fixed schema
- fail-closed behavior for missing runtime/model/provider
- clear interruption path for assistant speech
- no silent blank responses
- arch-aware test harness with marker-based device gating

### Should Have

- streaming partial transcription
- streaming partial assistant response
- low-latency response start
- visible degraded-mode indicators
- profile-aware runtime selection
- selectable personality profiles
- selectable voices
- session continuity across interruptions
- tool-grounded responses
- cross-session episodic recall
- agent-capable orchestration (opt-in)

### Could Have

- ambient listening mode
- multi-device orchestration
- proactive notifications
- emotional or expressive speech controls
- richer avatar or desktop presence
- multimodal visual awareness
- local LLM via llama.cpp
- QNN NPU acceleration for STT
- DirectML acceleration for STT/TTS
- custom wake word training ("jarvis" without "hey" prefix)

### Must Not

- depend on cloud-only operation by default
- hide failures behind null/empty payloads
- let voice logic break primary typed interaction
- let UI experiments define backend architecture
- merge unproven subsystem work as "complete" without live-path validation
- work on one hardware class and treat other classes as a later retrofit
- let the proving host become the shipping surface

---

## Runtime Strategy

### Local-First Execution Order

The preferred execution order is:
1. local runtime
2. local fallback runtime
3. explicitly approved remote provider

This applies independently to:
- STT
- TTS
- LLM reasoning
- embeddings and memory support services
- search escalation providers

### Runtime Selection Inputs

Runtime selection must be driven by:
- hardware profile
- capability flags
- readiness evidence
- policy
- user preferences
- personality/runtime compatibility where applicable

### Hardware Profiles

JARVISv7 should support profile-driven execution such as:
- desktop x86_64 with NVIDIA GPU and CUDA
- desktop x86_64 CPU-only
- laptop x86_64 with integrated GPU (DirectML candidate)
- laptop ARM64 with Qualcomm NPU (QNN candidate)
- ARM64 CPU-only fallback
- constrained fallback profile

Each profile should influence:
- model family
- quantization
- max concurrency
- response strategy
- voice latency expectations
- degraded-mode policy

### Degraded Modes

Examples:
- STT available, TTS unavailable → text reply + explicit silent-response mode
- TTS available, STT unavailable → typed input + spoken output
- local LLM unavailable → explicit provider fallback if allowed
- wake unavailable → push-to-talk only
- microphone unavailable → text-only fallback
- GPU unavailable → CPU profile with explicit performance downgrade
- QNN readiness unverified → CPU-EP fallback on same host

Degraded mode is acceptable.
Silent confusion is not.

---

## Explicit Cognition Framework Alignment

JARVISv7 should continue and strengthen the Explicit Cognition Framework.

### ECF Rules

- no hidden long-term assistant state inside the model
- no implicit memory writes without policy
- tool actions must be explicit and logged
- plans and execution phases must be inspectable
- all important state transitions must be reconstructable from artifacts
- cognition must remain separable from presentation and transport
- personality must be explicit and externally represented
- hardware capability assumptions must be derived from the profiler, not hidden inside provider code
- agent behavior must be opt-in, policy-gated, and traceable

### Why ECF Matters for Voice

Voice interaction increases ambiguity, latency sensitivity, interruption complexity, and persona sensitivity.
Without explicit cognition, explicit hardware awareness, and explicit turn artifacts, debugging spoken interaction becomes nearly impossible.

ECF is therefore more important in a voice-first system than in a text-centered one.

---

## Acceptance Model

JARVISv7 should be accepted based on primary-path behavior in the real runtime on every supported host class.

### Minimum Real Acceptance Path

A minimal acceptable voice loop is:

1. system profiles the host and emits capability flags
2. provisioning verifies the correct packages are installed for the detected hardware
3. readiness verifies DLLs, execution providers, and model artifacts
4. the selected runtime profile is explicit
5. the personality profile is explicit
6. user invokes assistant
7. assistant enters listening state visibly
8. user speaks a simple request
9. assistant transcribes successfully
10. assistant routes the transcript through the normal cognition/execution path
11. assistant returns a valid response aligned to personality
12. if TTS runtime is available, assistant speaks it
13. if user interrupts during speech, assistant stops and transitions cleanly
14. final state is explicit and recorded

If this path does not work in the active runtime on any supported host class, the slice is not complete.

### Validation Hierarchy

1. live runtime behavior on every target host class
2. capability profile correctness
3. readiness evidence correctness
4. targeted functional tests (arch-gated, device-gated)
5. build/test harness results
6. logs and traces
7. documentation updates

This order is intentional.

---

## Implementation Philosophy

JARVISv7 should be built through thin vertical slices, not isolated subsystem milestones.

The wrong approach is:
- build a route
- then build a recorder
- then build a panel
- then wire them later

The correct approach is:
- build the profiler and provisioning first
- prove provisioning is correct on every host class
- prove the voice runtime strategy and acceleration surface
- prove the smallest real conversational loop
- build the durable desktop shell once
- preserve the primary path at every step
- expand capability only after the real loop works

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

The user should never have to guess:
- what hardware/runtime profile was selected
- whether the assistant heard them
- whether the assistant is still thinking
- whether the assistant is speaking
- whether the system failed
- whether the system is degraded
- which LLM runtime is active

---

## Goals for Initial JARVIS

Initial JARVISv7 needs:
- one honest hardware profiler
- one honest provisioning model that works across host classes
- one honest readiness rail with evidence-backed claims
- one honest and working conversational loop
- correct runtime selection driven by readiness
- explicit personality handling
- deterministic control
- visible failures
- clean fallback behavior
- a durable desktop shell, not a proving host promoted to shipping surface

---

## Repository and Governance Alignment

JARVISv7 must remain aligned with repo governance.

This means:
- evidence-first changes
- minimal diffs
- no claiming completion without reproducible proof on every target host class
- approval-gated implementation
- no roadmap drift from runtime reality
- no "complete" status unless the primary path works in the real runtime

In repo terms:
- `ProjectVision.md` defines the target state and core invariants
- `SYSTEM_INVENTORY.md` defines what capabilities are actually observable now
- `CHANGE_LOG.md` defines what has actually been completed with evidence
- `slices.md` defines the planned sequencing
- `repo_tree.md` defines the structural boundaries that prevent drift

These must not be conflated.

---

## Definition of Success

JARVISv7 is successful when it behaves like a real local assistant rather than a text system with voice attachments.

The earliest meaningful success state is:

- the system profiles the hardware first
- the system provisions the correct packages for the detected hardware through one authority
- the system verifies readiness with evidence before selecting runtimes
- the system emits capability flags that drive runtime choices
- the assistant personality is explicit and consistent
- the user can invoke JARVISv7 with voice (wake word or push-to-talk)
- JARVISv7 can listen and transcribe locally on any supported host class
- the transcript enters the same core cognition path as typed input
- JARVISv7 produces a response in the real runtime
- JARVISv7 speaks when TTS is available
- JARVISv7 fails clearly when a modality is unavailable
- JARVISv7 can be interrupted without collapsing the session
- the desktop shell is the durable surface, not a promoted script
- all of the above are traceable through explicit artifacts and deterministic state transitions
- all of the above work on both x64 and ARM64 hosts

That is the foundation.
Everything else builds on top of it.

---
