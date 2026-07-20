# J.A.R.V.I.S v7

![Not Magic](https://img.shields.io/badge/Not-Magic-purple)
![Evidence Required](https://img.shields.io/badge/Evidence-Required-orange)
![Status: Building](https://img.shields.io/badge/Status-Building-green)
![License: MIT](https://img.shields.io/badge/License-MIT-blue)

* * *

## 📚 **J**udiciously **A**daptive **R**untime **V**oice **I**nterface **S**ystem — Mark7

JARVISv7 is a local-first, voice-first personal assistant project built for real conversational interaction on user-owned hardware. The target is not a browser chat box with a microphone button taped to it. The target is a desktop-resident assistant that can listen, reason, respond, speak, remember useful context, expose what it is doing, and fail in ways humans can actually diagnose.

It is still not sentient. It is still not flying the suit. It is still not allowed to call vibes a validation strategy.

JARVISv7 exists because v6 proved the vision was mostly right and the implementation was occasionally adventurous. v7 keeps the ambition, but adds hardware-aware startup, explicit readiness, visible degradation, evidence-backed validation, and fewer opportunities for architectural jazz hands.

> A project that has finally become disciplined enough to discover how much work remains.

* * *

![JARVISv7](docs/JARVISv7.png)

* * *

## 🚀 Quick Start

Fresh-clone setup lives in the platform quick-start guides below. They are the right place for commands, prerequisites, and the current repo-run desktop preview flow. The short version is: create `backend\.venv`, run `scripts\bootstrap.py`, install desktop dependencies, then launch the desktop shell with `npm --prefix desktop run dev`. The desktop starts the backend and displays readiness, services, resident voice, wake, session, and error state.

Useful entry points:

* [ProjectVision.md](ProjectVision.md) — where the project is going
* [SYSTEM_INVENTORY.md](SYSTEM_INVENTORY.md) — what is actually observable now
* [CHANGE_LOG.md](CHANGE_LOG.md) — completed work with evidence
* [AGENTS.md](AGENTS.md) — repository rules for assisted work
* [docs/QuickStart-windows.md](docs/QuickStart-windows.md) — Windows setup and repo-run desktop launch
* [docs/QuickStart-linux.md](docs/QuickStart-linux.md) — Linux and WSL setup; Linux AMD64 NVIDIA CUDA llama.cpp is verified in WSL2

The README is intentionally not the technical manual. Nobody wins when the front page becomes an installation crime scene.

> If you need commands, use the guide. If you need philosophy, continue scrolling at your own risk.

* * *

## 🧭 Project Vision

The destination has changed very little: JARVISv7 should behave like a persistent local assistant, not a text system pretending voice is a theme pack. The primary path is voice-first, desktop-first, local-first, hardware-aware, deterministic, and explicit about state. Text remains useful, but it is a secondary path into the same interaction model, not the product center of gravity.

The intended progression is simple, even when the engineering is not:

* know the machine before selecting capability
* establish one honest voice-and-text interaction loop
* preserve continuity without hiding state inside the model
* make memory useful without making it mysterious
* allow action only through explicit, governed capability
* add reusable skills, integrations, plugins, and agents only after the foundation can support them

That sounds less glamorous than “AI assistant,” but it is far more useful when something breaks at 11:47 PM and the system has the courtesy to say why.

> The goal is natural interaction without pretending the engineering underneath is simple.

* * *

## 🧱 What Exists Now

JARVISv7 now has substantially more than scaffolding. It has a hardware-aware backend, a desktop shell, local voice runtimes, a working conversation path, resident voice behavior, session continuity, structured personality, several distinct memory layers, and verified runtime evidence across multiple host and accelerator paths. It is still under construction, but increasingly the problems are specific instead of mystical.

Current working areas include:

* FastAPI backend with hardware profiling, provisioning, preflight, readiness, diagnostics, session, and status surfaces
* Tauri desktop shell with backend lifecycle, resident voice controls, readiness/status display, diagnostics, and local settings flow
* local STT, TTS, wake, and LLM runtime paths selected from readiness evidence
* resident shared-stream voice with push-to-talk, wake monitoring, bounded follow-up, and interruption handling
* canonical text and voice turns through the same conversation engine
* managed local `llama.cpp` with Ollama fallback
* disk-backed episodic memory, SQLite semantic memory, bounded working context, retrieval, and persisted turn/session artifacts
* structured personality profiles applied through explicit prompt and response boundaries
* disabled-by-default agent policy, spec catalog, local ledger, and read-only trace/status surfaces

That is not victory. It is, however, enough functionality that remaining excuses now have to fill out paperwork.

> Increasingly, things either work, degrade visibly, or have documented reasons why they do not.

* * *

## 🎙️ Voice Reality

Voice remains the primary objective. The project now has real voice infrastructure instead of a wish list with audio icons. Shared microphone handling, push-to-talk, wake monitoring, utterance segmentation, STT, TTS, desktop voice controls, resident follow-up, interruption behavior, and runtime diagnostics all exist in observable paths.

What is validated or materially present:

* local STT and TTS runtime selection by host readiness
* push-to-talk and wake paths over a shared stream
* resident voice invocation and bounded follow-up windows
* barge-in/interruption handling and playback coordination
* live voice tests for selected host paths
* desktop resident voice proof paths
* Windows ARM64 Qualcomm QNN STT and TTS paths
* Windows AMD64 CUDA and DirectML TTS paths

What still needs work is the pleasant part: latency, timing, conversational smoothness, natural interruption, robustness, and the small matter of making it feel less like a stack of subsystems successfully pretending to be one organism.

> Voice is not “done.” It is real enough now for the remaining work to become annoyingly measurable.

* * *

## 🏃 Runtime and Hardware

JARVISv7 treats hardware differences as architecture, not an embarrassing surprise to be patched later. Startup begins with profiling, provisioning, and readiness checks so runtime selection can be based on evidence instead of optimism. Windows AMD64, Windows ARM64, and selected Linux paths are treated as real targets rather than future apology letters.

Current runtime posture:

* CPU fallback paths are expected and explicitly represented.
* Linux AMD64 NVIDIA CUDA managed `llama.cpp` is live-proven in WSL2 using CUDA 12.4; WSL2 is the proving environment, not a separate runtime identity.
* ARM64 Adreno OpenCL `llama.cpp` support remains a documented staged path.
* Windows ARM64 Qualcomm QNN acceleration is verified for supported voice paths.
* AMD64 does not select QNN and does not pretend to.
* DirectML, CUDA, QNN, and other accelerator claims remain bounded by what has actually been proven.

The technical helper docs are here when the hardware rabbit hole becomes unavoidable:

* [docs/jarvis-arm-llamacpp.md](docs/jarvis-arm-llamacpp.md)
* [docs/jarvis-arm-whisper.md](docs/jarvis-arm-whisper.md)

Hardware acceleration is welcome. Hardware fan fiction is not.

> Prove it, record it, then claim it. Preferably in that order.

* * *

## 💾 Memory and Continuity

Memory is no longer just a concept taped to the side of the conversation engine with hope. JARVISv7 has bounded working context, session timelines, continuity packets, disk-backed episodic memory, SQLite semantic memory, retrieval/cache support, and explicit provenance and write boundaries.

That gives the assistant several useful forms of continuity without pretending they are all the same thing:

* current-turn context
* bounded working memory
* session and timeline continuity
* episodic recall across sessions
* semantic facts with durable storage
* persisted artifacts for reconstruction and evidence

This is a meaningful foundation, not the final form. Better retrieval, preference memory, procedural knowledge, correction workflows, and more useful long-term continuity still belong ahead.

> It remembers more than before. It does not yet have a soul. Please stop checking.

* * *

## ⚖️ Agents, Tools, and Governance

One reason v7 exists is that capable systems drift when rules are treated as decorative. JARVISv7 keeps governance close to the foundation: explicit policy, inspectable state, durable evidence, permission boundaries, and disabled-by-default agent surfaces.

Where things stand now:

* agent policy, specs, ledger records, and read-only trace/status boundaries exist
* autonomous or background agent execution does not
* general-purpose tool execution was intentionally removed until there is a real product path for it
* future tools, skills, MCP connections, plugins, and agents are expected to compose through explicit capability and permission boundaries
* inactive features are not granted honorary production status for showing up in a directory

The destination is still ambitious: reusable skills, governed tools, external integrations, plugins, and opt-in agents that can act without replacing the core assistant or inventing a second orchestration system.

This is not a lack of ambition. It is how the project avoids waking up with a self-important framework where a feature was requested.

> The system is not trying to become more dramatic. The system is trying to become more correct.

* * *

## 🧬 Personality and Presentation

Personality is treated as a subsystem, not seasoning. The assistant voice is configured, bounded, inspectable, and compatible with deterministic orchestration. Tone can exist without being allowed to override facts, policy, or basic survival instincts.

What this means in practice:

* personality profiles influence response presentation
* prompt envelopes include structured personality context
* rendering and cleanup paths keep text and voice output bounded
* provenance and policy remain separate from persona
* the assistant can be more consistent without being given root access to reality

The end goal is not blandness. It is personality that survives validation.

> Snark is acceptable. Hallucinated authority is not.

* * *

## ⚠️ Remaining Work

The main unanswered question is no longer what JARVIS should be. The answer is in [ProjectVision.md](ProjectVision.md): a local, voice-first, desktop-resident assistant that grows from a truthful runtime foundation into useful memory, governed action, reusable capability, and eventually opt-in agent behavior.

Major remaining goals:

* improve real-time voice quality, latency, interruption, and conversational flow
* strengthen desktop presence and user-facing state visibility
* deepen memory into preferences, procedures, correction, and better long-term usefulness
* introduce reusable skills and governed tools without loosening execution boundaries
* support MCP connections, plugins, and external integrations through recognizable reusable shapes
* introduce agents as opt-in orchestration over proven assistant capabilities
* improve parity across supported host classes
* prove more live runtime paths
* reduce the number of places where “works” still requires a footnote

That is not a small list. It is also not a reason to restart the project again, which is character development.

> The roadmap is increasingly engineering work rather than philosophical fog. Inconvenient, but healthy.

* * *

## 🔁 What Changed From v6

v6 showed that the voice-first assistant vision was achievable. It also showed that architecture without strong boundaries can become ambitious in the least helpful ways. v7 keeps the vision and adds discipline: acceptance criteria, inventories, validation harnesses, explicit degraded states, hardware-aware provisioning, traceability, and less tolerance for “probably fine.”

Compared with v6, v7 emphasizes:

* evidence-backed capability claims
* hardware-aware setup before runtime selection
* shared turn/session paths for text and voice
* desktop as the durable surface
* explicit personality, policy, memory, and capability boundaries
* validation on target host classes instead of wishful portability
* truthful degraded states when a feature is unavailable
