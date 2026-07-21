# J.A.R.V.I.S v7

![Not Magic](https://img.shields.io/badge/Not-Magic-purple)
![Evidence Required](https://img.shields.io/badge/Evidence-Required-orange)
![Status: Building](https://img.shields.io/badge/Status-Building-green)
![License: MIT](https://img.shields.io/badge/License-MIT-blue)

* * *

## 📚 **J**udiciously **A**daptive **R**untime **V**oice **I**nterface **S**ystem — Mark7

* Still not sentient.
* Still not flying the suit.
* Still not allowed to call vibes a validation strategy.
* Now with enough runtime evidence that remaining problems have nowhere polite to hide.

JARVISv7 is a local-first, voice-first personal assistant project built for real conversational interaction on user-owned hardware. The target is not a browser chat box with a microphone button taped to it. The target is a desktop-resident assistant that can listen, reason, respond, speak, remember useful context, expose what it is doing, and fail in ways humans can actually diagnose.

That description is the destination. The reason this is version seven is the route taken to reach it.

JARVISv7 exists because v6 taught two important lessons:

> The vision was mostly right.  
> The implementation was occasionally creative.  

* Some architectural decisions worked exactly as intended — some did not.  
* Several worked just well enough to expose entirely different problems.  
* Which, in hindsight, is indeed progress.  

Since then, v7 has moved from "another restart with better rules" to an actual construction site with permits, inspections, and a suspicious number of extension cords. It remains surprisingly difficult to manage.

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
* [docs/QuickStart-linux.md](docs/QuickStart-linux.md) — Linux and WSL setup — usable, documented, and still earning its confidence

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
* allow action only through explicit capability boundaries
* add reusable skills, integrations, plugins, and agents only after the foundation can support them

That sounds less glamorous than “AI assistant,” but it is far more useful when something breaks at 11:47 PM and the system has the courtesy to say why.  

> [ProjectVision.md](ProjectVision.md) contains the destination.  
> [SYSTEM_INVENTORY.md](SYSTEM_INVENTORY.md) tracks how much ground has actually been covered.  
> The goal is natural interaction without pretending the engineering underneath is simple.  

* * *

## 🧱 What Exists Now

JARVISv7 now has substantially more than scaffolding. It has a hardware-aware backend, a desktop shell, local voice runtimes, a working conversation path, resident voice behavior, session continuity, structured personality, several distinct memory layers, and verified runtime evidence across multiple host and accelerator paths. It is still under construction, but increasingly the problems are specific instead of mystical.

It has enough functioning foundation that the remaining work is increasingly about quality, reach, and composition rather than proving the basic idea.

Current working areas include:

* FastAPI backend with hardware profiling, provisioning, preflight, readiness, diagnostics, session, and status surfaces
* Tauri desktop shell with backend lifecycle, resident voice controls, readiness/status display, diagnostics, and local settings flow
* local STT, TTS, wake, and LLM runtime paths selected from readiness evidence
* resident shared-stream voice with push-to-talk, wake monitoring, bounded follow-up, and interruption handling
* canonical text and voice turns through the same conversation engine
* managed local `llama.cpp` with Ollama fallback
* disk-backed episodic memory, SQLite semantic memory, bounded working context, retrieval, and persisted turn/session artifacts
* structured personality profiles applied through explicit prompt and response boundaries

That is not victory. It is, however, enough functionality that remaining excuses now have to fill out paperwork.

> Increasingly, things either work, degrade visibly, or have documented reasons why they do not.

* * *

## 🎙️ Voice Reality

Voice remains the primary objective. The project now has real voice infrastructure instead of a wish list with audio icons. Shared microphone handling, push-to-talk, wake monitoring, utterance segmentation, STT, TTS, desktop voice controls, resident follow-up, interruption behavior, and runtime diagnostics all exist in observable paths.

What is validated or materially present:

* push-to-talk and wake paths over a shared stream
* resident voice invocation and bounded follow-up windows
* barge-in/interruption handling and playback coordination
* live voice tests for selected host paths
* desktop resident voice proof paths
* Windows AMD64 local voice paths, including validated CUDA and DirectML TTS execution where supported
* Windows ARM64 Qualcomm QNN STT and TTS paths
* Linux voice and runtime paths where explicitly documented and validated — optimism sold separately

What still needs work is the pleasant part: latency, timing, conversational smoothness, natural interruption, robustness, and the small matter of making it feel less like a stack of subsystems successfully pretending to be one organism.

> Voice is not “done.” It is real enough now for the remaining work to become annoyingly measurable.

* * *

## 🏃 Runtime and Hardware

JARVISv7 treats hardware differences as architecture, not an embarrassing surprise to be patched later. Startup begins with profiling, provisioning, and readiness checks so runtime selection can be based on evidence instead of optimism.

Proven runtime posture:

* Windows AMD64 is the broadest proving target, with CPU fallback and selected CUDA/DirectML paths.
* Windows ARM64 is a first-class target, including validated Qualcomm QNN voice acceleration where supported.
* Linux is supported enough to welcome contributors without claiming every path has achieved diplomatic immunity.
* All accelerator claims remain bounded by what has actually been proven.

Other acceleration is available with effort outside repo automation:

* ARM64 Adreno OpenCL accelerated `llama.cpp` remains a side-loaded path compiled through a helper guide.
* ARM64 QNN accelerated Whisper requires Qualcomm access and the corresponding binary download.
* AMD64 QNN accelerated `llama.cpp` can also be side-loaded through its helper guide.
* Linux AMD64 CUDA accelerated `llama.cpp` is available through a side-loaded binary compiled against CUDA 12.4.
* These alternatives are available for operators who choose them, but they are not represented as part of the proven default stack.

The technical helper docs are here when the hardware rabbit hole becomes unavoidable:

* [docs/helpers/jarvis-arm-llamacpp.md](docs/helpers/jarvis-arm-llamacpp.md)
* [docs/helpers/jarvis-arm-llamacpp-qnn.md](docs/helpers/jarvis-arm-llamacpp-qnn.md)
* [docs/helpers/jarvis-arm-whisper.md](docs/helpers/jarvis-arm-whisper.md)
* [docs/helpers/jarvis-wsl-llamacpp.md](docs/helpers/jarvis-wsl-llamacpp.md)

Hardware acceleration is welcome. Hardware fan fiction is not.

> Prove it, record it, then claim it. Preferably in that order.

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

## 💾 Memory and Continuity

Memory is no longer just a concept taped to the side of the conversation engine with hope. JARVISv7 has bounded working context, session timelines, continuity packets, disk-backed episodic memory, SQLite semantic memory, retrieval/cache support, and explicit provenance and write boundaries.

That gives the assistant several useful forms of continuity without pretending they are all the same thing:

* current-turn context
* bounded working memory
* session and timeline continuity
* episodic recall across sessions
* semantic facts with durable storage
* persisted artifacts for reconstruction and evidence

This is a meaningful foundation, not the final form. Better retrieval, preference memory, procedural knowledge, correction workflows, and genuinely useful long-term continuity still lie ahead.

> It remembers more than before. It does not yet have a soul. Please stop checking.

* * *

## ⚠️ Remaining Work

The main unanswered question is no longer what JARVIS should be. The answer is in [ProjectVision.md](ProjectVision.md): a local, voice-first, desktop-resident assistant that grows from a truthful runtime foundation into useful memory, governed action, reusable capability, and eventually opt-in agent behavior.

The actual gaps are less theatrical and more useful:

* improve real-time voice latency, endpointing, interruption, recovery, and conversational smoothness
* strengthen desktop presence, interaction polish, settings clarity, and user-facing state visibility
* deepen memory into preference, procedural, correction, retention, and better retrieval behavior
* connect useful external capability to the normal assistant path instead of leaving provider substrates isolated
* introduce reusable instructions, prompts, and skills without turning them into hidden policy
* establish honest tool execution, permissions, confirmations, cancellation, and audit behavior
* support MCP connections, plugins, and integrations through recognizable reusable shapes
* introduce agents only after tools, memory, permissions, and handoffs are proven beneath them
* improve Windows AMD64 and Windows ARM64 parity, then broaden Linux contributor paths without over-claiming them
* prove more live runtime paths and reduce the number of places where “works” still requires a footnote

That is not a small list. It is also not a reason to restart the project again, which is character development.

> The roadmap is increasingly engineering work rather than philosophical fog. Inconvenient, but healthy.

* * *

## 🧩 Extending JARVIS: Skills, Tools, Integrations, Plugins, and Agents

These are destination capabilities, not a disguised inventory of things that once had filenames.

The intended order matters:

* instructions and reusable prompts make behavior repeatable
* skills package bounded procedural knowledge
* tools provide explicit executable actions
* MCP connections and integrations expose external context and capability
* plugins bundle reusable capability without owning the whole application
* agents coordinate proven capabilities for larger, opt-in work

The normal assistant must remain useful without any of them. Extensions should add capability, not establish a parallel government in the basement.

> First make the assistant dependable. Then let it delegate.

* * *

## 🔁 What Changed From v6

v6 showed that the voice-first assistant vision was achievable. It also showed that architecture without strong boundaries can become ambitious in the least helpful ways. v7 keeps the vision and adds discipline: acceptance criteria, inventories, validation harnesses, explicit degraded states, hardware-aware provisioning, traceability, and less tolerance for “probably fine.”

As a result, JARVISv7 places much greater emphasis on:

* evidence-backed capability claims
* hardware-aware setup before runtime selection
* shared turn/session paths for text and voice
* desktop as the durable surface
* explicit personality, policy, memory, and capability boundaries
* Windows AMD64 first, Windows ARM64 alongside it, and Linux paths expanded with evidence
* truthful degraded states when a feature is unavailable

> That sounds less exciting, but turns out to be far more useful.

* * *

## 🤝 Contributions Welcome

JARVIS has reached the stage where progress comes less from generating new ideas and more from executing existing ones consistently.

Contributions are welcome, particularly those that:

* improve voice interaction
* improve memory and retrieval systems
* reduce complexity and improve reliability
* improve Windows AMD64, Windows ARM64, and Linux platform support
* shape future agent boundaries without turning them into autonomous gremlins
* improve architecture parity without pretending one machine represents the species
* improve hardware and runtime coverage — donations remain suspiciously effective
* improve live runtime validation instead of just making tests feel emotionally supportive
* advance RAG, MCP, skills, tools, plugins, agents, and local/cloud escalation without pretending they are already finished

**BONUS POINTS:** solving real problems without introducing three new ones.  
**DOUBLE BONUS POINTS:** documenting what actually happened instead of what would have been nice if it happened.

> Pull requests are welcome. Surprise architecture is less welcome.  
> The rules are stricter now. [AGENTS.md](AGENTS.md) is no longer a suggestion.

* * *

## 📜 License

Distributed under the MIT License.

Use it, modify it, learn from it, and improve it. The license does not include an arc reactor or legal permission to blame the repository for decisions made after midnight. A British synthetic voice may be the default. The accent is not part of the license. Just remember that experimental software occasionally behaves experimentally.

> See [LICENSE](LICENSE) for the legally competent version.

* * *

## 🧱 Acknowledgments

JARVISv7 did not appear fully formed. It accumulated through six earlier attempts, each of which solved something useful and uncovered something inconvenient.

Built on the accumulated successes, mistakes, redesigns, overcorrections, and occasional moments of accidental competence from:

* [**JARVISv1 (Just A Rough Very Incomplete Start)**](https://github.com/bentman/JARVISv1)  
  The beginning — many milestones, alpha nonetheless.

* [**JARVISv2 (Just Almost Real Viable Intelligent System)**](https://github.com/bentman/JARVISv2)  
  The first version that hinted this might actually be possible.

* [**JARVISv3 (Just A Reliable Variant In Service)**](https://github.com/bentman/JARVISv3)  
  The version that introduced stability.

* [**JARVISv4 (Just A Reimagined Version In Stabilization)**](https://github.com/bentman/JARVISv4)  
  The version that introduced discipline.

* [**JARVISv5 (Just A Runnable, Verified Iterative System)**](https://github.com/bentman/JARVISv5)  
  The first version that behaved like a system — without voice.

* [**JARVISv6 (Just Another Restart, Voice Included System)**](https://github.com/bentman/JARVISv6)  
  The version that proved the vision could work and exposed what still needed to be fixed.

* [**JARVISv7 (Just Another Restart, Validated Iteratively System)**](README.md) << this one >>  
  The version proving that "under construction" and "making progress" can, occasionally, be the same thing.

* * *

## 🧾 Bottom Line

JARVISv7 is not finished. It is no longer imaginary either.

There is a real desktop shell, a real local conversation path, real voice infrastructure, real hardware-aware runtime selection, real personality handling, real continuity and memory foundations, and enough validation to distinguish progress from decorative confidence.

The destination remains ambitious. The foundation is finally substantial enough that building upward is more sensible than starting over.

> Not magic. Not done. Definitely in progress.  
> “Sometimes you gotta run before you can walk.” — Tony Stark
