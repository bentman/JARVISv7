
## Repo Structure

JARVISv7 uses a repo layout that reinforces runtime domains, keeps declarative configuration separate from code, keeps mutable artifacts out of source, and prevents UI-first drift. The structure is designed to absorb the slice sequence in `slices.md` without restructure at any group boundary.

### Structure Rules

- Top-level folders come first; top-level root files come last; both lists stay alphabetized.
- Runtime domains own behavior; routes and UI surfaces are thin adapters.
- `config/` stores declarative settings and profiles, not mutable runtime state.
- `models/` stores model artifacts only, not executable source.
- `data/`, `cache/`, and `reports/` store mutable outputs and must not contain source-of-truth code.
- Runtime integrations use generic labels where technology may change during development.
- External escalation providers (cloud LLMs, search fallbacks) get explicit runtime files because they are stable policy surfaces.
- Search escalations live under their own provider domain, separate from LLM runtimes.
- Artifacts, sessions, and turns are persisted separately from implementation code.
- Frontend and desktop are product shells; conversation and runtime logic stay in backend domains.
- **Provisioning is PEP 621 / PEP 508 native**: package sets live in `pyproject.toml` as extras with environment-marker gating where markers suffice; hardware-vendor gating that markers cannot express (NPU vendor, CUDA availability) lives in the profiler-driven resolver under `backend/app/hardware/provisioning.py`. `backend/requirements.txt` is a derived lockfile of the base extra, not a source of truth.
- **Tests are arch-aware by design**, not arch-split by directory. Pytest markers + `conftest.py` skip conditions gate tests to the host classes / devices they target. Directory structure reflects test purpose (unit / integration / runtime) and functional domain (voice / turn / desktop / acceleration_matrix / agents / hardware).
- Every voice-family runtime (STT/TTS/LLM/Wake) accepts `device` as a parameter (`cpu` / `cuda` / `directml` / `qnn` / etc.) from day one. New device support is a runtime-internal branch, never a new runtime family.
- QNN is defined structurally from group A (extra, evidence tokens, device slot, flag) and activated later; the file layout accommodates this without new directories.
- Agent framework is a role-separated layer over proven boundaries (turn engine, tool registry, memory, runtimes); it lives in its own domain under `backend/app/agents/` and consumes the existing runtime and turn surfaces unchanged.

### Proposed Top-Level Tree

```text
JARVISv7/
├─ backend/                           # backend runtime, APIs, orchestration, providers, artifacts, agents
├─ cache/                             # mutable cache and backing-store dev assets (redis state, temp); not source code
├─ config/                            # declarative config: app, hardware, models, agents, policies, personality, prompts
├─ data/                              # mutable runtime state: memory, sessions, turns, agents (ledger), temp
├─ desktop/                           # desktop shell (tauri/native integration, overlays, tray, hotkeys)
├─ docs/                              # architecture, runtime, and decision records
├─ frontend/                          # web/debug/operator surface
├─ models/                            # local model artifacts and downloaded runtime assets (llm, stt, tts, wake)
├─ reports/                           # validation, diagnostics, benchmark outputs
├─ scripts/                           # provisioning, bootstrap, validation, packaging, utility scripts
├─ .env.example
├─ AGENTS.md
├─ CHANGE_LOG.md
├─ docker-compose.yml
├─ ProjectVision.md
├─ pyproject.toml                     # single source of truth for Python package metadata + extras + tooling
├─ README.md
├─ repo_tree.md
├─ slices.md
└─ SYSTEM_INVENTORY.md
```

**Root-file ownership notes:**
- `pyproject.toml` — provisioning authority (PEP 621 metadata, extras, pytest markers, ruff/mypy/coverage config). The only place package sets are declared.
- `docker-compose.yml` — Redis, SearXNG, and later local llama.cpp. Declared at the root so one `docker compose up` stands up the substrate.
- `.env.example` — operator-supplied values: API keys for cloud LLM escalation, QAIRT SDK path, `PVPORCUPINE_MODEL_PATH`, Ollama endpoint override, etc. Never checked in as `.env`.
- `ProjectVision.md` / `SYSTEM_INVENTORY.md` / `CHANGE_LOG.md` / `slices.md` / `repo_tree.md` — four separate governance docs, intentionally not conflated.

### Backend Runtime Domains

```text
backend/
├─ app/
│  ├─ agents/                        # role-separated agent framework (Group I); consumes runtimes + tools + turn engine
│  │  ├─ base.py                     # common AgentBase interface + role contract enforcement
│  │  ├─ critic.py                   # output validation role
│  │  ├─ curator.py                  # training-data mining role
│  │  ├─ executor.py                 # tool-invocation role
│  │  ├─ learner.py                  # training-cycle orchestration role
│  │  ├─ ledger.py                   # SQLite-backed agent message bus (I.2)
│  │  ├─ messages.py                 # typed AgentMessage and message-type enums
│  │  ├─ planner.py                  # task-decomposition role
│  │  └─ schemas.py                  # JSON schemas for message payloads
│  ├─ api/
│  │  ├─ dependencies.py             # route dependencies and shared request wiring
│  │  ├─ routes/
│  │  │  ├─ agents.py                # agent status/trace endpoints (read-only)
│  │  │  ├─ diagnostics.py           # diagnostics and health-facing endpoints
│  │  │  ├─ health.py                # health endpoints
│  │  │  ├─ readiness.py             # structured startup summary (family/device/model per subsystem)
│  │  │  ├─ session.py               # session-facing APIs (create, tick, close)
│  │  │  ├─ task.py                  # normal conversation/task APIs (text ingress)
│  │  │  └─ voice.py                 # voice-facing APIs (audio ingress)
│  │  └─ schemas/
│  │     ├─ agents.py                # agent-facing API schemas
│  │     ├─ common.py                # shared API schemas
│  │     ├─ readiness.py             # startup/readiness response schema consumed by desktop shell
│  │     ├─ session.py               # session schemas
│  │     ├─ task.py                  # task schemas
│  │     └─ voice.py                 # voice schemas
│  ├─ artifacts/
│  │  ├─ session_artifact.py         # session artifact definitions
│  │  ├─ storage.py                  # artifact persistence helpers (writes to data/turns, data/sessions)
│  │  ├─ trace_writer.py             # trace writing utilities
│  │  └─ turn_artifact.py            # canonical turn artifact definitions (schema fixed in C.3)
│  ├─ cache/                         # cache code layer (access, policy, client); distinct from top-level cache/ data directory
│  │  ├─ keys.py                     # cache key naming and namespaces
│  │  ├─ manager.py                  # cache access layer (fail-closed when Redis unavailable)
│  │  ├─ policies.py                 # cache policy rules
│  │  └─ redis_client.py             # redis integration
│  ├─ cognition/
│  │  ├─ executor.py                 # deterministic tool execution coordination (ACTING state owner, F.1)
│  │  ├─ planner.py                  # turn-level planning logic (distinct from agents/planner.py role)
│  │  ├─ policies.py                 # cognition policies
│  │  ├─ prompt_assembler.py         # prompt assembly with personality + working + episodic memory inputs
│  │  └─ responder.py                # response shaping logic + responder-boundary sanitation before TTS
│  ├─ conversation/
│  │  ├─ engine.py                   # turn lifecycle orchestration; explicit state transitions (no implicit)
│  │  ├─ interruption.py             # interruption/barge-in handling (C.5)
│  │  ├─ session_manager.py          # session lifecycle management (C.3)
│  │  ├─ states.py                   # canonical conversation states enum
│  │  └─ turn_manager.py             # turn creation/update/finalization
│  ├─ core/
│  │  ├─ capabilities.py             # normalized capability and profile types; includes qnn_available + directml_candidate flags
│  │  ├─ errors.py                   # core error types
│  │  ├─ logging.py                  # logging setup with verbose/trace modes for proving host + scripts
│  │  ├─ paths.py                    # canonical filesystem paths
│  │  └─ settings.py                 # environment/app settings (reads .env)
│  ├─ hardware/
│  │  ├─ detectors/
│  │  │  ├─ cpu_detector.py          # CPU detection including arch (amd64/arm64); normalizes at detector boundary
│  │  │  ├─ cuda_detector.py         # CUDA availability + version band detection
│  │  │  ├─ gpu_detector.py          # GPU presence + vendor (NVIDIA/AMD/Intel/Qualcomm/other)
│  │  │  ├─ memory_detector.py       # total + available memory detection
│  │  │  ├─ npu_detector.py          # NPU presence + vendor (Qualcomm/Intel/AMD/other) — never guesses vendor
│  │  │  └─ os_detector.py           # OS + desktop/laptop classification
│  │  ├─ preflight.py                # DLL/backend-path bootstrap (CUDA, QAIRT); import probes; evidence tokens
│  │  ├─ profiler.py                 # main callable profiler + resolve_backend_evidence_tokens()
│  │  └─ provisioning.py             # resolve_required_extras(profile) → ordered extras list; sole provisioning authority
│  ├─ memory/
│  │  ├─ episodic.py                 # episodic memory (cross-session; G.1)
│  │  ├─ manager.py                  # memory coordination layer
│  │  ├─ retrieval.py                # retrieval logic; consults cache layer (G.3)
│  │  ├─ semantic.py                 # semantic memory (future)
│  │  ├─ working.py                  # bounded working memory (in-session; C.3)
│  │  └─ write_policy.py             # explicit memory write policies
│  ├─ models/
│  │  ├─ catalog.py                  # model catalog authority (reads config/models/*.yaml)
│  │  └─ manager.py                  # model verify/ensure authority (HF + release-URL acquisition)
│  ├─ personality/
│  │  ├─ acknowledgment.py           # personality-aware acknowledgment / playback guard surface
│  │  ├─ adapter.py                  # applies personality as prompt-assembly input (never bypasses policy)
│  │  ├─ loader.py                   # loads personality profiles from config/personality/
│  │  ├─ resolver.py                 # resolves active personality for runtime/session
│  │  └─ schema.py                   # structured personality schema
│  ├─ routing/
│  │  ├─ capability_router.py        # routes work from capability flags
│  │  ├─ model_registry.py           # model/provider catalog access
│  │  └─ runtime_selector.py         # chooses concrete runtime/provider (LLM escalation policy owner)
│  ├─ runtimes/
│  │  ├─ internetsearch/
│  │  │  ├─ base.py                  # common internet search runtime interface
│  │  │  ├─ ddgs_runtime.py          # secondary DuckDuckGo search escalation runtime
│  │  │  ├─ searxng_runtime.py       # primary local SearXNG search runtime (E.3)
│  │  │  └─ tavily_runtime.py        # tertiary Tavily search escalation runtime (API key required)
│  │  ├─ llm/
│  │  │  ├─ base.py                  # common LLM runtime interface
│  │  │  ├─ claude_runtime.py        # anthropic escalation runtime (policy-gated)
│  │  │  ├─ gemini_runtime.py        # google escalation runtime (policy-gated)
│  │  │  ├─ local_runtime.py         # local/default LLM runtime (LlamaCppLLM; activated in H.1)
│  │  │  ├─ ollama_runtime.py        # ollama local fallback runtime
│  │  │  ├─ openai_runtime.py        # openai escalation runtime (policy-gated)
│  │  │  ├─ xai_runtime.py           # xAI escalation runtime (policy-gated)
│  │  │  └─ zai_runtime.py           # Z.AI escalation runtime (policy-gated)
│  │  ├─ stt/
│  │  │  ├─ barge_in.py              # barge-in detector used by interruption / wake-concurrency surfaces
│  │  │  ├─ base.py                  # common STT runtime interface; device ∈ {cpu, cuda, directml, qnn}
│  │  │  ├─ onnx_asr_runtime.py      # onnx-asr runtime (Parakeet/Canary/NeMo families over onnxruntime)
│  │  │  ├─ onnx_whisper_runtime.py  # ONNX Whisper over onnxruntime; all device values (QNN branch wired in H.2)
│  │  │  └─ stt_runtime.py           # selector: (family, device) dispatch from profiler readiness
│  │  ├─ tts/
│  │  │  ├─ base.py                  # common TTS runtime interface; device ∈ {cpu, cuda, directml}
│  │  │  ├─ kokoro_onnx_runtime.py   # Kokoro over kokoro-onnx (onnxruntime-backed); cross-platform primary
│  │  │  ├─ playback.py              # blocking / interruptible playback utilities (single interruption point)
│  │  │  └─ tts_runtime.py           # selector: (family, device) dispatch
│  │  └─ wake/
│  │     ├─ base.py                  # common wake runtime interface
│  │     ├─ openwakeword_runtime.py  # openWakeWord over onnxruntime; pre-trained hey_jarvis default (PRIMARY)
│  │     ├─ porcupine_runtime.py     # pvporcupine; optional alternative behind hw-wake-porcupine extra
│  │     └─ wake_runtime.py          # selector: provider ∈ {openwakeword, porcupine}; openwakeword default
│  ├─ services/
│  │  ├─ diagnostics_service.py      # diagnostics-facing service layer
│  │  ├─ session_service.py          # session service layer (resident lifecycle owner, D.3)
│  │  ├─ startup_service.py          # startup/readiness summary service; consumed by desktop shell + proving host
│  │  ├─ task_service.py             # host-facing task/text service (delegates to canonical turn execution)
│  │  ├─ turn_service.py             # canonical transcript-bound turn executor shared by voice/text paths
│  │  └─ voice_service.py            # voice-facing service layer
│  └─ tools/
│     ├─ filesystem/                 # filesystem tools (read-only at F.2 scope; write tools = future slice)
│     ├─ registry.py                 # tool registry (F.2)
│     ├─ search/                     # internal/bundled search tools (adapter over runtimes/internetsearch/)
│     └─ system/                     # system tools (time/date, hardware-info read-only)
├─ tests/
│  ├─ conftest.py                    # arch/device skipif helpers (skip_unless_x64, skip_unless_arm64, skip_unless_cuda,
│  │                                 #   skip_unless_directml, skip_unless_qnn, skip_unless_ollama, etc.);
│  │                                 #   caches preflight per test session; shared fixtures
│  ├─ fixtures/                      # shared test fixtures (known utterance WAV, known prompts, etc.)
│  ├─ unit/                          # fast, no hardware, no network; arch-gated per test via markers
│  │  ├─ agents/                     # agent role unit tests
│  │  ├─ cognition/
│  │  ├─ conversation/
│  │  ├─ hardware/
│  │  ├─ memory/
│  │  ├─ routing/
│  │  └─ runtimes/                   # runtime-family unit tests; device branches selected per marker
│  ├─ integration/                   # multi-module, still no live hardware
│  │  ├─ agents/
│  │  ├─ api/
│  │  └─ services/
│  └─ runtime/                       # live hardware (mic / audio out / GPU / NPU); marker-gated
│     ├─ acceleration_matrix/        # B.5 gate: (family × device × host class) matrix
│     ├─ agents/                     # agent live-path tests (Group I)
│     ├─ desktop/                    # desktop shell live paths
│     ├─ hardware/                   # profiler, preflight, provisioning live probes; provisioning-baseline gate (A.5)
│     ├─ turn/                       # turn engine live paths
│     └─ voice/                      # STT / TTS / Wake live paths
└─ Dockerfile
```

**Note**: `backend/requirements.txt` is not a manual source of truth. It is a generated lockfile of the `pyproject.toml` base extra emitted by the provisioning script. The file carries a top-of-file comment saying so.

**Backend-domain ownership notes:**
- `agents/` consumes `runtimes/`, `tools/`, `services/turn_service.py`, and `memory/` — never reaches past their interfaces. Agent-aware branches in the turn engine are policy-gated; non-agent turns continue to work unchanged.
- `cognition/` owns prompt assembly, tool-execution coordination (ACTING), and response shaping. It is the only layer that combines personality + memory + runtime output into a prompt. Never calls runtimes directly — goes through `routing/runtime_selector.py`.
- `conversation/` owns the state machine and session lifecycle. State transitions are explicit here, never implicit in prompt content.
- `hardware/` is the root of runtime-selection authority. `profiler.py` detects; `provisioning.py` translates facts to extras; `preflight.py` verifies evidence. No runtime file contains host-detection logic.
- `memory/` has a deliberate split: working (in-session, bounded) vs episodic (cross-session, policy-governed) vs semantic (future). `write_policy.py` is the only place that decides what enters each.
- `personality/` is a prompt-assembly input, not an orchestration layer. Never bypasses safety or policy; never lives as opaque prompt fragment.
- `routing/runtime_selector.py` is the single escalation-policy owner for LLM and search. Tool files and cognition files never reach past it.
- `runtimes/` contains one subdirectory per family. Each family has a `base.py` interface, one or more concrete runtimes, and a selector. Device is always a constructor parameter.
- `services/` is the API-facing layer. It orchestrates runtimes, cognition, and memory through their public interfaces; it owns no domain logic itself. The desktop shell (D.2) and proving host (C.6) both consume services — never the layers below.
- `tools/` depends on `runtimes/internetsearch/` (for search) but is otherwise self-contained. New tools drop in by registration; no redesign needed.

### Config Domains

```text
config/
├─ agents/
│  └─ roles.yaml                     # role definitions (system prompt refs, input/output schemas, policy constraints)
├─ app/
│  ├─ defaults.yaml                  # global defaults
│  ├─ policies.yaml                  # safety, fallback, LLM escalation, search escalation, execution,
│  │                                 #   agent-opt-in, filesystem-sandbox-path policies
│  └─ profiles.yaml                  # runtime profiles derived from capability flags
├─ cache/
│  ├─ policies.yaml                  # cache TTL / eviction / namespace policy
│  └─ redis.yaml                     # redis cache config
├─ hardware/
│  └─ notes.md                       # human-readable notes on system prerequisites (QAIRT SDK path, DirectML caveats,
│                                    #   PVPORCUPINE_MODEL_PATH, espeak-ng install, QNN quantization on x64,
│                                    #   ARM64 Tauri toolchain) — package sets live in pyproject.toml
├─ models/
│  ├─ llm.yaml                       # LLM catalog and selection config (local llama.cpp, Ollama, cloud)
│  ├─ models.yaml                    # top-level model registry catalog
│  ├─ search.yaml                    # search runtime/provider config (SearXNG primary, DDGS, Tavily)
│  ├─ stt.yaml                       # STT runtime/model config (whisper-small-onnx, qnn-qdq variant, parakeet)
│  ├─ tts.yaml                       # TTS runtime/model config (kokoro-v1.0-onnx)
│  └─ wake.yaml                      # wake config (openwakeword hey_jarvis default; porcupine optional;
│                                    #   future-custom-keyword caveat notes)
├─ personality/
│  ├─ concise.yaml                   # concise personality profile
│  ├─ default.yaml                   # runtime personality overlay/tuning profile
│  ├─ jarvis_personality.json        # canonical identity/persona source
│  └─ warm.yaml                      # warm personality profile
└─ prompts/
   ├─ agents/                        # per-role system prompt assets (planner, executor, critic, curator, learner)
   ├─ planner/                       # turn-level planner prompt assets (distinct from agents/planner)
   ├─ responder/                     # responder prompt assets
   └─ system/                        # system prompt assets
```

**Config-domain ownership notes:**
- Package sets are declared in `pyproject.toml` under `[project.optional-dependencies]` with PEP 508 environment markers where markers suffice. Vendor-specific gating that markers cannot express (NPU vendor, CUDA presence) is applied by `backend/app/hardware/provisioning.py::resolve_required_extras()`. `config/hardware/notes.md` holds only human-facing operator notes about non-pip prerequisites.
- `config/app/policies.yaml` is the escalation and opt-in surface. Adding a cloud LLM provider, enabling the agent framework, or changing the search escalation order is a policy edit — not code.
- `config/models/*.yaml` catalogs are the only place model identities, repo IDs, local paths, and device-preferred variants are declared. Runtimes read from the catalog; they never hardcode model names.
- `config/personality/` carries structured personality profiles. The `personality` domain in `backend/app/` loads them; the prompts themselves are structured config, not free-form prompt fragments.
- `config/prompts/` is split by consumer: `agents/` for the role framework, `planner/` + `responder/` for the turn-level cognition layer, `system/` for shared assets. Each role/layer has its own subdirectory so prompt edits have a single obvious location.

### Mutable Runtime Domains

```text
cache/                               # mutable data only; no source code lives here
├─ redis/                            # local redis persistence and dev data
└─ temp/                             # cache-related temp outputs

data/
├─ agents/
│  └─ ledger.db                      # durable agent message bus (I.2); SQLite-backed
├─ memory/
│  ├─ episodic/                      # episodic memory data (cross-session; durable authority for G)
│  ├─ semantic/                      # semantic memory data (future)
│  └─ working/                       # working memory data (in-session)
├─ sessions/                         # session artifacts and persisted state (durable authority)
├─ temp/                             # runtime temp files
└─ turns/                            # turn artifacts (durable authority; C.3 schema)

reports/
├─ benchmarks/                       # benchmark outputs
├─ diagnostics/                      # diagnostics outputs (proving-host --trace-to destination; validation-suite
│                                    #   trace artifacts; one subdirectory per run timestamp)
└─ validation/                       # validation reports (from validate_backend.py runs; one per run)
```

**Mutable-domain ownership notes:**
- `cache/` is infrastructure acceleration only; losing it does not lose user data. Redis is coordination + retrieval acceleration, never source of truth.
- `data/` holds durable authority for everything the assistant must remember: turns, sessions, memory, agent ledger. Backup target. Never contains source code.
- `reports/` is diagnostic output, safe to delete. Everything written here has a run-timestamped path printed at startup so logs correlate to artifacts.

### Model Artifact Domains

```text
models/
├─ llm/                              # local LLM model artifacts (llama.cpp-consumable formats; H.1)
├─ stt/
│  ├─ whisper-small-onnx/            # ONNX Whisper (CPU/CUDA/DirectML)
│  ├─ whisper-small-onnx-qnn-qdq/    # Quantized/QDQ Whisper for QNN (defined A.6, acquired H.2)
│  └─ parakeet-tdt/                  # Parakeet-family ONNX model for onnx-asr path
├─ tts/
│  └─ kokoro-v1.0-onnx/              # Kokoro ONNX model + voices (kokoro-v1.0.onnx + voices-v1.0.bin pair)
└─ wake/
   ├─ openwakeword/                  # openWakeWord .onnx models (arch-independent):
   │                                 #   hey_jarvis_v0.1.onnx + melspectrogram.onnx + embedding_model.onnx
   └─ porcupine/                     # Porcupine custom .ppn files when hw-wake-porcupine extra is installed
                                     #   (per-arch if Picovoice Console requires separate Windows x64/ARM64 files)
```

### Desktop Shell Domain

```text
desktop/
├─ src/                              # web UI: conversation display, status panel, hardware + LLM selection
│  ├─ assets/
│  ├─ components/
│  │  ├─ conversation/               # conversation display + tool-grounded response rendering (F.3)
│  │  ├─ hardware-selection/         # shows active family + device per STT/TTS/LLM/Wake
│  │  ├─ llm-selection/              # policy-gated runtime switcher (local/Ollama/cloud)
│  │  ├─ status/                     # tray + in-window state display (all 12 canonical states)
│  │  └─ tray/                       # system tray presence + state icons + context menu
│  ├─ index.html
│  ├─ main.js
│  └─ style.css
├─ src-tauri/
│  ├─ src/
│  │  ├─ backend.rs                  # backend process lifecycle bridge
│  │  ├─ lib.rs                      # Tauri app entry
│  │  ├─ main.rs
│  │  └─ tray.rs                     # tray presence, state icons, context menu
│  ├─ Cargo.toml
│  ├─ build.rs
│  └─ tauri.conf.json
└─ README.md                         # dev prerequisites by arch:
                                     #   x64: Rust stable, Node LTS, MSVC v143, WebView2
                                     #   arm64: Rust stable + rustup aarch64-pc-windows-msvc target,
                                     #          Node LTS (arm64 where available),
                                     #          MSVC v143 C++ ARM64 build tools, WebView2
```

### Scripts Domain

Scripts follow a common convention: every script accepts `--verbose`, `--dry-run`, `--trace-to <dir>`; every script emits a host-fingerprint line (arch / Python version / active extras / readiness) as its first stdout line so logs are self-identifying. Scripts are orchestrators over `backend/app/**` — they never duplicate application logic.

```text
scripts/
├─ bootstrap.py                      # end-to-end orchestration for a new host:
│                                    #   profile → provision → ensure models → preflight → readiness summary.
│                                    #   Single command for new-host setup; stops at first failed checkpoint.
├─ ensure_models.py                  # model catalog acquisition / verification
│                                    #   (HuggingFace + openWakeWord release URLs; HF_HUB_OFFLINE toggle handled here)
├─ provision.py                      # PROVISIONING AUTHORITY: calls resolve_required_extras() → pip install -e .[extras]
│                                    #   Subcommands:
│                                    #     install   — run full provisioning
│                                    #     verify    — re-run without installing; confirm resolved extras match current host
│                                    #     lock      — emit platform-pinned backend/requirements.txt from base extra
│                                    #     dry-run   — print the install plan only
│                                    #     explain   — print why each extra was chosen (resolver reasoning trace)
├─ run_backend.py                    # start backend API only (desktop-less); used by desktop shell and tests
├─ run_jarvis.py                     # proving host (developer/diagnostic); NOT the durable application surface
│                                    #   Flags: --turns, --voice-only, --text-only, --verbose, --trace-to, --profile,
│                                    #          --policy-override, --dry-run
└─ validate_backend.py               # VALIDATION AUTHORITY over backend/tests/**; subcommand-based:
                                     #   profile     — run profiler + preflight; print capability report
                                     #   unit        — unit suite only
                                     #   integration — integration suite
                                     #   runtime     — live runtime suite
                                     #                 [--families stt,tts,llm,wake] [--devices cpu,cuda,directml,qnn]
                                     #   regression  — minimum green-on-current-host set for slice closeouts
                                     #   matrix      — B.5 acceleration matrix
                                     #   all         — unit + integration + regression
                                     #   ci          — suppresses live markers; missing hardware = skipped-ok
                                     #   Exit codes: 0 pass | 1 fail | 2 skipped-not-failed | 3 env-unsatisfied
```

**Script-domain ownership notes:**
- `bootstrap.py` enforces startup checkpoints in order: profiler must succeed → provisioning must succeed → model acquisition must succeed → preflight must succeed → readiness summary printable. First failure stops the sequence with a clear reason. This is the canonical new-host setup path.
- `provision.py` is the **only** place that composes `pip install` invocations. Consumers never run `pip install -r requirements.txt` directly; they run `scripts/provision.py install`.
- `validate_backend.py` is the **only** place tests are run in a controlled, reported way. The pytest CLI remains available for developer loops but slice closeouts cite validator subcommand output.
- `run_jarvis.py` is explicitly developer/diagnostic scaffold. The durable surface is `desktop/` from D.2 onward. Documentation says so at the top of the script.

### Key Invariants (drift-prevention)

1. **Provisioning authority is `pyproject.toml` + `backend/app/hardware/provisioning.py`.** `backend/requirements.txt` is a derived lockfile. No hand-maintained JSON manifest registry.
2. **`backend/app/hardware/profiler.py` is the sole source of runtime/device recommendations.** No runtime file contains `if platform.system() == ...` or equivalent host-detection logic.
3. **Every voice-family runtime file accepts `device` as a constructor parameter.** Adding a new device value is a branch inside an existing runtime, never a new file.
4. **`backend/app/hardware/preflight.py` is the sole owner of DLL / backend-path bootstrap.** No runtime file touches `os.add_dll_directory` or equivalent.
5. **`backend/app/routing/runtime_selector.py` owns escalation policy for LLM and search.** Tool files and cognition files never reach past this layer.
6. **Tests are arch-aware by marker, not by directory.** `backend/tests/conftest.py` defines `skip_unless_*` helpers; directory structure reflects test purpose (unit/integration/runtime) and functional domain (voice/turn/desktop/acceleration_matrix/agents/hardware).
7. **`scripts/validate_backend.py` is the single entry to run tests in a controlled way.** Subcommands with stable exit codes.
8. **`scripts/provision.py` is the single entry to install Python dependencies.** Only place that composes `pip install -e .[...]` invocations.
9. **`scripts/bootstrap.py` enforces startup checkpoints** in fixed order (profile → provision → ensure models → preflight → readiness). First failure halts with clear reason.
10. **`scripts/run_jarvis.py` is a proving host, not a shipping path.** `desktop/` is the durable surface from D.2 onward.
11. **The QNN slot exists in extras, evidence tokens, capability flags, and runtime device enumeration from group A.** Activation in H.2 adds only inference code and a quantized model; no structural changes.
12. **Every live runtime test is marker-gated** (`pytest.mark.live`, plus family/device/arch markers). The matrix in `backend/tests/runtime/acceleration_matrix/` is the B.5 gate that must remain green before C/D/E/F/G/H/I slice closeouts.
13. **Agent roles consume existing boundaries unchanged.** Agents never reach past `runtime_selector`, `tool_registry`, `turn_service`, or the memory surfaces — they compose them.
14. **Turn artifact schema is fixed in C.3** and treated as a compatibility boundary. Later slices (G, I) may add optional fields; they never rename or remove.
15. `SYSTEM_INVENTORY.md`, `CHANGE_LOG.md`, `ProjectVision.md`, and `slices.md` are not conflated. Inventory ≠ roadmap ≠ vision ≠ changelog.

---
