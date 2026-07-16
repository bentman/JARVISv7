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

* [ProjectVision.md](ProjectVision.md) — target product behavior
* [SYSTEM_INVENTORY.md](SYSTEM_INVENTORY.md) — what is actually observable now
* [CHANGE_LOG.md](CHANGE_LOG.md) — completed work with evidence
* [AGENTS.md](AGENTS.md) — repository rules for assisted work
* [docs/QuickStart-windows.md](docs/QuickStart-windows.md) — Windows setup and repo-run desktop launch
* [docs/QuickStart-linux.md](docs/QuickStart-linux.md) — Linux and WSL setup, currently with more optimism than evidence

The README is intentionally not the technical manual. Nobody wins when the front page becomes an installation crime scene.

> If you need commands, use the guide. If you need philosophy, continue scrolling at your own risk.

* * *

## 🧭 Project Vision

The destination has changed very little: JARVISv7 should behave like a persistent local assistant, not a text system pretending voice is a theme pack. The primary path is voice-first, desktop-first, local-first, hardware-aware, deterministic, and explicit about state. Text remains useful, but it is a fallback and diagnostic path into the same turn engine, not the product center of gravity.

Core invariants:

* local execution first, with cloud escalation only by explicit policy
* voice as the root interaction model
* desktop presence as the durable user surface
* hardware profiling, provisioning, and readiness before runtime selection
* deterministic orchestration instead of prompt-only control flow
* memory, artifacts, tools, traces, and personality outside the model
* visible failure states instead of silent collapse
* validation evidence before capability claims

That sounds less glamorous than “AI assistant,” but it is far more useful when something breaks at 11:47 PM and the system has the courtesy to say why.

> The goal is natural interaction without pretending the engineering underneath is simple.

* * *

## 🧱 What Exists Now

JARVISv7 now has more than scaffolding. It has a hardware-aware backend, a desktop shell, local voice runtimes, a conversation engine, session continuity, a resident voice path, structured personality handling, deterministic tool boundaries, and verified runtime evidence across Windows AMD64 and Windows ARM64. It is still under construction, but increasingly the problems are specific instead of mystical.

Current working areas include:

* FastAPI backend with hardware profiler, provisioning, preflight, readiness, and status routes
* Tauri desktop shell with backend lifecycle, resident voice controls, readiness/status display, and local settings flow
* STT/TTS runtime families using ONNX Whisper and Kokoro paths, with device selection driven by readiness
* resident shared-stream voice layer with push-to-talk, wake monitoring, bounded follow-up, and barge-in handling
* canonical text and voice turn paths through the conversation engine
* managed local `llama.cpp` LLM runtime with Ollama fallback
* local service substrate for Redis and SearXNG-backed features
* session continuity, timeline artifacts, prompt assembly, and bounded memory context
* agent specs, dry-run roles, local ledger records, and explicit governance boundaries

That is not victory. It is, however, enough functionality that remaining excuses now have to fill out paperwork.

> Increasingly, things either work, degrade visibly, or have documented reasons why they do not.

* * *

## 🎙️ Voice Reality

Voice remains the primary objective. The project now has real voice infrastructure instead of a wish list with audio icons. Shared microphone handling, push-to-talk, wake monitoring, utterance segmentation, STT, TTS, desktop voice controls, resident follow-up, and interruption behavior have all moved into observable code paths.

What is validated or materially present:

* local STT and TTS runtime selection by host readiness
* push-to-talk and wake paths over a shared stream
* resident voice invocation and bounded follow-up windows
* barge-in/interruption helpers and playback coordination
* live voice tests for selected host paths
* desktop resident voice proof paths
* ARM64 QNN STT validation for the side-by-side `whisper-qualcomm-qnn` model

What still needs work is the pleasant part: latency, timing, conversational smoothness, natural interruption, robustness, and the small matter of making it feel less like a stack of subsystems successfully pretending to be one organism.

> Voice is not “done.” It is real enough now for the remaining work to become annoyingly measurable.

* * *

## 🏃 Runtime and Hardware

JARVISv7 treats hardware differences as architecture, not an embarrassing surprise to be patched later. Startup begins with profiling, provisioning, and readiness checks so runtime selection can be based on evidence instead of optimism. Windows AMD64 and Windows ARM64 are first-class targets because “works on my machine” becomes less impressive when there is only one machine.

Current runtime posture:

* CPU fallback paths are expected and explicitly represented.
* AMD64 CUDA local LLM sidecar work has live evidence where staged.
* ARM64 Adreno OpenCL `llama.cpp` support is documented as an end-user/staged sidecar path.
* Windows ARM64 Qualcomm QNN STT is verified through `QNNExecutionProvider` and `QnnHtp.dll` evidence.
* AMD64 does not select QNN and does not pretend to.
* DirectML, ROCm, Metal, CoreML, and other accelerator paths remain bounded by what has actually been proven.

The technical helper docs are here when the hardware rabbit hole becomes unavoidable:

* [docs/jarvis-arm-llamacpp.md](docs/jarvis-arm-llamacpp.md)
* [docs/jarvis-arm-whisper.md](docs/jarvis-arm-whisper.md)

Hardware acceleration is welcome. Hardware fan fiction is not.

> Prove it, record it, then claim it. Preferably in that order.

* * *

## 💾 Memory and Continuity

Memory is no longer just a concept taped to the side of the conversation engine with hope. JARVISv7 has disk-backed episodic memory foundations, prompt assembly integration, session timeline artifacts, continuity packets, and explicit provenance boundaries. The system can carry bounded context across related turns without pretending that every cached thought is suddenly wisdom.

Current memory and continuity scope:

* session and turn artifacts
* bounded continuity policy
* prompt assembly with trusted context ordering
* disk-backed episodic memory foundations
* retrieval/cache support where appropriate
* explicit boundaries around what is and is not remembered

This is a meaningful step toward the ProjectVision target of continuity, but it is not the final memory system. Semantic/vector memory, richer retrieval, proactive memory policy, and deeper cross-session usefulness remain future work.

> It remembers more than before. It does not yet have a soul. Please stop checking.

* * *

## ⚖️ Agents, Tools, and Governance

One reason v7 exists is that capable systems drift when rules are treated as decorative. JARVISv7 responds by making governance part of the architecture: explicit policy, structured agent specs, local ledger records, deterministic tool boundaries, read-only trace diagnostics, and disabled-by-default agent surfaces. The system is trying to become useful without becoming a tiny unsupervised bureaucracy.

Current boundaries:

* agent specs and Agent Creator exist as bounded, spec-first surfaces
* dry-run planner, executor, critic, curator, and learner roles exist for structure and tests
* local ledger records and trace diagnostics support auditability
* tool invocation is deterministic and constrained
* policy and status surfaces avoid claiming inactive things are secretly powerful
* autonomous/background agent execution is not claimed

This is not a lack of ambition. It is how the project avoids waking up with a self-important framework where a feature was requested.

> The system is not trying to become more dramatic. The system is trying to become more correct.

* * *

## 🧬 Personality and Presentation

Personality is treated as a subsystem, not seasoning. The assistant voice is expected to be configured, bounded, inspectable, and compatible with deterministic orchestration. Tone can exist without being allowed to override facts, policy, or basic survival instincts.

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

The main unanswered question is no longer what JARVIS should be. The answer is in [ProjectVision.md](ProjectVision.md): a local, voice-first, desktop-resident assistant with explicit cognition, real continuity, reliable runtime selection, visible state, and clean failure behavior. The remaining work is mostly the more irritating category: implementation quality.

Major remaining goals:

* improve real-time voice quality, latency, interruption, and conversational flow
* strengthen desktop presence and user-facing state visibility
* deepen memory beyond episodic/recency-oriented foundations
* expand tool-grounded usefulness without loosening governance
* integrate agents as opt-in orchestration rather than uncontrolled background magic
* improve architecture parity across supported host classes
* prove more runtime paths with live evidence
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
* explicit personality, policy, memory, and tool boundaries
* validation on target host classes instead of wishful portability
* truthful degraded states when a feature is unavailable
