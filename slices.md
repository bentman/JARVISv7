
# JARVISv7 — Slice Roadmap

> Authoritative roadmap baseline. Shapes architecture only as much as necessary to prevent drift; does not specify implementation.
> Every slice must land on the real runtime used by the product on every host class it targets before it is considered complete.
> Proven boundaries from one slice are consumed by later slices unchanged unless explicitly revoked.

## Rules

- Each slice defines: why it exists here, goal, scope, out-of-scope, method-viability assumptions, boundaries (owns / must-not-touch), key design decisions, acceptance surfaces, finish line, risks.
- Assumptions about external packages, wheels, and platform behavior are marked as assumptions. Each must be validated with explicit install + import evidence on every target host class before the sub-slice that depends on it is considered complete.
- Additive-only provisioning. Hardware-family packages enter through declarative, arch/vendor-gated extras managed by the provisioning layer. No merge semantics beyond additive.
- Hardware-authority rule: hardware-dependent runtime selection starts in the profiler. Config files define catalog / default metadata. Runtime modules execute the selected runtime, model, and device; they do not invent hardware policy locally.
- Every voice-family runtime (STT/TTS/LLM/Wake) accepts `device` as a parameter from day one. New device support is a branch inside an existing runtime, never a new runtime family.
- A slice is complete only when the highest relevant acceptance surface (unit → runtime → live → desktop live) is green on every host class the slice targets, and both the x64 and ARM64 regression suites remain green.

---

## Preferred Slice Order

```
Group A — Host Reality & Provisioning
  A.1  Hardware Profiler + Capability Flags
  A.2  Provisioning Model (base requirements + declarative hardware extras, pyproject-native)
  A.3  Readiness Rail (preflight ownership + evidence tokens)
  A.4  Arch-Aware Test Harness + Validation Script Design
  A.5  Provisioning Gate (CPU x64 + CPU ARM64 clean-install proof)
  A.6  QNN Definition (extras, tokens, device slot — no wiring)

Group B — Cross-Platform Voice Runtime Strategy
  B.1  STT Runtime Family + Device Matrix
  B.2  TTS Runtime Family + Device Matrix
  B.3  LLM Runtime Family + Escalation Surface
  B.4  Wake Runtime Family (openWakeWord primary, Porcupine optional)
  B.5  Acceleration Vetting Gate (CPU / CUDA / DirectML / QNN-slot across all 4 families)

Group C — Canonical Turn Engine
  C.1  Minimal Voice Turn
  C.2  Spoken Response + SPEAKING State
  C.3  Session Continuity + Canonical Turn Artifact
  C.4  Live Multi-Turn Spoken Continuity
  C.5  Interruption / Barge-In
  C.6  Developer Usability Surface

Group D — Durable Application Surface
  D.1  Application Shell Contract
  D.2  Durable Desktop Host (with arch-aware build/dev prerequisites)
  D.3  Resident Session Loop
  D.4  Wake Integration in Durable Host
  D.5  Personality / Presence Polish

Group E — Local Service Substrate
  E.1  Redis + SearXNG via docker-compose
  E.2  Cache Layer Wired to Redis
  E.3  Internet Search Runtime (SearXNG primary, DDGS + Tavily escalation)

Group F — Tool Foundation + ACTING Path
  F.1  Executor + ACTING State
  F.2  Tool Registry + First Tool Set
  F.3  Tool Result Rendering in Desktop + Text Shells

Group G — Cross-Session Episodic Retrieval
  G.1  Episodic Write + Retrieve
  G.2  Retrieval Injected into Prompt Assembly
  G.3  Redis-Cached Retrieval

Group H — Voice Acceleration
  H.0  Voice acceleration viability census (non-mutating; produces device/host state table)
  H.1  STT CPU baseline reconfirmation post-G
  H.2  ARM64 QNN prerequisite gate (QNN provider/HTP discovery gate only)
  H.3  ARM64 QNN STT activation (requires H.2 PASS + pre-qual: 2026-05-11-slice_h.3_pre-qual.md)
  H.4  x64 CUDA STT readiness / regression guard
  H.5  Windows DirectML voice viability gate
  H.6  DirectML STT/TTS device option activation where H.5 proved viable
  H.7  TTS acceleration viability / device slot normalization
  H.8  Voice acceleration live turn matrix

Group I — Hardware Path Normalization
  I.1  ARM acceleration sequence normalization (CPU / QNN / NPU fallback chain)
  I.2  x64 acceleration sequence normalization (CPU / CUDA / DirectML / non-NVIDIA fallback chain)
  I.3  Live mic/audio user-interaction matrix on both host classes

Group J — Runtime/Readiness UX + Degraded-State Surfacing

Group K — UI Controls + Operator Settings

Group L — Personality Policy Envelope

Group M — Realtime Conversation Session Boundary

Group N — Conversation Continuity and Session Memory Boundary

Group O — Agent Framework

Group P — Agent Framework Correction (Agent System)

Group Q — Ollama.cpp / Local LLM Runtime
```

No slice in a later group may reopen a decision owned by an earlier group without an explicit revocation note.

---

~~# Group A — Host Reality & Provisioning~~ Completed

**Why this group exists first.** Every runtime decision downstream consumes the outputs of this group. Provisioning is an application-level design concern — the set of packages a host installs is determined by detected hardware facts running through one authoritative resolver, not by developers editing a monolithic requirements file. Nothing else ships until A.1–A.5 are green on both Windows x64 and Windows ARM64 hosts.

## A.1 — Hardware Profiler + Capability Flags

**Why here.** Hardware profiling is the first callable capability. Detection is the root input for every later runtime-selection decision; placing it first eliminates the "every subsystem invents its own environment checks" failure mode.

**Goal.** One callable `run_profiler()` returns a normalized `HardwareProfile` + `CapabilityFlags` pair that every downstream subsystem consumes.

**Scope.**
- Detection targets: OS, arch (`amd64` / `arm64`), CPU model + feature flags, total/available memory, GPU presence, GPU vendor (NVIDIA / AMD / Intel / Qualcomm / other), CUDA availability + version band, NPU presence + vendor (Qualcomm / Intel / AMD / other), desktop vs laptop classification where practical.
- Output: `FullCapabilityReport(profile: HardwareProfile, flags: CapabilityFlags)`. Flags include `supports_local_llm`, `supports_gpu_llm`, `supports_cuda_llm`, `supports_local_stt`, `supports_local_tts`, `supports_wake_word`, `supports_realtime_voice`, `supports_desktop_shell`, `requires_degraded_mode`, `qnn_available`, `directml_candidate`.
- One detector module per fact category so failures are isolated and each detector is independently unit-testable.
- Profiler emits the same schema across host classes; absent facts are represented with explicit "unknown"/"unavailable" values rather than omission.

**Out of scope.** Provisioning (A.2), DLL bootstrap / preflight (A.3), runtime selection (B), model loads.

**Boundaries.**
- Owns: `backend/app/hardware/profiler.py`, `backend/app/hardware/detectors/**`, `backend/app/core/capabilities.py`.
- Must not touch: config, runtimes, services.

**Key design decisions.**
- Profiler never imports optional hardware-family packages (`onnxruntime`, `torch`, etc.) — detection is stdlib + `psutil`/platform-level only, so the profiler itself runs on a clean base install.
- NPU vendor detection must distinguish Qualcomm (QNN target), Intel (DirectML/OpenVINO target), AMD (ROCm target), and unknown; the profiler never guesses vendor from OS alone.
- Desktop vs laptop classification is best-effort; downstream code treats it as a hint, not a hard constraint.

**Acceptance.**
- Unit: each detector tested against representative synthetic hosts.
- Runtime live: `run_profiler()` executes cleanly and prints a populated report on Windows x64 and Windows ARM64.

**Finish line.** Both host classes emit a populated `FullCapabilityReport` with no errors and no `None`/unknown values in required fields.

**Risks.**
- Qualcomm NPU detection on Windows ARM64 may require WMI / registry probing rather than CPU feature flags; fall back to device-enumeration methods rather than guessing.
- CPU detector must report `arm64` on Windows ARM64 even when Python reports `platform.machine() == 'ARM64'` (caps) vs `'aarch64'` on Linux; normalize at detector boundary.

---

## A.2 — Provisioning Model

**Why here.** The set of packages a host installs is an application-level decision that belongs in the application's declarative configuration, not in a hand-maintained `requirements.txt`. This slice treats provisioning as a first-class, enforceable contract between the profiler and `pip`.

**Goal.** The profiler alone determines what gets installed. Adding a new hardware family is one extra in `pyproject.toml` plus one branch in the resolver — nothing else changes.

**Scope.**
- `pyproject.toml` is the single source of truth (PEP 621). `[project].dependencies` holds the universal base; `[project.optional-dependencies]` holds one extra per hardware family and one `dev` extra.
- Base dependencies: packages that install cleanly on Windows x64, Windows ARM64, Linux x64, Linux ARM64 simultaneously. No ML/runtime-specific packages.
- Hardware extras (canonical names reserved here; package contents finalized per family in B):
  - `hw-cpu-base` — intentionally empty; CPU-only hosts get the base.
  - `hw-x64-base` — PEP 508 markers `platform_machine in 'AMD64 x86_64'`; x64 acceleration family defaults.
  - `hw-arm64-base` — PEP 508 markers `platform_machine in 'ARM64 aarch64'`; ARM64 ONNX runtime family.
  - `hw-gpu-nvidia-cuda` — CUDA EP family (NVIDIA + CUDA detection).
  - `hw-gpu-amd` — DirectML/ROCm family (wired in H.3).
  - `hw-gpu-intel` — DirectML family.
  - `hw-npu-qualcomm-qnn` — `onnxruntime-qnn` family (defined in A.6, wired in H.2).
  - `hw-wake-porcupine` — optional; `pvporcupine` alternative wake runtime (B.4).
  - `dev` — tooling (pytest, ruff, mypy, pre-commit).
- Resolver: `backend/app/hardware/provisioning.py::resolve_required_extras(profile) -> list[str]` is the only place that translates hardware facts to extras. Returns an ordered, additive list. Handles vendor gating that PEP 508 markers cannot express (CUDA availability, NPU vendor).
- Provisioning script (see A.4 for script-design convention) composes `pip install -e '.[base,hw-*,dev]'` from resolver output. Supports dry-run, verify-against-installed, and locked-lockfile emission for reproducibility.
- `backend/requirements.txt` is a generated platform-neutral lockfile of the base extra only, for CI consumers. Top-of-file comment identifies it as generated.

**Out of scope.** QNN extra population (A.6 defines, H.2 activates). Model catalog (B). Runtime selection (B).

**Assumptions.**
- PEP 508 environment markers `platform_machine` and `sys_platform` are sufficient to gate arch-detectable extras.
- `onnxruntime` publishes `win_arm64` wheels for CPython 3.11–3.14 (PyPI 1.24.4 listing confirms).
- `onnxruntime-qnn>=2.0.0` publishes `win_arm64` wheels for CPython 3.11/3.12/3.13 (PyPI 2.0.0 listing confirms).
- `pip install -e '.[extra1,extra2]'` composes extras correctly across modern `pip` versions.

**Boundaries.**
- Owns: `pyproject.toml`, `backend/app/hardware/provisioning.py`, the provisioning script.
- Must not touch: runtimes, services, desktop.

**Key design decisions.**
- Extras are the Python ecosystem's native declarative mechanism for optional dependency sets with environment markers (PEP 508 / PEP 621). Hand-rolled JSON manifest registries are rejected because they duplicate existing infrastructure and add merge semantics to maintain.
- Resolver returns extras in a deterministic, documented order so install output is reproducible across invocations.
- Resolver output is serializable and logged with every provisioning invocation (included in host-fingerprint output — see A.4).
- Operator never edits `backend/requirements.txt` by hand; if it's out of date it's regenerated from `pyproject.toml`.

**Acceptance.**
- Unit: `resolve_required_extras()` returns correct extras for synthetic profiles covering every host class.
- Live: provisioning dry-run on x64 and ARM64 hosts prints correct extras; clean-venv install succeeds on both.

**Finish line.** A new host runs one provisioning command and ends up with exactly the packages its hardware needs, derived from profiler output alone.

**Risks.**
- Environment markers vary subtly across `pip` versions; freeze supported `pip` version in `dev` extra and test against it.
- `pyproject.toml` extras install order is not strictly guaranteed; the resolver ordering exists for logging/debugging, not for install correctness.
- NPU vendor gating cannot use PEP 508 markers; the resolver must make the call. Document this split clearly so maintainers do not move it into markers.

---

## A.3 — Readiness Rail

**Why here.** Correct extras installed does not imply usable inference. DLLs must load, execution providers must register, quantized artifacts must be discoverable. This is the evidence-based layer every runtime selector in B consumes.

**Goal.** Each voice family (STT/TTS/LLM/Wake) has a clear, evidence-backed readiness claim per device on every host class.

**Scope.**
- `backend/app/hardware/preflight.py` owns:
  - DLL / backend-path bootstrap. On Windows CUDA hosts this covers cuDNN / cuBLAS discovery. On Qualcomm hosts this covers QAIRT backend `.dll` discovery (via env var). No runtime file touches `os.add_dll_directory`.
  - Import probes against installed extras. Each probe produces an evidence token (`import:onnxruntime`, `import:onnxruntime-qnn`, `import:kokoro_onnx`, etc.).
  - EP registration probes (`ep:CUDAExecutionProvider`, `ep:DmlExecutionProvider`, `ep:QNNExecutionProvider`).
  - Optional session-creation probes for deep readiness (used sparingly because they can load model weights).
- `backend/app/hardware/profiler.py::resolve_backend_evidence_tokens(family, active_extras)` translates the token set into per-family readiness claims.
- `derive_{stt,tts,llm,wake}_device_readiness(preflight)` returns `(selected_device, selected_device_ready, reason)` tuples consumed by runtime selectors.
- Readiness report structure is stable and documented — it is also the payload of the startup-summary API endpoint (D.1).

**Out of scope.** Running actual inference (B). Model acquisition (B). QAIRT SDK installation (operator prerequisite, documented in `.env.example` and `config/hardware/notes.md`).

**Boundaries.**
- Owns: `preflight.py`, `resolve_backend_evidence_tokens()`, `derive_*_device_readiness()`.
- Must not touch: concrete runtime files, catalog, services.

**Key design decisions.**
- Evidence tokens are strings, not booleans. They describe *what was probed and what result came back*, so a reasoning trace can be reconstructed without rerunning probes.
- Fail-closed semantics: if any required token is missing, the device is not `ready`, and the reason string names the missing token.
- DLL bootstrap is idempotent and repeatable — multiple callers in one process must produce the same result without re-running the costly parts.
- Session-creation probes (if needed for deep readiness) are opt-in per probe and never run as part of the default readiness call, to keep startup fast.

**Acceptance.**
- Unit: synthetic token sets produce expected readiness claims for every host class.
- Live: both host classes emit complete per-family readiness with evidence-traceable reasons.

**Finish line.** Every host class answers the question "can I transcribe / synthesize / chat / wake on device X right now?" with an evidence-backed yes/no and a reason.

**Risks.**
- CUDA DLL discovery on Windows is sensitive to PATH ordering; the bootstrap must document precedence rules explicitly.
- QAIRT backend DLL discovery on Qualcomm may differ by SDK version; accept an operator-supplied absolute path via env var rather than guessing.

---

## A.4 — Arch-Aware Test Harness + Validation Script Design

**Why here.** Tests and validation must be first-class citizens of the architecture, not added after the fact. Before any provisioning gate closes or runtime work begins, the harness must be arch-aware by design so every later slice can write tests that run where they make sense and skip cleanly where they don't.

**Goal.** One marker-driven test harness plus one subcommand-driven validation entry point serve every later slice's testing needs without further redesign.

**Scope.**

**Pytest markers registered in `pyproject.toml` under `[tool.pytest.ini_options].markers`:**
- Arch: `x64`, `arm64`.
- Device readiness: `cuda`, `directml`, `qnn`.
- Surface: `live` (requires mic / speaker / live hardware), `slow` (>5s).
- External service: `requires_ollama`, `requires_redis`, `requires_searxng`, `requires_docker`, `requires_qairt`.
- Family: `stt`, `tts`, `llm`, `wake`, `turn`, `desktop`, `agents`.

**`backend/tests/conftest.py`** exposes `skip_unless_*` reusable `pytest.mark.skipif` constants (`skip_unless_x64`, `skip_unless_arm64`, `skip_unless_cuda`, `skip_unless_directml`, `skip_unless_qnn`, `skip_unless_ollama`, etc.) that read from the profiler + preflight, so tests declare their requirements and the harness decides skip/run per host.

**Directory layout reflects test purpose, not host class:**
```
backend/tests/
├─ conftest.py
├─ fixtures/
├─ unit/                   # fast, no hardware, no network
├─ integration/            # multi-module, no live hardware
└─ runtime/                # live hardware
   ├─ acceleration_matrix/ # B.5 gate
   ├─ agents/
   ├─ desktop/
   ├─ hardware/
   ├─ turn/
   └─ voice/
```

**`scripts/validate_backend.py` redesign** — subcommand-based:
- `profile` — run profiler + preflight; print the current host's capability report.
- `unit` — unit suite.
- `integration` — integration suite.
- `runtime [--families STT,TTS,... --devices cpu,cuda,...]` — live runtime suite, marker-filtered.
- `regression` — minimum green-on-current-host set that every slice closeout must pass.
- `matrix` — the B.5 acceleration matrix.
- `all` — unit + integration + regression.
- `ci` — suppresses `live` markers automatically, treats missing hardware as skipped-ok.

Every subcommand starts with a **host-fingerprint line** as the first stdout: arch, Python version, active extras, readiness summary. This makes every log self-identifying.

**Stable documented exit codes:** 0 pass, 1 fail, 2 skipped-but-not-failed, 3 environment-unsatisfied.

**Shared script CLI convention** applied to every script in `scripts/` (not only validator): `--verbose`, `--dry-run`, `--trace-to <dir>`, `--profile` (emit the fingerprint line). Scripts never re-implement profiler / preflight / provisioning logic — they import from `backend/app/**`.

**Regression composition:** per-slice closeout declares its "must-remain-green on x64" and "must-remain-green on ARM64" subsets. The regression subcommand runs the union on the current host, skipping arch-mismatched entries with a clear reason.

**Out of scope.** Writing the actual tests for later slices (each slice writes its own against this harness). CI platform integration (documented, not implemented).

**Boundaries.**
- Owns: `backend/tests/conftest.py`, `pyproject.toml` pytest markers, `scripts/validate_backend.py`, `backend/tests/fixtures/`.
- Must not touch: application code outside test discovery.

**Key design decisions.**
- Markers + `skipif` rather than directory split: avoids duplicating shared setup, keeps one test per behavior, makes "runs on both archs" the easy case.
- Validator is a thin orchestrator over pytest; it never contains test logic of its own.
- Host-fingerprint first line is enforced by every script as a harness convention, not just the validator.

**Acceptance.**
- Live on both host classes: `validate_backend profile` prints the correct report; `validate_backend unit` runs clean; `validate_backend runtime` correctly skips arch-mismatched tests with reason strings.

**Finish line.** Every later slice can write tests tagged for the correct host class / device / family, and the validator skips cleanly where they don't apply and runs cleanly where they do.

**Risks.**
- Marker proliferation: cap the list in `pyproject.toml` and require every new marker to be added there with a docstring, so the marker set stays comprehensible.
- `skip_unless_cuda` etc. depend on preflight running at session start; ensure `conftest.py` caches preflight result per test session.

---

## A.5 — Provisioning Gate

**Why here.** Before any voice runtime work begins, the provisioning + readiness + test-harness contract must prove out end-to-end on both baseline host classes. This is a hard gate — runtime work does not start until this closes.

**Goal.** A clean host of each supported baseline class can go from empty venv to green regression suite via a documented command sequence, with no manual intervention and no hand-edited requirements files.

**Scope.**
- On a clean Windows x64 host: provisioning → profile → preflight → regression all pass.
- On a clean Windows ARM64 host: same sequence passes.
- Linux x64 / Linux ARM64 validated at best-effort if host available; not blocking for closeout.
- `SYSTEM_INVENTORY.md` records the blocking gate entry: "Provisioning Baseline Verified (Windows x64 + Windows ARM64)".
- Documented operator sequence in `README.md`: clone → `python -m venv .venv` → activate → `scripts/provision.py` → `scripts/validate_backend.py regression`.

**Out of scope.** Any runtime code (B).

**Boundaries.**
- Owns: provisioning-baseline live tests under `backend/tests/runtime/hardware/`.
- Must not touch: anything added by B or later.

**Acceptance.** Documented sequence green on both Windows host classes from a fresh-clone state.

**Finish line.** No runtime code in B may start until this gate is green on both Windows host classes.

**Risks.**
- A Python point-release change between baseline validation and first B slice may invalidate extras; `.python-version` + `requires-python` range bounds this.

---

## A.6 — QNN Definition

**Why here.** Carry QNN as a first-class definition from day one so activation is pure hardware acceleration boundary wiring. Defining it here forces every runtime family in B to treat `qnn` as one of the device values it must accept.

**Goal.** Activating QNN at the hardware acceleration boundary requires no manifest / extra / flag / token / schema changes — only runtime code and a quantized model.

**Scope.**
- `hw-npu-qualcomm-qnn` extra in `pyproject.toml`, applied by the resolver on Qualcomm NPU hosts.
- Packages: `onnxruntime-qnn>=2.0.0` (PyPI Windows ARM64 wheels confirmed for CPython 3.11/3.12/3.13).
- Evidence tokens added to `resolve_backend_evidence_tokens()`: `import:onnxruntime-qnn`, `ep:QNNExecutionProvider`, `dll:QnnHtp` — all returning "defined but not wired" until hardware acceleration validation proves activation.
- `CapabilityFlags.qnn_available` set from NPU vendor detection.
- `qnn` accepted as a valid `selected_device` value in STT readiness; selector emits a clear "defined, inference not wired" reason and refuses to select it for actual work without hardware acceleration validation.
- Operator prerequisites documented in `.env.example` and `config/hardware/notes.md`: QAIRT SDK install path, backend `.dll` location.

**Out of scope.** Inference code. Quantized model catalog entries (placeholder only). The hardware acceleration boundary owns activation and validation.

**Boundaries.**
- Owns: the extra entry, token definitions, the `qnn_available` flag, documentation.
- Must not touch: runtime implementations.

**Key design decisions.**
- Define the slot, not the implementation — prevents the "QNN as retrofit" failure mode without blocking on SDK availability or hardware access.
- Quantization tooling notes included in `config/hardware/notes.md`: per ORT QNN docs the `onnx` package has ARM64 install issues, so quantization runs on x64; this is documented as an operator workflow, not a blocker here.

**Acceptance.** Unit tests confirm Qualcomm host synthetic profiles produce the expected "defined but not wired" readiness claims.

**Finish line.** QNN is present in the architecture as a slot every hardware acceleration decision is aware of.

**Risks.**
- `onnxruntime-qnn` versioning may diverge from core `onnxruntime`; pin compatible ranges explicitly.

---

~~# Group B — Cross-Platform Voice Runtime Strategy~~ Completed

**Why this group exists here.** Runtime family choice is an application-level decision made once, up front, for all supported hardware. Every family treats `device` as a parameter. Acceleration is exercised within this group so no GPU/NPU support needs retrofitting later.

## B.1 — STT Runtime Family + Device Matrix

**Why here.** STT is the first voice-critical runtime and the one most exposed to hardware variation. One runtime family that accepts all required device values eliminates the dual-stack maintenance surface.

**Goal.** The STT family transcribes a known utterance on every supported device on the current host, with device selection driven by readiness tokens.

**Scope.**
- Primary runtime: ONNX-based Whisper via `onnxruntime`. Single runtime file accepting `device ∈ {cpu, cuda, directml, qnn}`. Device branches live inside the runtime; `cpu` works on every host, GPU/NPU branches check readiness.
- Secondary runtime: `onnx-asr` (`istupakov/onnx-asr`). Supports Windows/Linux/macOS on x86/Arm CPUs with CUDA/TensorRT/CoreML/DirectML/ROCm/WebGPU backends per its PyPI listing. Kept behind a runtime flag for non-Whisper model families (Parakeet/Canary/NeMo), lower-latency streaming scenarios, and non-English coverage owned by the voice interaction boundary.
- Selector in `backend/app/runtimes/stt/stt_runtime.py` dispatches on `(runtime_family, device)` from profiler/readiness output.
- Catalog entries in `config/models/stt.yaml`:
  - `whisper-small-onnx` (CPU/CUDA/DirectML).
  - `whisper-small-onnx-qnn-qdq` (placeholder; artifact acquired in H.2).
  - One Parakeet-family ONNX model for the `onnx-asr` path.
- Cache keying is `(runtime_family, model_name, device)` so runtimes never collide in cache.

**Out of scope.** QNN inference and QNN-target quantization tooling belong to the hardware acceleration boundary. Streaming partial transcripts belong to the streaming response boundary.

**Assumptions.**
- ONNX Whisper `small` is available on HuggingFace in a layout compatible with `onnxruntime`.
- `onnx-asr` installs cleanly on both x64 and ARM64 with its stated dependency bounds.
- `onnxruntime-directml` wheels available for target CPython versions on Windows GPU hosts.

**Boundaries.**
- Owns: `backend/app/runtimes/stt/{base.py, onnx_whisper_runtime.py, onnx_asr_runtime.py, stt_runtime.py, barge_in.py}`, `config/models/stt.yaml`.
- Must not touch: TTS, LLM, wake, services.

**Key design decisions.**
- One ONNX Whisper runtime file holds all device branches; `faster-whisper` is not included in the base strategy. The local STT runtime boundary owns any second-runtime decision if ONNX coverage proves insufficient for a specific need.
- Selector refuses to pick an unready device with a clear reason rather than falling through silently.
- `onnx-asr` is present from day one because defining its slot up front keeps the runtime boundary stable.

**Acceptance.**
- Unit: runtime + selector dispatch table.
- Runtime live: CPU transcription on every host; CUDA on NVIDIA host; DirectML on GPU host; QNN marker-skipped with reason until H.2.

**Finish line.** Transcription works on every `(host_class × supported_device)` combination; `qnn` slot exists and refuses cleanly.

**Risks.**
- ONNX Whisper model file layouts vary between HF uploads; catalog entries pin exact repo IDs + expected file set.
- DirectML EP behavior varies between `onnxruntime-directml` package versions; pin range in `hw-gpu-amd` / `hw-gpu-intel` extras.

---

## B.2 — TTS Runtime Family + Device Matrix

**Why here.** Same cross-platform logic as B.1. One family, device as parameter.

**Goal.** A known text synthesizes to audio on every supported device on the current host.

**Scope.**
- Primary runtime: Kokoro via `kokoro-onnx` (`onnxruntime`-backed, pure-Python wheel). Accepts `device ∈ {cpu, cuda, directml}`.
- Catalog entry: `kokoro-v1.0-onnx` in `config/models/tts.yaml`. Model file pair (`kokoro-v1.0.onnx` + `voices-v1.0.bin`) handled by the catalog's file-pair pattern.
- Selector in `backend/app/runtimes/tts/tts_runtime.py` dispatches on `(runtime_family, device)`.
- Blocking and interruptible playback utilities under `backend/app/runtimes/tts/playback.py`; consumed by voice service (C.2) and barge-in (C.5).
- Response sanitation at responder boundary (`backend/app/cognition/responder.py`) before text reaches TTS, to strip control characters / unspeakable content.

**Out of scope.** QNN TTS (no publicly verified Kokoro QNN quantization exists). Voice cloning. Non-English beyond the chosen Kokoro voice pack.

**Assumptions.**
- `kokoro-onnx` is a pure-Python wheel installable on both x64 and ARM64.
- `espeak-ng` (or equivalent phonemizer) is an operator prerequisite if the ONNX pipeline requires it; documented in `config/hardware/notes.md`.
- HuggingFace offline mode works with the acquisition/ensure pattern (`HF_HUB_OFFLINE=0` for acquisition, `=1` for runtime).

**Boundaries.**
- Owns: `backend/app/runtimes/tts/{base.py, kokoro_onnx_runtime.py, tts_runtime.py, playback.py}`, `config/models/tts.yaml`.

**Key design decisions.**
- PyTorch-based Kokoro is not default (x64-only path). The voice interaction boundary owns any second-runtime decision on x64 if a concrete need appears, but single-stack is the goal.
- Playback utilities live in runtime layer, not in services, so interruption logic (C.5) has one interruption point.

**Acceptance.**
- Unit: runtime + selector dispatch.
- Runtime live: synthesis on every supported device on the host; TTS-unavailable degraded mode emits text only with recorded degradation.

**Finish line.** Audio out on every `(host_class × supported_device)` combination; graceful degradation when TTS runtime is absent.

**Risks.**
- `espeak-ng` phonemizer dependency on Windows ARM64 may require a specific install; document fully in `config/hardware/notes.md`.

---

## B.3 — LLM Runtime Family + Escalation Surface

**Why here.** LLM is the last voice-critical runtime. Defining the interface here — even with only Ollama live initially — ensures the turn engine in C consumes one LLM interface, and local-`llama.cpp` activation in H.1 is a pure substitution rather than new architecture.

**Goal.** One stable LLM interface consumed by cognition. Local paths preferred, cloud escalation policy-gated.

**Scope.**
- Interface: `backend/app/runtimes/llm/base.py`.
- Local runtimes:
  - `local_runtime.py` — `LlamaCppLLM`. `is_available()` gating; `generate()` raises `NotImplementedError` until H.1.
  - `ollama_runtime.py` — live local path at HTTP endpoint.
- Cloud escalation runtimes (each in its own file, explicit policy surface): `claude_runtime.py`, `openai_runtime.py`, `gemini_runtime.py`, `xai_runtime.py`, `zai_runtime.py`.
- Selector in `backend/app/routing/runtime_selector.py` prefers local chain (llama.cpp → Ollama) then escalates per policy. Policies live in `config/app/policies.yaml`.
- Readiness extension: `llm_local_ready`, `llm_selected_runtime` fields in `BackendReadiness`. Initially reflects Ollama availability.
- Personality profile is an input to prompt assembly via `backend/app/personality/adapter.py`; personality never bypasses policy.

**Out of scope.** Activating local llama.cpp inference (H.1). Agent orchestration (I).

**Assumptions.** Ollama reachable at the documented HTTP endpoint.

**Boundaries.**
- Owns: `backend/app/runtimes/llm/**`, LLM-specific portion of `runtime_selector.py`, LLM readiness fields.

**Key design decisions.**
- Cloud runtimes exist as files from day one even if gated off. This keeps the escalation architecture explicit and prevents "add a provider" from becoming a new decision each time.
- Policy is config-driven, not code-branched. Enabling a cloud provider is a policy edit, not a code change.
- Selector emits the chosen runtime + reason into the readiness summary so the desktop shell can display it (D.2).

**Acceptance.**
- Unit: selector dispatch; cloud runtimes with stubbed HTTP layers.
- Runtime live: known prompt returns valid response via Ollama.

**Finish line.** LLM interface stable; Ollama live; local llama.cpp slot dormant; cloud slots defined but policy-gated off.

**Risks.**
- Ollama API contract changes between versions; pin client version and document expected Ollama server version range.

---

## B.4 — Wake Runtime Family (openWakeWord primary, Porcupine optional)

**Why here.** Wake word is hardware-adjacent (microphone handling + real-time detection). Deciding the strategy before the durable shell prevents "wake word bolted on at the end."

**Why openWakeWord is primary.** openWakeWord ships a pre-trained `hey_jarvis` model (~200k synthetic clips). Model files are `.onnx` or `.tflite` — architecture-independent, so one file runs on both Windows x64 and Windows ARM64. Clean operational default across host classes.

**Goal.** A user on either host class gets working wake-phrase detection from a clean install with zero custom-training work.

**Scope.**
- Interface: `backend/app/runtimes/wake/base.py`.
- **Primary runtime**: openWakeWord via `onnxruntime`. Per project README, Windows installs use `onnxruntime` as `tflite-runtime` wheels are not available on Windows. Catalog entries in `config/models/wake.yaml` point at openWakeWord v0.5.1 release URLs for `hey_jarvis_v0.1.onnx`, `melspectrogram.onnx`, `embedding_model.onnx`.
- **Optional runtime**: Porcupine via `pvporcupine`. Installed via `hw-wake-porcupine` extra — not part of default install. Built-in "jarvis" keyword usable via `keywords=['jarvis']` without any `.ppn` file.
  - Reserved config slots: `wake.yaml` carries a `provider: openwakeword | porcupine` field and a `porcupine_keyword_path` slot even when unused.
  - Future-custom-keyword caveat documented: Picovoice Console selects platform at training time; whether a single Windows `.ppn` covers both x64 and ARM64 at Console level is not definitively documented, so custom-keyword work should validate with Picovoice support and plan for per-arch files if needed. Dev-tier AccessKey allows one keyword at a time.
- Wake selector dispatches on `provider` config value; openWakeWord default.
- Custom "jarvis"-only training (no "hey" prefix) is not implemented. The voice interaction boundary owns custom wake-word training; it remains a Linux/WSL/Colab operator task per openWakeWord's notebook ("automated model training is only supported on linux systems due to the requirements of the text to speech library used for synthetic sample generation (Piper)"). Trained `.onnx` output is arch-independent.

**Out of scope.** Training custom openWakeWord models. NPU-accelerated wake (wake runs on CPU for both providers).

**Assumptions.**
- openWakeWord v0.5.1 release asset URLs remain reachable.
- `pvporcupine` installs cleanly on Windows ARM64 when the optional extra is selected (validate at extra installation time).

**Boundaries.**
- Owns: `backend/app/runtimes/wake/{base.py, openwakeword_runtime.py, porcupine_runtime.py, wake_runtime.py}`, `config/models/wake.yaml`.

**Key design decisions.**
- openWakeWord default because arch-independence + pre-trained `hey_jarvis` gives the best baseline UX with no operator setup.
- Porcupine kept as an optional alternative because its dev-tier single-keyword limit doesn't fit a primary multi-keyword surface but may be right for specific deployments.
- Custom-keyword training is not implemented and is not a precondition for the current voice interaction boundary.

**Acceptance.**
- Unit: selector dispatch; runtime fail-closed when models missing.
- Runtime live: openWakeWord detects "hey jarvis" on both host classes. Porcupine runtime smoke-tested when `hw-wake-porcupine` extra is installed.

**Finish line.** Wake detection works out-of-box on both host classes via openWakeWord. Porcupine available as drop-in when the extra is installed.

**Risks.**
- openWakeWord false-reject rate in noisy environments may push users toward custom verifier models; that path is documented but not required.

---

## B.5 — Acceleration Vetting Gate

**Why here.** Before turn-engine work begins, every `(family × device × host_class)` combination the host supports must produce a known state. This is a hard gate enforced by `backend/tests/runtime/acceleration_matrix/`.

**Goal.** The matrix has a recorded state (`PASS` / `SKIP-with-reason` / `PENDING-H.x`) for every combination, on every host class.

**Scope.**
- Single end-to-end probe per family per device:
  - STT: transcribe known utterance.
  - TTS: synthesize known text.
  - LLM: known prompt → valid response via Ollama.
  - Wake: detect "hey jarvis" via openWakeWord.
- QNN is exercised as the definition-only probe — readiness emits "qnn defined, inference not available"; STT selector refuses to select `qnn` with a clear reason. That is the expected passing state.
- Matrix results recorded in `SYSTEM_INVENTORY.md` as the gate entry.

**Out of scope.** Full QNN STT (H.2). Cloud LLM live calls (still policy-gated).

**Boundaries.**
- Owns: `backend/tests/runtime/acceleration_matrix/**`.
- Must not touch: turn engine, services, desktop.

**Key design decisions.**
- Matrix is a gate, not a one-time event — C/D/E/F/G/H/I slice closeouts must keep it green.
- Every cell's result has an explicit reason string, never a silent skip.

**Acceptance.** Matrix green or PENDING-H.x on both Windows host classes.

**Finish line.** No C-group slice starts until matrix is green.

**Risks.**
- Matrix scope creep — cap cells at the four families × the four canonical devices, not every permutation possible.

---

~~# Group C — Canonical Turn Engine~~ Completed

## C.1 — Minimal Voice Turn

**Why here.** With A + B complete, every runtime is addressable through one interface. The turn engine consumes those interfaces and only those interfaces.

**Goal.** One spoken utterance returns a text response in the real runtime.

**Scope.**
- Turn pipeline: STT → prompt assembly (personality profile input) → LLM via B.3 selector → responder → visible text response.
- Text input enters the same turn executor as a secondary ingress; no separate chat architecture.
- Canonical conversation states stubbed: `BOOTSTRAP`, `PROFILING`, `IDLE`, `LISTENING`, `TRANSCRIBING`, `REASONING`, `ACTING`, `RESPONDING`, `SPEAKING`, `INTERRUPTED`, `RECOVERING`, `FAILED`. Only `IDLE → LISTENING → TRANSCRIBING → REASONING → RESPONDING → IDLE/FAILED` land live in this slice; others are pending their respective slices.
- One-turn orchestration deterministic: control flow is explicit in `conversation/engine.py`, not in prompt content.

**Out of scope.** Spoken output (C.2). Multi-turn (C.3). Interruption (C.5). ACTING/tools (F).

**Boundaries.**
- Owns: `backend/app/conversation/{engine,states,turn_manager}.py`, `backend/app/cognition/{prompt_assembler,responder}.py`, `backend/app/services/{turn_service,voice_service,task_service}.py`.

**Key design decisions.**
- Personality profile is a prompt-assembly input, not a prompt fragment — explicit, inspectable, policy-bounded.
- Both voice and text turns go through `turn_service.py` so they cannot diverge.

**Acceptance.** Unit + runtime live: one spoken utterance returns a text response on both host classes.

**Finish line.** Base turn lifecycle proven on live hardware.

---

## C.2 — Spoken Response + SPEAKING State

**Goal.** Voice turn returns spoken audio on every supported device.

**Scope.**
- `SPEAKING` state on live path. TTS output flows through `voice_service.py` via `backend/app/runtimes/tts/playback.py`.
- Degraded mode: if TTS selector returns unavailable, turn returns text and records degradation in the turn artifact (turn artifact itself lands in C.3).
- Responder-boundary sanitation applied before text reaches TTS.

**Out of scope.** Interruption logic (C.5).

**Acceptance.** Runtime live: voice turn returns spoken audio on every supported device. Degraded-mode path returns text cleanly when TTS is unavailable.

**Risks.**
- Audio device selection on Windows can be surprising; log the selected device explicitly.

---

## C.3 — Session Continuity + Canonical Turn Artifact

**Why here.** Before multi-turn (C.4) lands, artifact and memory shape must be fixed. Retrofitting artifact fields later breaks every already-written turn.

**Goal.** Two turns in one session produce deterministic, inspectable artifacts and bounded working-memory continuity.

**Scope.**
- Session manager owns session lifecycle and the `session_id` that threads through artifacts.
- Canonical turn artifact captures (per `ProjectVision.md` field list): turn id, session id, input modality, hardware profile snapshot, capability flags, active personality profile, raw audio refs, transcript, final prompt text, retrieved memory refs, tools invoked, reasoning/execution trace metadata, response text, audio output refs, interruption events, final state, failure reason, phase timestamps.
- Bounded working memory (`memory/working.py`) with explicit write policy (`memory/write_policy.py`).
- Artifact storage in `data/turns/` and `data/sessions/`; storage helpers in `backend/app/artifacts/`.
- Transcript-bound continuity executor shared by voice and text paths — session `N` reads session `N-1`'s relevant turn artifacts for context when the write policy permits.

**Out of scope.** Cross-session episodic retrieval (G). Interruption artifact fields populated from real interruptions (C.5).

**Boundaries.**
- Owns: `backend/app/conversation/session_manager.py`, `backend/app/artifacts/**`, `backend/app/memory/{working,write_policy}.py`, `backend/app/services/turn_service.py` continuity surface.

**Key design decisions.**
- Artifact schema is fixed in this slice and treated as a compatibility boundary — later slices may add fields but not rename or remove.
- Memory write policy is explicit, auditable config in `write_policy.py`, not implicit logic in the turn engine.

**Acceptance.** Unit + runtime live: two turns in one session, artifacts written, working memory bounded, clean session closure.

**Finish line.** Session + artifact shape stable enough to build on.

---

## C.4 — Live Multi-Turn Spoken Continuity

**Goal.** Two or more spoken turns in one session, live, with turn N consuming turn N-1's context.

**Scope.**
- Continuity executor exercises the C.3 artifact/memory surface across real voice turns.
- No new orchestration primitives — this is an acceptance slice proving C.3's foundation works under realistic load.

**Acceptance.** Runtime live: two-turn spoken session completes with turn 2 referencing turn 1 context.

**Risks.** Microphone/device state across turns on Windows — verify explicitly, don't assume clean carryover.

---

## C.5 — Interruption / Barge-In

**Goal.** User can interrupt the assistant mid-response; session continues coherently.

**Scope.**
- Barge-in detector (`runtimes/stt/barge_in.py`) runs during SPEAKING.
- State transitions on interruption: `SPEAKING → INTERRUPTED → RECOVERING → next_valid_state` per `ProjectVision.md` interruption policy.
- Interruption events recorded in turn artifact with timing + recovery state.
- Policy: speech output is interruptible at nearest safe boundary; listening has priority once barge-in is accepted; unsupported-interruption modes degrade to stop-and-reinvoke with explicit surfacing.
- Initial acceptable behavior: user interrupts → speech stops → system records → clean transition to next allowed state without corrupting session. Perfect conversational overlap not required.

**Out of scope.** Wake-during-speech belongs to the realtime conversation/session boundary.

**Acceptance.** Runtime live: interruption during SPEAKING produces clean state transitions and a turn artifact recording the event.

**Risks.**
- Barge-in false-positives during assistant's own audio output (feedback loop); document the test-scope suppression pattern if needed for live tests on specific hardware.

---

## C.6 — Developer Usability Surface

**Why here.** The proving-host period is where regressions are caught. Honest failure visibility is a debugging investment that pays across every later slice.

**Goal.** Every failure mode prints a clear reason. No empty results, no context-less tracebacks.

**Scope.**
- `scripts/run_jarvis.py` proving host. Flags: `--turns`, `--voice-only`, `--text-only`, `--verbose`, `--trace-to`, `--dry-run`, `--profile`, `--policy-override` (for named policy tests).
- Readable startup summary printed at boot: selected runtime family, device, model per voice family; reason each was selected; active personality.
- Named, explicit failure states when any family unavailable (profiler unavailable, STT unavailable, TTS unavailable, model missing, provider import failure, wake unavailable).
- `--verbose` streams state transitions to stdout.
- Trace artifacts to `reports/diagnostics/<timestamp>/` with predictable path printed at startup.
- Shared CLI convention (from A.4) applied: every script emits host-fingerprint as first line; every script accepts `--verbose` / `--dry-run` / `--trace-to`.
- Logging configuration in `backend/app/core/logging.py` consumed by all scripts and the backend.

**Out of scope.** The durable desktop shell (D).

**Boundaries.**
- Owns: `scripts/run_jarvis.py`, `backend/app/core/logging.py`.

**Key design decisions.**
- Proving host is explicit diagnostic/developer tool — never the shipping path. `desktop/` (D.2) is the durable surface.

**Acceptance.** Manual: new developer clones, provisions, runs `scripts/run_jarvis.py --turns 1 --verbose`, and understands exactly what happened and why.

**Finish line.** Proving-host ergonomics good enough that later-slice debugging doesn't require re-architecting the script each time.

---

~~# Group D — Durable Application Surface~~ Completed

## D.1 — Application Shell Contract

**Why here.** Before any Tauri code, the shell's contract with the backend must be explicit — what backend exposes, what shell consumes, what shell never owns.

**Goal.** A headless HTTP client can drive the full application contract without any shell involvement.

**Scope.**
- Backend API routes (`backend/app/api/routes/`): `health`, `readiness`, `session`, `task`, `voice`, `diagnostics`, `agents` (read-only, for I).
- Readiness endpoint emits structured startup summary: per-family runtime + device + model + readiness claim + reason; active personality; active LLM; degraded-mode indicators.
- Session lifecycle operations exposed as explicit verbs (create, tick, close) rather than implicit state transitions.
- Shell-facing contract: shell never contains orchestration logic, runtime selection, or model acquisition.
- Request/response schemas fixed in `backend/app/api/schemas/` — treated as compatibility boundary with desktop shell.

**Out of scope.** Desktop-specific code (D.2).

**Boundaries.**
- Owns: API routes + schemas.

**Acceptance.** Unit tests for every route; headless client drives full contract.

**Finish line.** Shell contract fixed enough that D.2 can be written against it without surprise.

---

## D.2 — Durable Desktop Host

**Why here.** The shell lands on the durable surface once, consuming D.1's API contract.

**Goal.** A user on either Windows host class launches JARVISv7 as a native desktop application and completes a voice turn.

**Dev/build prerequisites by host arch** (documented in `README.md` + `desktop/README.md`):
- **Windows x64 dev**: Rust stable, Node LTS, MSVC v143 build tools, WebView2 runtime.
- **Windows ARM64 dev**: Rust stable + `rustup target add aarch64-pc-windows-msvc`, Node LTS (ARM64 where available), **MSVC v143 — VS 2022 C++ ARM64 build tools** per Tauri's Windows installer docs. NSIS installer runs via emulation on ARM; bundled app is native ARM64.
- Cross-compile x64 → ARM64 is a documented escape hatch but not the primary dev path.

**Scope.**
- Native desktop application under `desktop/` using Tauri 2.x.
- System tray with named visible states: Starting, Ready, Listening, Transcribing, Thinking, Speaking, Interrupted, Degraded, Failed.
- Conversation display, hotkey / PTT invocation, start/stop/running lifecycle.
- **Visible hardware selection**: component displays active runtime family + device for each of STT/TTS/LLM/Wake, pulled from D.1 readiness endpoint.
- **Visible LLM selection**: component shows current LLM runtime and offers policy-gated switch (local llama.cpp / Ollama / approved cloud).
- Shell is a thin adapter; all orchestration backend-owned.

**Out of scope.** Resident session loop (D.3). Wake integration (D.4).

**Assumptions.**
- Tauri 2.x supports Windows ARM64 with the noted toolchain (confirmed by Tauri docs).
- WebView2 runtime present or bootstrappable on both host classes.

**Boundaries.**
- Owns: `desktop/src-tauri/**`, `desktop/src/**`.

**Key design decisions.**
- `scripts/run_jarvis.py` is explicitly demoted to developer/diagnostic scaffold at this slice's landing; `desktop/` is the durable surface.
- Shell components for hardware / LLM selection are read-mostly; user-initiated changes go through backend services, not through shell-local state.

**Acceptance.** Native dev build succeeds on both Windows host classes (not just cross-compile). Desktop live: tray → PTT → speak → state transitions visible → spoken response.

**Finish line.** README documents arch-split prerequisites. Both host classes can build and run the durable shell.

**Risks.**
- WebView2 version skew across Windows hosts may affect rendering; document minimum version.
- NSIS installer on ARM64 runs via emulation; acceptable but document clearly.

---

## D.3 — Resident Session Loop

**Goal.** Three or more consecutive voice turns in one session, no manual re-invocation, on both host classes.

**Scope.**
- Session service (`backend/app/services/session_service.py`) owns resident lifecycle.
- Continuous interaction without manual PTT between turns; wake word or hotkey triggers next turn.
- Closes the "single-turn caller-initiated next turn" boundary from C.4/C.5 into a true resident path.
- Desktop shell tray reflects resident state; conversation display updates continuously.

**Out of scope.** Wake invocation path (D.4).

**Acceptance.** Desktop live on both host classes: three+ consecutive turns without manual re-invocation.

---

## D.4 — Wake Integration in Durable Host

**Goal.** Wake phrase triggers LISTENING within the durable host.

**Scope.**
- B.4 wake runtime integrated into resident loop.
- Wake activates LISTENING without PTT; PTT remains available.
- Wake-unavailable degrades cleanly to PTT-only with visible indicator.

**Acceptance.** Desktop live: "hey jarvis" triggers LISTENING on both host classes via openWakeWord.

**Risks.** Wake concurrent with SPEAKING (barge-by-wake) is outside this boundary; the realtime conversation/session boundary owns that behavior.

---

## D.5 — Personality / Presence Polish

**Goal.** Personality profile switch is visible in the shell and reflected in the next turn's response style.

**Scope.**
- Personality shaping controls in shell (profile picker).
- Assistant presence behaviors (acknowledgment phrases, response pacing hints consumed by TTS).
- Overlay / ambient presence patterns are defined in `docs/`; implementation is not claimed by the desktop shell boundary.

**Acceptance.** Desktop live: personality switch changes next turn's response style.

---

~~# Group E — Local Service Substrate~~ Completed

## E.1 — Redis + SearXNG via docker-compose

**Why here.** Substrate stood up before any slice that consumes cache or search prevents those later slices from redrawing infrastructure boundaries.

**Goal.** Redis and SearXNG start cleanly via `docker compose up` and are reachable from the backend.

**Scope.**
- `docker-compose.yml` at repo root provisioning Redis + SearXNG with healthchecks and named volumes.
- Operator prerequisites documented: Docker Desktop or equivalent.
- Service discovery config in `config/cache/redis.yaml` and `config/models/search.yaml`.
- Fail-closed: backend runs without these services present; subsystems that need them report unavailable.

**Out of scope.** Backend wiring (E.2, E.3).

**Boundaries.**
- Owns: `docker-compose.yml`, `config/cache/redis.yaml`.

**Acceptance.** `docker compose up` → both services healthy from the host.

---

## E.2 — Cache Layer Wired to Redis

**Goal.** Cache layer is callable and degrades explicitly when Redis is unavailable.

**Scope.**
- `backend/app/cache/{manager,redis_client,policies,keys}.py`.
- Cache manager exposes get/set/delete with TTL; policies in config; key namespacing documented.
- Redis is accelerator and coordination substrate — durable authority stays in `data/`.
- Fail-closed: Redis unavailable returns cache-miss, not exception, to callers.

**Acceptance.** Unit + runtime live: cache roundtrip against running Redis; fail-closed when Redis stopped.

---

## E.3 — Internet Search Runtime

**Goal.** Search query returns results via SearXNG on healthy stack; falls back to DDGS when SearXNG down.

**Scope.**
- `backend/app/runtimes/internetsearch/{base,searxng_runtime,ddgs_runtime,tavily_runtime}.py`.
- Selector per `config/app/policies.yaml`: SearXNG primary, DDGS secondary, Tavily tertiary (requires API key).
- Standard result schema across providers.
- Used by tool adapter in F.2.

**Acceptance.** Runtime live: known query returns results via SearXNG; fallback exercised with SearXNG stopped.

**Risks.**
- SearXNG instance config affects engine availability; document minimum engine set in config notes.

---

~~# Group F — Tool Foundation + ACTING Path~~ Completed

## F.1 — Executor + ACTING State

**Why here.** `ConversationState.ACTING` must land on the live path so tool use is orchestrated, not ad-hoc.

**Goal.** A voice or text turn requiring tool use reaches ACTING state and returns a tool-grounded response.

**Scope.**
- `backend/app/cognition/executor.py` coordinates deterministic tool execution within the turn lifecycle.
- ACTING state exercised in the live turn; state transitions explicit in `engine.py`.
- Tool invocations and results recorded in turn artifacts.

**Out of scope.** Specific tools (F.2). Shell rendering (F.3).

**Acceptance.** Unit + runtime live: turn transitions through ACTING with a stub tool.

---

## F.2 — Tool Registry + First Tool Set

**Goal.** Time/date, filesystem read, internet search each produce correct, traceable results on the live runtime.

**Scope.**
- `backend/app/tools/registry.py` authoritative for tool discovery and dispatch.
- First tools:
  - `backend/app/tools/system/` — time/date, hardware-info (read-only).
  - `backend/app/tools/filesystem/` — read-only filesystem access within sandboxed paths.
  - `backend/app/tools/search/` — adapter over `backend/app/runtimes/internetsearch/`.
- Tool contract supports additional tool registration without redesign.
- Tool invocations explicit and logged; no hidden side effects.

**Boundaries.**
- Owns: `backend/app/tools/**`.

**Key design decisions.**
- Filesystem tool is read-only at this slice's scope. Write tools belong to the tool orchestration boundary and require their own policy gates.
- Search adapter is the only bridge from tools to runtimes; tools never reach past the runtime boundary.

**Acceptance.** Runtime live: each of the three tools returns correct results in a real voice turn.

---

## F.3 — Tool Result Rendering in Desktop + Text Shells

**Goal.** Desktop shell and text surface render tool-grounded responses without knowing tool internals.

**Scope.**
- Response shape extended to carry optional tool-result metadata consumable by shells.
- Desktop conversation display renders tool invocations (summary) + results (formatted per tool type).
- Text surface renders the same shape inline.
- Tool-result rendering schema in `backend/app/api/schemas/`.

**Acceptance.** Desktop live: turn that invokes search or filesystem tool renders the grounded response with visible attribution.

---

~~# Group G — Cross-Session Episodic Retrieval~~ Completed

## G.1 — Episodic Write + Retrieve

**Why here.** Session-scoped memory is not enough for a persistent local assistant. Episodic retrieval closes the gap between "works in a session" and "persistent assistant."

**Goal.** Session N can recall and reference information from session N-1 via episodic retrieval.

**Scope.**
- `backend/app/memory/episodic.py`: write, retrieve, and summarize episodic memory across sessions.
- `backend/app/memory/retrieval.py`: query episodic + working memory for relevant prior context.
- Durable authority: prior turn artifacts in `data/turns/`, sessions in `data/sessions/`.
- Explicit write policy extending `write_policy.py` pattern — governs what enters episodic memory, what is redacted, what is retained how long.
- Retrieval results logged in turn artifacts (explicit provenance).

**Out of scope.** Semantic/vector memory belongs to the semantic memory boundary. Cross-session summarization beyond recency-based recall belongs to the semantic memory boundary.

**Boundaries.**
- Owns: `backend/app/memory/{episodic,retrieval}.py`.

**Acceptance.** Unit + runtime live: turn in session N recalls an artifact fact from session N-1.

---

## G.2 — Retrieval Injected into Prompt Assembly

**Goal.** Retrieved context joins working memory at prompt-assembly time, traceable via turn artifact.

**Scope.**
- `prompt_assembler.py` extended to accept retrieval output alongside working memory.
- Retrieved-context provenance recorded per artifact: which turn it came from, why it was selected.

**Acceptance.** Runtime live: turn artifact shows injected retrieval context and its source.

---

## G.3 — Redis-Cached Retrieval

**Goal.** Retrieval lookups accelerated by Redis cache; fail-closed to direct query when Redis down.

**Scope.**
- Retrieval manager consults E.2 cache layer before falling to disk.
- Cache keys namespaced per retrieval operation.
- Durable memory authority stays in artifacts, not infrastructure.

**Acceptance.** Runtime live: retrieval-cache hit measured faster than miss; Redis-stopped path still returns results.

---

~~# Group H — Voice Acceleration~~ Completed

**Why this group exists here.** Voice acceleration (STT/TTS on GPU/NPU) belongs after the core loop, tools, memory, and episodic retrieval are stable. Acceleration work at this stage is a clean device-branch substitution inside already-proven runtime families — not new architecture. Local LLM service work belongs to the local LLM runtime boundary because it has distinct resource and build constraints that must be assessed independently after acceleration is proven.

**Voice-first ordering.** H works only on STT and TTS device uplift. LLM runtime selection (Ollama) is unchanged. Wake remains CPU-only.

**Viability-gate discipline.** Each acceleration variant (QNN, CUDA, DirectML) begins with a non-mutating viability gate that produces documented evidence before any wiring code is written. An unproven host or missing prerequisite closes as `SKIP-no-host`, `SKIP-prereq-missing`, or `NOT-WIRED:<reason>` — never as `BLOCKED-*`.

**Close states for hardware/provider sub-slices:**
- `PASS` — proven on the target host with the target device
- `SKIP-no-host` — no host with the required hardware was available
- `SKIP-prereq-missing` — required SDK, DLL, or package not present; not a blocker if clearly documented
- `NOT-WIRED:<reason>` — capability is defined and slotted, but current evidence does not justify runtime activation; the relevant capability boundary owns wiring and validation
- `Degraded-memory-constrained` — host hardware present but insufficient for the target model size; documented with memory parameters

## H.0 — Voice Acceleration Viability Census

**Why here.** Before writing any acceleration wiring code, produce a complete `(family × device × host_class)` state table from existing profiler/preflight evidence. Non-mutating. No package installs, no session creation, no model downloads.

**Goal.** A documented table stating what is currently provable per device per host for STT and TTS, and what prerequisites are missing.

**Scope.**
- Run `validate_backend.py profile` on both host classes.
- Enumerate `(STT × {cpu, cuda, directml, qnn}) × {x64, arm64}` and `(TTS × {cpu, cuda, directml}) × {x64, arm64}`.
- Record the result state for each cell using the close-state vocabulary above.
- Output is the input to H.1–H.8 planning; no code changes.

**Acceptance.** Census table recorded in `CHANGE_LOG.md` with both host classes. Table uses close-state vocabulary only — no ambiguous cell states.

**Finish line.** Architect / Advisor / User agree on which H sub-slices are implementation and which are SKIP before H.1 begins.

---

## H.1 — STT CPU Baseline Reconfirmation

**Goal.** STT CPU path green on both host classes post-G. Confirms the regression baseline before any acceleration wiring.

**Scope.**
- Run existing STT live tests on both host classes.
- Record any regressions from the B.5 / G-era baseline.
- No code changes unless a regression is found.

**Acceptance.** `validate_backend.py runtime --families stt --devices cpu` green on both host classes. Regression ≥ 96.

---

## H.2 — ARM64 QNN Prerequisite Gate

**Why here.** QNN slot was defined in A.6. Before activation code is written, QNN prerequisite enablement must be proven: provider/plugin discovery and HTP backend discovery.

**Goal.** Confirmed: QAIRT SDK installed and `QnnHtp.dll` discoverable so ARM64 QNN environment/provider readiness is proven.

**Scope.**
- Non-mutating verification: `QAIRT_SDK_PATH` set, DLL probe succeeds, `onnxruntime-qnn` imports on ARM64.
- H.2 owns environment and provider gate only: DLL discoverability + `QNNExecutionProvider` registration. Artifact acquisition and session proof are owned by the H.3 pre-qual (`2026-05-11-slice_h.3_pre-qual.md`).
- H.3 pre-qual owns artifact acquisition, artifact layout proof, encoder/decoder QNN session loading, tensor contract capture, and one-step decode viability.
- If any prerequisite is missing: close H.2 as `SKIP-prereq-missing` with an explicit checklist of what is missing. H.3 pre-qual cannot start until H.2 closes as `PASS`.

**Acceptance.** Gate closes as `PASS` (all prerequisites confirmed) or `SKIP-prereq-missing` (missing items documented). `BLOCKED-*` is not an acceptable state.

---

## H.3 — ARM64 QNN STT Activation

**Depends on:** H.2 `PASS`.

**Goal.** Voice turn on the Qualcomm ARM64 host completes with `selected_device="qnn"` for STT. CPU-EP regression still green on the same host.

**Scope.**
- Activate QNN STT by loading the artifact proven by H.3 pre-qual and selecting QNN only when readiness and artifact proof are both present.
- Use existing ONNX Whisper runtime only if its model contract is compatible with the proven artifact layout; otherwise add a narrow QNN/Qualcomm STT adapter.
- Populate the QNN Whisper catalog entry for the proven artifact path.
- Preflight owns QAIRT DLL discovery (extends A.3 pattern).
- Selector prefers QNN when ready; CPU-EP remains baseline fallback.

**Out of scope.** QNN TTS (no verified Kokoro HTP quantization). QNN LLM or Wake.

**Acceptance.** Runtime live: voice turn with `selected_device="qnn"` on ARM64 Qualcomm host. CPU-EP regression green on the same host.

**Risks.**
- QNN HTP op coverage is a subset of ONNX; session creation may succeed but partition unexpectedly to CPU. Document probe method in readiness evidence.

---

## H.4 — x64 CUDA STT Readiness / Regression Guard

**Goal.** Confirm CUDA EP status on available x64 NVIDIA host and protect the regression baseline.

**Scope.**
- Run existing CUDA STT live test or viability probe on x64 NVIDIA host.
- If no NVIDIA CUDA host is available: close H.4 as `SKIP-no-host`.
- If CUDA EP is missing or not proven: close H.4 as `SKIP-prereq-missing`.
- No new wiring code unless CUDA STT is currently broken (regression only).

**Acceptance.** `PASS`, `SKIP-no-host`, or `SKIP-prereq-missing` — all acceptable. Regression ≥ 96 either way.

---

## H.5 — Windows DirectML Voice Viability Gate

**Goal.** Confirm whether `DmlExecutionProvider` is loadable and usable for STT/TTS on any available Windows GPU host.

**Scope.**
- Non-mutating probe: attempt `onnxruntime-directml` import + EP registration on available host.
- If no DirectML-capable host available: close H.5 as `SKIP-no-host`.
- If EP fails to load or register: close H.5 as `SKIP-prereq-missing` with reason.
- Result is the gate for H.6.

**Acceptance.** `PASS` or `SKIP-*` with documented reason. No implementation unless `PASS`.

---

## H.6 — DirectML STT/TTS Device Option Activation

**Depends on:** H.5 `PASS`.

**Goal.** Voice turn on a Windows DirectML host completes with `selected_device="directml"` for STT and/or TTS.

**Scope.**
- Activate DirectML branch in `onnx_whisper_runtime.py` and `kokoro_onnx_runtime.py` where H.5 proved the EP loadable.
- Selector updates to prefer DirectML when ready.
- If H.5 was `SKIP-*`: H.6 closes as `NOT-WIRED:<reason>` without any code change.

**Acceptance.** Runtime live with DirectML device on proven host, or `NOT-WIRED:<reason>` if H.5 was `SKIP-*`.

---

## H.7 — TTS Acceleration Viability / Device Slot Normalization

**Goal.** TTS device options normalized alongside STT. CPU proven on both hosts. CUDA/DirectML where viability gates proved provider support. QNN TTS explicitly marked not wired when no verified Kokoro HTP quantization exists.

**Scope.**
- TTS CPU live test reconfirmation on both host classes.
- TTS CUDA / DirectML branches activated where the corresponding STT gate (H.4 / H.6) proved the EP.
- QNN TTS: explicitly `NOT-WIRED:no-verified-kokoro-htp-quantization`. Document in `config/hardware/notes.md`.

**Acceptance.** TTS CPU `PASS` on both hosts. Acceleration variants `PASS` or `NOT-WIRED:<reason>`.

---

## H.8 — Voice Acceleration Live Turn Matrix

**Goal.** All H sub-slices reconciled into a recorded `(family × device × host_class)` state table. No `BLOCKED-*` cells at closeout.

**Scope.**
- Run `validate_backend.py matrix` on both host classes.
- Every cell is `PASS`, `SKIP-*`, or `NOT-WIRED:<reason>`. Any `FAIL` blocks Group H closeout.
- Matrix recorded in `SYSTEM_INVENTORY.md` as the Group H gate entry.

**Acceptance.** Matrix green on both host classes (allowing SKIP/NOT-WIRED cells with reasons). Regression >= 96.

**Finish line.** Group I hardware-path normalization may begin.

---

~~# Group I — Hardware Path Normalization~~ Completed

**Why this group exists here.** Hardware acceleration evidence records what actually works per device per host class. The readiness/provisioning boundary consumes that evidence to normalize the selector, readiness deriver, and preflight reporting into coherent, documented acceleration paths for both host classes. Additional hardware variants (Intel NPU, additional AMD GPUs) are represented as defined-but-not-wired slots owned by the hardware acceleration boundary.

## I.1 — ARM Acceleration Sequence Normalization

**Goal.** ARM64 path fully documented and normalized: CPU → QNN (if H.3 passed) → fallback chain. Selector and readiness deriver reflect the proven evidence from H.

**Scope.**
- Normalize `derive_stt_device_readiness()` and `derive_tts_device_readiness()` to prefer QNN when H.3 proved it, fall back to CPU cleanly.
- Intel NPU and other ARM NPU variants represented as defined-but-not-wired slots owned by the hardware acceleration boundary.
- No new runtime families; this is selector and readiness normalization only.
- Document the ARM64 path in `config/hardware/notes.md`.

**Acceptance.** Unit: ARM64 readiness derivation correct for all acceleration states from H. Runtime live: ARM64 host selects the best proven device and falls back cleanly.

---

## I.2 — x64 Acceleration Sequence Normalization

**Goal.** x64 path fully normalized: CPU → CUDA (if H.4 passed) → DirectML (if H.6 passed) → fallback chain.

**Scope.**
- Normalize x64 readiness derivers to prefer CUDA → DirectML → CPU in documented order.
- Non-NVIDIA GPU variants (Intel iGPU, AMD without DirectML) represented as defined-but-not-wired slots owned by the hardware acceleration boundary.
- Document the x64 path in `config/hardware/notes.md`.

**Acceptance.** Unit: x64 readiness derivation correct for all acceleration states from H. Runtime live: x64 host selects the best proven device.

---

## I.3 — Live Mic/Audio User-Interaction Matrix

**Goal.** Full end-to-end voice turn (mic in → STT → LLM → TTS → speaker out) validated on both host classes with the best available device from I.1/I.2.

**Scope.**
- Live voice turn with microphone and speaker on both host classes.
- STT uses the normalized device from I.1/I.2 (best proven device, not forced CPU).
- Interruption path exercised.
- Results recorded in `CHANGE_LOG.md` per host class.

**Acceptance.** Desktop live: mic-in → spoken-response on both host classes. Regression ≥ 96.

**Finish line.** Hardware acceleration path is normalized and proven end-to-end on both host classes. Group J readiness/UX work may begin.

---

~~# Group J — Runtime/Readiness UX + Degraded-State Surfacing~~ Completed

**Why this group exists here.** After acceleration is normalized (H+I), the readiness surface expands significantly: more devices, more prerequisites, more possible degraded states. Before UI controls land (K), the readiness data must be accurate, visible, and surfaced with explicit reasons. This is a backend-and-API concern that must be stable before K adds interactive controls that depend on it.

**Goal.** Every runtime family shows its selected device, readiness state, and degraded/fallback reason in the desktop shell and in `GET /readiness`. Operator can diagnose any degraded state from the UI without reading source code.

**Scope.**
- Extend `GET /readiness` response to surface per-family: selected device, ready flag, reason string, fallback chain taken.
- Desktop shell readiness panel updated to render the extended readiness data.
- Degraded-mode indicators visible per family (e.g., "STT: CPU (QNN prereq missing)", "LLM: Ollama (local not configured)").
- Readiness trace accessible from `GET /diagnostics/preflight`.
- `scripts/run_jarvis.py --profile` and `validate_backend.py profile` updated to emit the extended readiness summary.

**Out of scope.** Interactive controls or `.env` editing (K). Agent framework (L). Local LLM (M).

**Acceptance.** Desktop live: readiness panel shows correct device/reason for each family on both host classes. Degraded state induced artificially shows the correct reason.

---

~~# Group K — UI Controls + Operator Settings~~ Completed

**Why this group exists here.** With readiness data accurate and visible (J), interactive controls can be added safely. Controls that modify operator settings must have explicit guardrails so the UI cannot silently mutate runtime state or policy.

**Goal.** Operator can adjust configurable settings from the UI and see the effect after backend restart. No live runtime mutation.

**Scope.**
- App size, font size, button layout, settings flyout, icon polish.
- Capability/selector controls: display and switch between proven runtime options (device, personality, LLM runtime) via existing backend API.
- **Operator-configurable `.env` editing**: UI may write only fields explicitly declared as operator-configurable in `config/hardware/notes.md`. All writes target `.env` only — not `settings.py`, `pyproject.toml`, or any config YAML. The existing settings precedence (shell env > `.env` > `.env.example`) is preserved.
- **Restart-required semantics**: all `.env` changes require backend restart to take effect. The UI makes this explicit ("Restart required" label + restart button). No live runtime switching from the UI.
- **Bootstrap toggles** (Docker/Redis/SearXNG enable/disable): these are startup-time settings, not live switches. UI presents them as restart-required; the backend startup sequence reads them and configures accordingly. Toggling does not trigger a live service start/stop.
- No new routes or backend logic required beyond what J exposes.

**Out of scope.** Agent framework (L). Local LLM (M). Advanced policy editing.

**Acceptance.** Desktop live: operator changes an allowed `.env` field, restarts backend, and sees the effect reflected in the readiness panel. An attempt to write a non-operator-configurable field is rejected or silently ignored.

---

~~# Group L — Personality Policy Envelope~~ Completed

**Why this group exists here.** Personality is already visible and selectable in the durable desktop/backend surface, but current runtime behavior is intentionally thin: `backend/app/personality/schema.py` carries only `profile_id`, `display_name`, `tone`, `brevity`, `formality`, and legacy `system_prompt_addendum`; `backend/app/cognition/prompt_assembler.py` receives `personality` and currently ignores it; `backend/app/conversation/engine.py` already passes the active profile into prompt assembly and records `active_personality_profile_id` in turn artifacts. Group L turns that existing integration point into an application-owned policy envelope before agents or additional LLM runtimes consume it.

**Reference inputs.**
- Product requirement: `ProjectVision.md` requires personality to be structured, inspectable, modality-consistent, and unable to override safety, facts, or deterministic orchestration.
- Current capability state: `SYSTEM_INVENTORY.md` and `CHANGE_LOG.md` show personality profile selection and desktop metadata display exist, while Slice K explicitly did not change personality runtime behavior.
- Current code anchors: `backend/app/personality/schema.py`, `backend/app/personality/loader.py`, `backend/app/personality/adapter.py`, `config/personality/*.yaml`, `backend/app/cognition/prompt_assembler.py`, `backend/app/cognition/responder.py`, `backend/app/conversation/engine.py`, `backend/app/runtimes/llm/base.py`, `backend/app/artifacts/turn_artifact.py`, `backend/app/api/routes/personality.py`, `backend/app/api/schemas/personality.py`.
- External constraint reference for implementation planning: OWASP prompt-injection guidance supports segregating trusted instructions from user, retrieved, and tool content; Group L should claim structured authority separation and deterministic rendering, not complete prompt-injection prevention.

**Goal.** Replace raw-or-ignored personality behavior with a structured `PersonalityProfile -> PersonalityPolicy -> PromptEnvelope -> renderer -> LLM runtime -> style guard -> TTS-safe response` boundary that works with current flat-string local/Ollama paths and leaves a clear adapter path for structured-message runtimes.

**Scope.**
- Expand personality profiles into validated, structured style data: identity summary, tone, brevity, formality, warmth, assertiveness, humor policy, response style, acknowledgment style, confirmation style, interruption style, voice pacing, voice energy, and enabled state.
- Compile profiles into a bounded `PersonalityPolicy` that can influence style, wording, pacing, and presentation, but cannot define tool permissions, model routing, memory policy, safety overrides, hidden instructions, or orchestration authority.
- Introduce a structured prompt envelope that separates application rules, personality style policy, working memory, retrieved memory, tool results, user transcript, and output contract by authority/provenance.
- Preserve current flat `LLMBase.generate(prompt: str)` compatibility while adding an optional envelope-aware generation boundary for structured-message API runtimes.
- Add a deterministic style guard after LLM generation for bounded style, single-turn response constraints, and voice/text presentation cleanup.
- Keep active personality traceable through turn artifacts and existing session/personality selection paths.

**Out of scope.**
- New model providers, provider installation, OAuth/API escalation, llama.cpp activation, or local LLM service work.
- Hardware profiling, provisioning, preflight/readiness, STT/TTS runtime selection, wake monitoring, search provider fallback, Redis/SearXNG behavior, memory storage format, desktop layout, or operator settings semantics.
- LLM-driven tool selection, autonomous agent behavior, agent role contracts, or tool permission changes.
- Claiming prompt-injection prevention as solved; Group L only claims segmented authority, deterministic rendering, and safer personality consistency.

**Boundaries.**
- Owns: `backend/app/personality/schema.py`, `backend/app/personality/loader.py`, `backend/app/personality/adapter.py`, new `backend/app/personality/policy.py`, `config/personality/*.yaml`, `backend/app/cognition/prompt_assembler.py`, new `backend/app/cognition/prompt_envelope.py`, new `backend/app/cognition/prompt_renderer.py`, new `backend/app/cognition/style_guard.py`, narrow additions to `backend/app/runtimes/llm/base.py`, narrow integration in `backend/app/conversation/engine.py`, and focused tests under `backend/tests/unit/personality/`, `backend/tests/unit/cognition/`, and `backend/tests/unit/conversation/`.
- May touch only for compatibility if needed: `backend/app/api/routes/personality.py`, `backend/app/api/schemas/personality.py`, `backend/tests/unit/api/test_routes.py`, `backend/tests/unit/desktop/test_desktop_static_contract.py`.
- Must not touch: `backend/app/hardware/**`, `scripts/provision.py`, `scripts/validate_backend.py`, `pyproject.toml`, `backend/app/runtimes/stt/**`, `backend/app/runtimes/tts/**`, `backend/app/runtimes/wake/**`, `backend/app/tools/**`, `backend/app/runtimes/internetsearch/**`, `docker-compose.yml`, `desktop/src/style.css`, desktop layout structure, or `desktop/src-tauri/**`.

**Key design decisions.**
- Personality is not an authority source. It sits below application invariants, safety/policy, deterministic orchestration, tool authority, routing authority, and factual grounding.
- `system_prompt_addendum` is not the primary mechanism. It may remain temporarily as a legacy config field, but Group L must not pass it raw into prompt content.
- Role overlays, if introduced, are style-only. They may tune response shape for personal-assistant, research, code-planning, code-agent, tool-narration, error-reporting, or escalation-narration contexts, but they cannot grant permissions or choose runtimes.
- Tool output, retrieved memory, and working memory are rendered as context with explicit provenance, not as trusted application/persona instructions.
- Flat-string rendering remains the default compatibility path for current Ollama/local-style runtimes. Structured role-message rendering is an extension point, not a requirement for Group L closeout.
- Response normalization is deterministic. Do not add a second LLM as a default persona judge.

**Governance recording.**
- Each validated L sub-slice records its completed evidence in `CHANGE_LOG.md` before the next L sub-slice begins.
- `SYSTEM_INVENTORY.md` is updated only during L.6 closeout after full Group L validation evidence exists.

## L.0 — Personality Runtime Boundary Census

**Why here.** Before changing behavior, record the current personality and prompt path from code evidence so later implementation does not accidentally reopen Slice C/D/F/G/J/K boundaries.

**Goal.** A repo-grounded baseline of the current profile schema, config fields, prompt assembly behavior, turn-engine integration, response normalizer behavior, LLM interface, API summary, and desktop metadata assumptions.

**Scope.**
- Inspect `backend/app/personality/**`, `config/personality/*.yaml`, `backend/app/cognition/prompt_assembler.py`, `backend/app/cognition/responder.py`, `backend/app/conversation/engine.py`, `backend/app/runtimes/llm/base.py`, `backend/app/api/routes/personality.py`, and desktop static contract tests.
- Identify tests that currently assert personality addendum is not injected and prompt assembly ignores personality.
- No code changes unless the sub-slice is explicitly approved as an implementation gate.

**Acceptance.** Baseline evidence recorded before L.1 begins, including exact files inspected and the expected behavior changes L.1-L.5 will intentionally make. `CHANGE_LOG.md` records the validated L.0 evidence before L.1 begins.

**Finish line.** The implementation boundary is documented and the affected test set is known.

---

## L.1 — Structured Personality Profile Schema + Loader Validation

**Goal.** Personality profiles are structured enough to persist, compare, validate, list, select, and apply consistently without free-form prompt authority.

**Scope.**
- Extend `PersonalityProfile` with the minimal structured fields required by `ProjectVision.md`: `identity_summary`, `warmth`, `assertiveness`, `humor_policy`, `response_style`, `acknowledgment_style`, `confirmation_style`, `interruption_style`, `voice_pacing`, `voice_energy`, and `enabled`.
- Update `config/personality/default.yaml`, `config/personality/concise.yaml`, and `config/personality/warm.yaml` to include the new fields.
- Add enum-like validation in the loader/schema layer and reject unknown/prohibited authority fields such as tool permissions, routing rules, memory permissions, safety overrides, or hidden instructions.
- Preserve profile selection by `profile_id` and the existing desktop/API summary contract unless a narrow additive field exposure is required.
- Treat `system_prompt_addendum` as legacy/deprecated compatibility data; do not make it a raw prompt instruction.

**Out of scope.** Prompt rendering and response style enforcement (L.2-L.5).

**Acceptance.**
- Unit: personality profile roundtrip, YAML loading, unknown profile rejection, unsafe profile id rejection, unknown/prohibited field rejection, and default profile loading all pass.
- API/static compatibility: existing personality list/select behavior remains intact.
- `CHANGE_LOG.md` records the validated L.1 evidence before L.2 begins.

**Finish line.** All configured profiles load through the expanded validated schema, and invalid authority-bearing config fails closed.

---

## L.2 — PersonalityPolicy Compiler + Style-Only Role Overlays

**Goal.** Convert a validated `PersonalityProfile` into bounded style policy data consumed by prompt construction and response guarding.

**Scope.**
- Add `backend/app/personality/policy.py` with a deterministic compiler from `PersonalityProfile` to `PersonalityPolicy`.
- Policy output includes identity, style rules, speech rules, bounded confirmation/acknowledgment/interruption guidance, and a list of forbidden override categories for trace/debug use.
- Add optional style-only role overlays if a current code path needs them; overlays cannot alter tool permissions, runtime selection, memory policy, safety policy, or orchestration state transitions.
- Keep the current selected profile as the only personality state source in `SessionService` and `TurnEngine`.

**Out of scope.** Agent role contracts and agent orchestration. Those remain Group O.

**Acceptance.**
- Unit: compiler is deterministic for fixed input, rejects unsupported style values, applies defaults, and proves overlays cannot introduce prohibited authority fields.
- `CHANGE_LOG.md` records the validated L.2 evidence before L.3 begins.

**Finish line.** Personality behavior is represented as validated policy data, not raw prompt text.

---

## L.3 — PromptEnvelope + Flat Renderer

**Goal.** Prompt construction becomes structured and provenance-aware while preserving the current flat prompt string path.

**Scope.**
- Add `backend/app/cognition/prompt_envelope.py` with `PromptSegment` and `PromptEnvelope` concepts covering authority/provenance, content type, trust level, and text.
- Add `backend/app/cognition/prompt_renderer.py` to render an envelope into a deterministic flat prompt for current local/Ollama-style runtimes.
- Update `assemble_prompt()` to build an envelope from application rules, personality policy, working memory, retrieved context, user transcript, and output contract, then render it flat by default.
- Fence retrieved memory and tool content as untrusted context, not instruction authority.
- Preserve current turn artifact compatibility by continuing to store the rendered prompt text in `final_prompt_text`.

**Out of scope.** Native chat-role provider calls; L.4 only creates the adapter path.

**Acceptance.**
- Unit: fixed profile/transcript/memory/retrieval input produces deterministic prompt text.
- Unit: retrieved content containing strings such as "ignore previous instructions" appears only in an untrusted context segment.
- Unit: prompt still ends with the expected assistant output contract for flat runtimes.
- `CHANGE_LOG.md` records the validated L.3 evidence before L.4 begins.

**Finish line.** `assemble_prompt()` no longer ignores personality, and prompt authority ordering is explicit in code and rendered output.

---

## L.4 — LLM Envelope Adapter + Turn Integration

**Goal.** The turn engine can pass the same personality-aware envelope contract through current and structured-message LLM runtime adapters without breaking existing runtimes.

**Scope.**
- Add an optional `generate_envelope(envelope, **kwargs)` method to `LLMBase` that defaults to flat rendering plus existing `generate(prompt: str)`.
- Keep all existing concrete LLM runtimes compatible without requiring provider installation or cloud/API calls.
- Update `TurnEngine` to use the envelope-aware boundary where available while preserving existing failure handling, ACTING state behavior, tool invocation metadata, retrieval references, and turn artifact writes.
- Move tool execution context insertion toward envelope segments rather than appending raw text to the rendered prompt.

**Out of scope.** Changing runtime selection, adding providers, changing tool execution authority, or adding agents.

**Acceptance.**
- Unit: fake LLMs using only `generate(prompt)` still pass.
- Unit: envelope-aware fake LLM receives the structured envelope.
- Unit: tool result content is rendered as untrusted `tool_result` context and still records `tools_invoked` / `agent_trace` exactly as before.
- Runtime: existing text-turn and voice-turn live tests remain green on target host classes.
- `CHANGE_LOG.md` records the validated L.4 evidence before L.5 begins.

**Finish line.** Current flat-string runtimes keep working, and structured-message runtimes have a single adapter boundary.

---

## L.5 — Deterministic Style Guard + TTS Projection

**Goal.** Apply personality style after generation through deterministic normalization that is safe for text and voice paths.

**Scope.**
- Add `backend/app/cognition/style_guard.py` or extend the existing responder boundary without duplicating it.
- Preserve `bound_single_turn_response()` and `sanitize_for_tts()` behavior while adding bounded style cleanup for brevity, acknowledgment trimming, confirmation wording, and TTS-safe presentation.
- Apply voice/text modality as an input to the guard so voice can prefer shorter, cleaner spoken output without changing factual content or tool policy.
- Ensure the guard cannot add new facts, perform tool calls, select models, or rewrite failure states.

**Out of scope.** Second-pass LLM judging, emotional speech synthesis, TTS voice model switching, or audio runtime changes.

**Acceptance.**
- Unit: style guard is deterministic and bounded for representative profiles.
- Unit: voice output remains TTS-safe and strips markdown/control text as current tests expect.
- Unit: guard does not alter tool metadata, final state, failure reason, or retrieved memory refs.
- `CHANGE_LOG.md` records the validated L.5 evidence before L.6 begins.

**Finish line.** Personality affects final wording/presentation through deterministic constraints without becoming another reasoning or policy engine.

---

## L.6 — Cross-Surface Validation + Governance Closeout

**Goal.** Prove the personality policy envelope works across text, voice, artifacts, API selection, and desktop metadata without reopening unrelated surfaces.

**Scope.**
- Focused unit tests under personality, cognition, conversation, API, and desktop static contract as needed.
- Runtime validation for text turn and voice turn on Windows x64 and Windows ARM64 using the repository validator.
- Regression validation remains green on both host classes.
- Update `CHANGE_LOG.md` with L.6 validation evidence before closeout.
- Update `SYSTEM_INVENTORY.md` only in L.6, and only after full Group L validation evidence exists.

**Acceptance.**
- `backend\.venv\Scripts\python -m pytest` focused suites PASS on the implementing host.
- `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families turn --devices cpu` or the host-appropriate turn runtime subset PASSes where applicable.
- `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASSes on Windows x64 and Windows ARM64.
- Prompt-injection fixture proves user/retrieved/tool content is not promoted into application/personality policy.
- Desktop personality metadata remains stable or additive-only.
- `CHANGE_LOG.md` records the validated L.6 evidence, then `SYSTEM_INVENTORY.md` records the completed Group L capability.

**Finish line.** Personality is structured, validated, rendered through a trusted prompt envelope, applied consistently to text/voice prompt construction, guarded deterministically after generation, and traceable through turn artifacts.

---

~~# Group M - Realtime Conversation Session Boundary~~ Completed

**Why this group exists here.** The product already has a resident voice path, a durable desktop/API session status surface, committed turn execution, wake/PTT behavior, canonical conversation states, and turn/session artifacts. What is still missing is a durable realtime session boundary that owns live invocation timing, event ordering, interruption context, and channel handoff without taking ownership from the committed turn engine. Group M inserts that boundary before agents so later orchestration consumes a stable conversation-session substrate instead of reaching into voice service internals.

**Reference inputs.**

- Product direction: `ProjectVision.md` requires deterministic session lifecycle, canonical states, wake/PTT voice surfaces, barge-in, local-first operation, and traceable turn artifacts.
- Current capability state: `SYSTEM_INVENTORY.md` and `CHANGE_LOG.md` record verified voice turn, resident session, wake/PTT, desktop/backend, semantic-memory, and personality-envelope capabilities.
- Current code anchors: `backend/app/services/resident_voice_invocation.py`, `backend/app/services/session_service.py`, `backend/app/conversation/engine.py`, `backend/app/conversation/session_manager.py`, `backend/app/conversation/states.py`, `backend/app/artifacts/session_artifact.py`, `backend/tests/unit/services/test_resident_voice_invocation.py`, `backend/tests/unit/services/test_session_service.py`.
- External reference input: `20260613_slice-m.md` cites LiveKit, Twilio ConversationRelay, and Dialogflow CX as prior art for separating live session mechanics, interruption handling, and state progression from reasoning policy.

**Goal.** Add a realtime conversation session boundary that records ordered live-session events, commits ready user turns to the existing `TurnEngine`, preserves current wake/PTT behavior, and leaves reasoning, tools, memory, prompt assembly, STT/TTS runtime selection, and desktop UI ownership unchanged.

**Out of scope.**

- Agent framework behavior, role contracts, planner/executor orchestration, or autonomous tool selection.
- Semantic-memory redesign, retrieval policy changes, or memory storage changes.
- Personality policy changes or prompt-envelope authority changes.
- LLM routing, model selection, STT/TTS runtime selection, wake runtime replacement, hardware provisioning, or preflight/readiness changes.
- WebRTC, telephony, cloud realtime backends, streaming LLM/TTS protocol, VAD endpointing, or automated progress-phrase scheduling.
- Desktop UI redesign.

**Boundaries.**

- The realtime session boundary owns live session events, invocation timing, source/channel metadata, interruption event context, and handoff into committed turns.
- `TurnEngine` continues to own committed turn execution, STT, reasoning, tools, memory retrieval, LLM generation, TTS playback, current barge-in behavior, and `TurnArtifact` content.
- `SessionService` continues to own the coarse active status exposed to desktop/API clients.
- `SessionManager` continues to own session id, working memory, turn artifact storage, and session artifact closeout.
- `ConversationState` remains the canonical coarse state vocabulary.

**Minimum event ordering target.**

```text
SESSION_ACTIVE
INVOCATION_RECEIVED
AUDIO_CAPTURE_STARTED
AUDIO_CAPTURE_COMPLETED
USER_TURN_COMMITTED
TRANSCRIBING
REASONING
RESPONDING
SPEAKING
TURN_COMPLETED
SESSION_IDLE
```

**Minimum interruption ordering target.**

```text
ASSISTANT_SPEECH_STARTED
USER_INTERRUPTION_DETECTED
ASSISTANT_SPEECH_STOP_REQUESTED
TURN_RECOVERING
SESSION_IDLE
```

**Governance recording.**

- Each validated M sub-slice records completed evidence in `CHANGE_LOG.md` before the next M sub-slice begins.
- `SYSTEM_INVENTORY.md` is updated only during M.6 closeout after full Group M validation evidence exists.

## M.0 — Realtime Boundary Census and Event Vocabulary Baseline

**Goal.** Establish the repository-accurate baseline for realtime session ownership before code changes.

**Scope.** Reconfirm current responsibilities of `ResidentVoiceInvocationService`, `SessionService`, `TurnEngine`, `SessionManager`, `ConversationState`, `TurnArtifact`, and `SessionArtifact`. Define the first event vocabulary by mapping current observable transitions rather than inventing new runtime concepts.

**Acceptance.** Census references the exact files and tests inspected, distinguishes live session events from committed turn artifacts, and does not assign reasoning, memory, tool execution, or prompt assembly ownership to the realtime boundary.

**Validation.** Documentation-only diff review plus optional baseline targeted tests. Append `CHANGE_LOG.md` after validation evidence exists. Do not update `SYSTEM_INVENTORY.md` in M.0.

---

## M.1 — Realtime Event Schema and Session Ledger Contract

**Goal.** Add the typed data contract for realtime session events without changing voice-turn behavior.

**Scope.** Add a small conversation realtime module for event records and ledger helpers. Model deterministic event fields: session id, event type, monotonic sequence, timestamp, source, optional turn id, coarse conversation state, and metadata. Preserve `SessionArtifact` as closeout and `TurnArtifact` as committed-turn evidence.

**Suggested locations.** `backend/app/conversation/realtime/events.py`, `backend/app/conversation/realtime/ledger.py`, and `backend/tests/unit/conversation/realtime/`.

**Acceptance.** Event construction is deterministic and unit tested. Ledger ordering is append-only and sequence based. Tool, memory, personality, and prompt data are not stored in realtime event records except by explicit reference id where already available.

**Validation.** Focused unit tests, then `backend/.venv/Scripts/python scripts/validate_backend.py unit`. Append `CHANGE_LOG.md` after validation evidence exists.

---

## M.2 — Realtime Conversation Session Coordinator~

**Goal.** Introduce the coordinator that owns live session timing and delegates committed turns to the existing `TurnEngine`.

**Scope.** Add a `RealtimeConversationSession` that accepts invocation/channel events, records realtime events, commits ready user input, and delegates to `TurnEngine.run_text_turn()` or `TurnEngine.run_voice_turn()`. Keep `SessionManager` and `SessionService` in their current ownership roles.

**Suggested locations.** `backend/app/conversation/realtime/session.py`, `backend/app/conversation/realtime/policy.py`, and focused tests under `backend/tests/unit/conversation/realtime/`.

**Acceptance.** Coordinator can start a session, record invocation events, commit exactly one user turn for ready input, and return to idle. Existing `TurnEngine` behavior is called rather than duplicated. The coordinator does not perform STT, TTS, LLM, memory retrieval, tool execution, or prompt assembly itself.

**Validation.** Unit tests with fake turn engine/session service dependencies, then `backend/.venv/Scripts/python scripts/validate_backend.py unit`. Append `CHANGE_LOG.md` after validation evidence exists.

---

## M.3 — Resident Voice Adapter Integration

**Goal.** Move live voice invocation orchestration behind the realtime session boundary while preserving current wake/PTT behavior.

**Scope.** Refactor `ResidentVoiceInvocationService` into a channel adapter that normalizes source, handles queueing, captures or forwards audio, and submits invocation events to the realtime coordinator. Preserve push-to-talk capture, wake invocation using supplied audio without second capture, wake empty-transcript response text, PTT empty-transcript failure semantics, worker queue draining, failure cleanup, and registered invocation hooks.

**Primary files.** `backend/app/services/resident_voice_invocation.py`, `backend/app/services/session_service.py`, `backend/tests/unit/services/test_resident_voice_invocation.py`, `backend/tests/unit/services/test_session_service.py`.

**Acceptance.** Existing resident voice invocation behavior remains green. Realtime events are emitted in expected order for PTT and wake invocations. No second audio capture occurs for wake-supplied audio. The adapter does not gain reasoning, memory, tool, prompt, or runtime-selection responsibilities.

**Validation.** Focused resident voice and session service tests, then `backend/.venv/Scripts/python scripts/validate_backend.py unit`. Append `CHANGE_LOG.md` after validation evidence exists.

---

## M.4 — Turn-Taking and Failure Event Coverage

**Goal.** Make normal, empty-input, and capture-failure paths observable through realtime events without introducing streaming endpointing.

**Scope.** Add turn-taking policy that treats current PTT/wake audio submission as the committed user-turn boundary. Record deterministic event sequences for normal completion, no-speech wake handling, PTT empty transcript failure, capture failure, and engine failure. Keep canonical coarse states aligned with `ConversationState`.

**Suggested locations.** `backend/app/conversation/realtime/turn_taking.py` plus existing resident voice and realtime unit tests.

**Acceptance.** Normal invocation event order matches the Group M minimum ordering target. Failure paths record terminal failure context without masking current exception behavior. Session status remains accurate after success, failure, and cleanup. No VAD, streaming endpointing, or partial transcript protocol is introduced.

**Validation.** Focused realtime and resident voice unit tests, then `backend/.venv/Scripts/python scripts/validate_backend.py unit`. Append `CHANGE_LOG.md` after validation evidence exists.

---

## M.5 — Interruption and Response Boundary Events

**Goal.** Represent assistant speech and interruption events at the realtime boundary while keeping current playback and barge-in behavior in `TurnEngine`.

**Scope.** Add event wrappers for assistant speech start, interruption detection, stop request, recovery, and idle return. Preserve existing `BargeInDetector`, playback start/stop, `interruption_events`, and `ConversationState` usage in `TurnEngine`. Provide a deterministic response-event queue for non-streaming assistant responses.

**Suggested locations.** `backend/app/conversation/realtime/interruption.py`, `backend/app/conversation/realtime/response_queue.py`, `backend/tests/unit/conversation/realtime/`, and existing turn-engine tests if present and relevant.

**Acceptance.** Interruption events appear in realtime order without moving interruption ownership out of `TurnEngine`. Existing turn artifact interruption fields are preserved. Non-interrupted responses still produce speech-start and completion/idle events. No streaming LLM or streaming TTS protocol is added.

**Validation.** Focused realtime interruption/response queue tests, relevant existing turn-engine tests, then `backend/.venv/Scripts/python scripts/validate_backend.py unit`. Append `CHANGE_LOG.md` after validation evidence exists.

---

## M.6 — Runtime Validation and Governance Closeout

**Goal.** Close Group M with validated behavior, governance entries, and no undocumented capabilities.

**Scope.** Run the smallest relevant validation first, then broaden only as required by repository governance. Confirm desktop/API status behavior still reflects wake/PTT invocation state. Confirm committed turn artifacts and session closeout artifacts still use their existing owners.

**Required validation path.** Focused unit tests for realtime, resident voice, session service, and any touched turn-engine behavior; `backend/.venv/Scripts/python scripts/validate_backend.py unit`; `backend/.venv/Scripts/python scripts/validate_backend.py regression`.

**Governance closeout.** Append `CHANGE_LOG.md` entries at each validated sub-slice. Update `SYSTEM_INVENTORY.md` only in M.6 after full validation proves an observable realtime conversation session boundary exists. Do not promote inventory state based on roadmap text alone.

**Acceptance.** Group M implementation has validation evidence on the current host class. `SYSTEM_INVENTORY.md` records only implemented and verified observable artifacts. No Group M closeout claims agent behavior, streaming transport, semantic-memory redesign, model-routing changes, or desktop UI redesign.


---

~~# Group N — Conversation Continuity and Session Memory Boundary~~ Completed

**Why this group exists here.** The realtime session boundary is now verified, but it intentionally owns live event ordering and handoff only. The existing memory foundation is also verified, but it is still bounded working memory plus disk-backed episodic retrieval with recency/keyword lookup. The missing product boundary is the durable continuity layer between those two facts: the system needs explicit session-level context that can make follow-up turns, interruption recovery, and memory writeback decisions without hiding state inside the model or letting later agents invent their own history model.

**Reference inputs.**

- Product direction: `ProjectVision.md` defines a session as a bounded conversational context for continuity, memory policy, and interruption recovery; it also requires externalized cognition, traceable artifacts, and no hidden model state.
- Current capability state: `SYSTEM_INVENTORY.md` records verified Group M realtime event boundary, Slice C turn/session artifacts and working memory, and Slice G episodic retrieval/cache foundations. It also states semantic/vector memory is not implemented and durable memory authority is disk-backed episodic entries, not Redis.
- Current change evidence: `CHANGE_LOG.md` records Group M x64/ARM64 validation and the follow-up realtime event-truth correction; it also records Slice G episodic retrieval and prompt injection behavior.
- Current code anchors: `backend/app/conversation/session_manager.py`, `backend/app/services/session_service.py`, `backend/app/conversation/realtime/session.py`, `backend/app/conversation/realtime/ledger.py`, `backend/app/artifacts/turn_artifact.py`, `backend/app/artifacts/session_artifact.py`, `backend/app/memory/working.py`, `backend/app/memory/write_policy.py`, `backend/app/memory/episodic.py`, `backend/app/memory/retrieval.py`, `backend/app/cognition/prompt_assembler.py`, `backend/app/conversation/engine.py`.
- Planning input: `20260614_slice-n.md` identifies the gap between in-memory realtime session events and memory-backed conversational continuity, and recommends placing this boundary before agents.

**Goal.** Create an explicit continuity and session-memory boundary that persists enough session timeline facts to reconstruct what happened, builds a bounded continuity packet for follow-up turns, supports deterministic interruption recovery context, and feeds prompt assembly without changing tool authority, retrieval authority, runtime selection, or agent behavior.

**Out of scope.**

- Agent framework behavior, planner/executor/critic orchestration, autonomous tool selection, or role contracts.
- Semantic/vector memory, embedding generation, semantic indexing, or autonomous long-term memory decisions.
- Streaming STT, streaming LLM/TTS, VAD endpointing, telephony, WebRTC, or cloud realtime backends.
- Model routing, hardware profiling/provisioning/readiness, STT/TTS/LLM runtime selection, wake runtime replacement, desktop UI redesign, or personality policy changes.
- Storing hidden conversation state inside prompts or model sessions.

**Boundaries.**

- Continuity owns session-level timeline facts, bounded carry-forward context, follow-up classification policy, interruption recovery context, and closeout/writeback eligibility metadata.
- `RealtimeConversationSession` continues to own live invocation events and channel handoff, not durable memory policy.
- `TurnEngine` continues to own committed turn execution, STT, reasoning, tool execution, LLM generation, TTS playback, and `TurnArtifact` creation.
- `SessionManager` continues to own session identity, working memory, turn artifact storage, and session closeout; Group N may extend this boundary only to attach explicit session timeline/continuity artifacts.
- Episodic memory remains disk-backed turn-level memory with policy-gated writes and recency/keyword retrieval; Redis remains retrieval-cache acceleration only.
- Prompt assembly receives continuity as a structured, explicit session context segment; it must not merge continuity into personality, retrieval, tools, or user input.

**Target prompt authority order.**

```text
application rules
personality style
trusted session continuity packet
working memory
retrieved episodic context
tool result context
user request
output contract
```

**Governance recording.**

- Each validated N sub-slice records completed evidence in `CHANGE_LOG.md` before the next N sub-slice begins.
- `SYSTEM_INVENTORY.md` is updated only during N.6 closeout after full Group N validation evidence exists on the required host classes.

## N.0 — Continuity Boundary Census

**Goal.** Establish the repository-accurate ownership map before adding continuity code.

**Scope.** Confirm current ownership for live event ordering, committed turn result, working memory, episodic write/read, retrieved context, session closeout, prompt assembly context ordering, and future semantic write eligibility.

**Primary files.** `backend/app/conversation/session_manager.py`, `backend/app/services/session_service.py`, `backend/app/conversation/realtime/session.py`, `backend/app/conversation/realtime/ledger.py`, `backend/app/artifacts/turn_artifact.py`, `backend/app/artifacts/session_artifact.py`, `backend/app/memory/working.py`, `backend/app/memory/write_policy.py`, `backend/app/memory/episodic.py`, `backend/app/memory/retrieval.py`, `backend/app/cognition/prompt_assembler.py`, `backend/app/conversation/engine.py`.

**Acceptance.** Census identifies what is implemented, what is verified, what is only planned, and which component owns each boundary. It explicitly states that semantic/vector memory, agents, streaming, and hidden model state are not part of Group N.

**Validation.** Documentation-only diff review plus optional baseline targeted tests. Append `CHANGE_LOG.md` after validation evidence exists. Do not update `SYSTEM_INVENTORY.md` in N.0.

---

## N.1 — Durable Session Timeline Artifact

**Goal.** Persist session-level timeline facts without bloating or replacing turn artifacts.

**Scope.** Add or extend a session-level artifact boundary that records ordered session facts by reference: session start, invocation source, user turn committed, linked turn id, assistant response started, speech started only if real playback occurred, interruption detected, recovery, idle, and failure. Keep realtime ledger as the live event source and keep `TurnArtifact` as the committed-turn source.

**Suggested locations.** `backend/app/artifacts/session_timeline.py`, `backend/app/conversation/session_timeline.py`, storage helpers near `backend/app/artifacts/storage.py`, and focused tests under `backend/tests/unit/artifacts/` or `backend/tests/unit/conversation/`.

**Acceptance.** Timeline serialization is deterministic, append-only by sequence, links to turn ids rather than duplicating turn artifact bodies, and records speech events truthfully with degraded TTS paths excluded from speech-start claims.

**Validation.** Focused artifact/timeline unit tests, then `backend/.venv/Scripts/python scripts/validate_backend.py unit`. Append `CHANGE_LOG.md` after validation evidence exists.

---

## N.2 — Continuity Packet

**Goal.** Build a bounded explicit context packet for follow-up turns from current-session facts and existing memory surfaces.

**Scope.** Define a `ContinuityPacket` that can include last user request, last assistant response summary, open topic, pending interruption/correction context, recent turn ids, recent retrieved memory refs, safe carry-forward facts, and excluded or expired context. Source data should come from session timeline, recent turn artifacts, working memory, and existing episodic retrieval outputs.

**Suggested locations.** `backend/app/conversation/continuity.py`, `backend/app/conversation/continuity_packet.py`, and focused tests under `backend/tests/unit/conversation/`.

**Acceptance.** Packet construction is bounded, deterministic, inspectable, and does not mutate memory. It does not perform semantic search, embeddings, autonomous memory decisions, tool calls, or model calls.

**Validation.** Unit tests for packet bounds, empty-session behavior, recent-turn inclusion, interruption context inclusion, and stale/excluded context. Append `CHANGE_LOG.md` after validation evidence exists.

---

## N.3 — Follow-Up and Interruption Recovery Policy

**Goal.** Decide deterministically whether a new turn continues the current conversational context, starts fresh, or enters interruption recovery.

**Scope.** Add policy inputs for time since last turn, same active session, invocation source, last final state, failure reason, interruption flag/events, explicit reset/stop phrases if already present, and whether the prior assistant response was interrupted. Outputs should be small and explicit: continue current session, start new session, recover interrupted response, ignore stale context, or summarize and close.

**Suggested locations.** `backend/app/conversation/continuity_policy.py` and focused tests under `backend/tests/unit/conversation/`.

**Acceptance.** Policy is deterministic and unit tested. The LLM may consume the policy result later, but it does not choose the policy result. Failure and stale-context paths fail closed by excluding unsafe carry-forward context.

**Validation.** Unit tests for same-session follow-up, stale session reset, failed-turn handling, interrupted-response recovery, and explicit reset/stop behavior where supported. Append `CHANGE_LOG.md` after validation evidence exists.

---

## N.4 — Prompt Assembly Integration

**Goal.** Feed the continuity packet into the existing personality prompt envelope without crossing authority boundaries.

**Scope.** Extend prompt assembly to accept optional trusted session continuity context and render it before working memory, retrieved context, tool context, user request, and output contract. Preserve Group L ordering and Group L tool-result placement guarantees.

**Primary files.** `backend/app/cognition/prompt_assembler.py`, `backend/app/cognition/prompt_envelope.py`, `backend/app/cognition/prompt_renderer.py`, `backend/app/conversation/engine.py`, and relevant cognition/conversation tests.

**Acceptance.** Prompt envelope segment order is application -> persona -> trusted session continuity -> working memory -> retrieved context -> tool result -> user request -> output contract. Continuity is explicitly session context, not personality policy, not retrieval, not tool output, and not user input.

**Validation.** Focused prompt assembler/renderer tests and conversation tests proving legacy `system_prompt_addendum` is still not injected and untrusted content remains separated. Append `CHANGE_LOG.md` after validation evidence exists.

---

## N.5 — Session Closeout and Memory Writeback Hook

**Goal.** Provide a conservative closeout boundary for session summaries and future memory curation without implementing semantic memory.

**Scope.** At session closeout, persist summary metadata, linked turn ids, timeline references, interruption/recovery facts, and writeback eligibility markers. Initial writeback should remain policy-gated and conservative: no embeddings, no vector store, no autonomous semantic memory, and no hidden model-generated memory unless explicitly introduced and validated in a later slice.

**Suggested locations.** `backend/app/conversation/session_closeout.py`, `backend/app/memory/write_policy.py`, `backend/app/memory/episodic.py`, `backend/app/artifacts/session_artifact.py`, and focused tests under `backend/tests/unit/conversation/` and `backend/tests/unit/memory/`.

**Acceptance.** Session closeout remains deterministic, links the timeline and turn artifacts, and does not change existing episodic retrieval semantics. Existing episodic write/read and Redis-cached retrieval behavior remain green.

**Validation.** Focused closeout and memory tests, then relevant memory/retrieval tests. Append `CHANGE_LOG.md` after validation evidence exists.

---

## N.6 — Validation and Inventory Closeout

**Goal.** Close Group N with validated continuity behavior and no undocumented capability claims.

**Scope.** Validate that the continuity boundary supports multi-turn follow-up context, stale-context exclusion, interruption recovery context, prompt authority ordering, and existing episodic retrieval behavior without introducing agents, semantic memory, streaming, model routing, or desktop redesign.

**Required validation path.**

- Focused continuity, artifact, cognition, memory, and conversation tests.
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py regression`
- Runtime turn validation where the implementing sub-slices touch live turn behavior.

**Governance closeout.** Append `CHANGE_LOG.md` entries at each validated sub-slice. Update `SYSTEM_INVENTORY.md` only in N.6 after full validation proves an observable conversation continuity and session memory boundary exists. Do not promote inventory state from roadmap text alone.

**Acceptance.**

- A second turn in the same session receives bounded continuity context.
- A new session does not inherit stale continuity context.
- Interrupted response evidence can produce recovery context.
- The continuity packet is visible in artifact or diagnostic evidence.
- Episodic retrieval still works unchanged.
- Prompt envelope authority ordering remains correct.
- No agents, semantic vectors, streaming transport, telephony, model routing, or desktop UI redesign are introduced.

---

# Group O — Agent Framework

**Why this group exists here.** Agents belong after the core loop, tools, memory, acceleration normalization, readiness surfacing, realtime invocation, and session continuity are stable. The agent framework is a role-separated orchestration layer on top of the turn engine, tool registry, memory, prompt envelope, API route, and turn artifact surfaces already proven in C/F/G/L/M/N. Placing it here reduces the risk of agents being built against unstable conversation, memory, readiness, or trace boundaries.

Aligns with the Explicit Cognition Framework principles in `ProjectVision.md`.

Extended implementation slice: `20260615_slice-o.md`.

## O.1 — Agent Role Contracts and Message Schema

**Goal.** Define agent roles, message types, and typed request/response contracts.

**Scope.** Code add: planned `backend/app/agents/` package with role/message contracts. Canonical roles: Planner, Executor, Critic, Curator, Learner. Role configs in `config/agents/roles.yaml`. Role prompts in `config/prompts/agents/`. No execution behavior yet.

**Acceptance.** Unit: message schema validation, role config loading, serialization, and request/response contract surface for all five roles. No live turn integration and no agent execution.

---

## O.2 — Agent Ledger / Artifact Trail

**Goal.** Durable agent records exist for future agent events, plans, outcomes, and policy decisions.

**Scope.** Code add: planned `backend/app/agents/ledger.py` with durable local persistence under `data/agents/`, plus artifact-compatible records for future trace reconstruction. Redis, if used later, is cache-only; durable authority remains local ledger storage. No hidden or background behavior.

**Acceptance.** Unit: records post, query, survive reopen, and reconstruct trace order. No live turn path calls the ledger for hidden work.

---

## O.3 — Agent Policy Gate and API Truth Surface

**Goal.** Agent availability and constraints are explicit, disabled by default, and truthfully reported by the existing backend API surface.

**Scope.** Code add: explicit enabled/disabled status, allowed roles, allowed tools, and truthful API/status response. Extend `config/app/policies.yaml` with agent policy only when implementing Group O. Evolve `backend/app/api/routes/agents.py` and `backend/app/api/schemas/agents.py` from the current disabled read-only status stub. Agents are disabled by default. Normal non-agent turns through `/task/text`, `/task/voice`, and `/session/ptt` remain unchanged.

**Acceptance.** Unit: default disabled/read-only status; allowed roles/tools are reported from policy; enabled status under test policy is truthful; existing task/session API tests remain green.

---

## O.4 — Minimum Truthful Agent Boundary Validation

**Goal.** Prove O.1 through O.3 together before any planner/executor/critic behavior begins.

**Scope.** Validation item: roles/messages exist, ledger/artifact trail exists, policy gate exists, status is truthful, agents do not execute, and normal conversation still works.

**Acceptance.** Focused unit/API/conversation validation passes. `SYSTEM_INVENTORY.md` may add the agent boundary only after this validation passes. No planner, executor, critic, tool-using agent, hidden, or background behavior is claimed.

---

## O.5 — Planner Dry-Run Role

**Goal.** Planner produces a typed plan record without executing tools or altering conversation output.

**Scope.** Code add: planned planner module under `backend/app/agents/` that reads typed requests and writes proposed plan records to the ledger/artifact trail under the O.3 policy gate.

**Acceptance.** Focused validation proves planner records are persisted, policy-gated, dry-run marked, and inventory remains unchanged until behavior exists and passes validation.

---

## O.6 — Executor Dry-Run Tool Boundary

**Goal.** Executor can evaluate planned tool requests against existing deterministic tool boundaries without hidden execution.

**Scope.** Code add: planned executor role module under `backend/app/agents/`. Any tool-capable path must use existing `ToolExecutor` and `ToolRegistry`, must be policy-gated by allowed tools, and must be explicit dry-run until a later approved execution slice.

**Acceptance.** Focused validation proves allowed/blocked tool decisions are truthful, no unregistered tool dispatch occurs, and normal non-agent tool behavior remains unchanged.

---

## O.7 — Critic Dry-Run Review Role

**Goal.** Critic reviews planner/executor records and writes typed review outcomes without controlling final responses.

**Scope.** Code add: planned critic module under `backend/app/agents/` that reads ledger trace records and writes review outcomes, policy decisions, and warnings.

**Acceptance.** Focused validation proves critic review records persist, correlate to a trace, and do not alter non-agent responses unless a later approved orchestration slice enables that behavior.

---

## O.8 — Agent Trace Diagnostics

**Goal.** Read-only trace diagnostics expose existing agent ledger/artifact records without triggering agent work.

**Scope.** Code add: read-only diagnostics in `backend/app/api/routes/agents.py` and `backend/app/api/schemas/agents.py` only after ledger/artifact trace data exists.

**Acceptance.** API tests prove trace-read endpoints return existing records only, never execute agents, and remain truthful when agents are disabled.

---

## O.9 — Curator and Learner Dry-Run Roles

**Goal.** Curator and Learner run end-to-end in dry-run, producing a mixed training dataset and a proposed (not deployed) adapter.

**Scope.** Code add: Curator mines existing turn/session artifacts; Learner produces proposal-only training/evaluation plans. No model training, deployment, adapter loading, model routing, semantic memory, or dependency changes.

**Acceptance.** Focused validation proves curator scoring/dedup and learner proposal-only output. No inventory claim until capability exists and passes validation.

---

## O.10 — Validation and Governance Closeout

**Goal.** Close each Group O capability only after observable behavior is validated and repository truth ledgers are updated with evidence.

**Scope.** Each sub-slice must name the code add and its own validation. Use focused agent/API/conversation tests first, then `backend/.venv/Scripts/python scripts/validate_backend.py unit`, `backend/.venv/Scripts/python scripts/validate_backend.py regression`, and `git diff --check` when implementation requires governance closeout. Update `CHANGE_LOG.md` after each implemented sub-slice validation. Update `SYSTEM_INVENTORY.md` only after an observable agent capability exists and passes validation.

**Acceptance.** Truthful boundary first, then validated optional agent capabilities with non-agent text, voice, session, memory, tool, and realtime behavior unchanged when disabled.

**Finish line.** Agent framework runnable as an optional, policy-gated orchestration layer with persisted role messages, deterministic tool boundaries, reconstructable traces, and unchanged non-agent turns.

---

# Group P — Agent Framework Correction (Agent System)

**Why this group exists here.** Group O created a safe agent boundary, ledger, disabled policy surface, dry-run helpers, and read-only diagnostics, but it also exposed a design gap: agent roles became framework-level Python concepts (`AgentRole` literals, `VALID_AGENT_ROLES`, and hardcoded default role configs). That closes off the future JARVIS goal of user-created agents defined by shared specs. Group P corrects that architecture before any agent runtime behavior is expanded.

Aligns with the Agent Layer and Explicit Cognition Framework principles in `ProjectVision.md`: agents are optional, policy-gated, traceable, and compose the turn engine, tool registry, memory, and LLM runtime without replacing them.

Correction slice: `20260615_slice-p.md`.

**Current repository facts.**
- `SYSTEM_INVENTORY.md` records Group O as a verified minimum truthful agent boundary plus dry-run roles/read-only diagnostics.
- `CHANGE_LOG.md` records x64 validation for O.1-O.10 and ARM64 validation for O.1-O.3.
- Current implementation has hardcoded role IDs in `backend/app/agents/messages.py` and `backend/app/agents/roles.py`.
- Current default roles live in `config/agents/roles.yaml`.
- Current policy/status/ledger surfaces live in `backend/app/agents/policy.py`, `backend/app/agents/ledger.py`, `backend/app/api/routes/agents.py`, and `backend/app/api/schemas/agents.py`.

## P.0 — Agent Spec Framework Correction Census

**Goal.** Establish the exact correction boundary before changing code.

**Scope.** Inspect and map every hardcoded agent-role surface: `backend/app/agents/messages.py`, `backend/app/agents/roles.py`, `backend/app/agents/policy.py`, `backend/app/agents/ledger.py`, `backend/app/api/routes/agents.py`, `backend/app/api/schemas/agents.py`, `config/agents/roles.yaml`, `config/prompts/agents/`, `backend/tests/unit/agents/`, `SYSTEM_INVENTORY.md`, and `CHANGE_LOG.md`.

**Acceptance.** Census identifies which Group O artifacts remain valid boundary infrastructure and which role-specific concepts must become spec-defined data. No code changes. No inventory update from census alone.

---

## P.1 — JarvisAgentSpec Schema and Spec Repository

**Goal.** Add `JarvisAgentSpec` as the single schema for all JARVIS agents.

**Scope.** Code add: planned `backend/app/agents/specs.py` and spec storage under `config/agents/specs/` or a compatible config path. The spec must define stable `spec_id`, display metadata, description, prompt reference, allowed message types, allowed tools, enabled/default-disabled state, ownership/system-vs-user classification, and validation constraints.

**Key correction.** `agent_creator`, `planner`, `executor`, `critic`, `curator`, and `learner` are specs, not privileged framework concepts.

**Acceptance.** Unit tests validate spec schema, duplicate ID rejection, default-disabled behavior, prompt references, and serialization. New agent roles can be added by spec without editing Python role literals.

---

## P.2 — Spec IDs Replace Hardcoded Role Literals

**Goal.** Replace framework-level role literals and `VALID_AGENT_ROLES` with validated spec IDs loaded from the spec repository.

**Scope.** Refactor `backend/app/agents/messages.py`, `backend/app/agents/roles.py`, `backend/app/agents/policy.py`, and related tests so request/message/ledger/status fields accept validated spec IDs rather than a fixed Python `Literal` role set. Preserve existing message contracts, policy gate behavior, ledger behavior, and `/agents/status` truthfulness.

**Boundary rule.** The core system/boundary agent remains separate from user-created JARVIS agents. Boundary/system IDs may be reserved, but user-created IDs come from specs and remain disabled unless policy explicitly allows them.

**Acceptance.** Existing Group O status/ledger tests still pass. Tests prove a new valid spec ID can be loaded and used without Python literal changes, while unknown IDs fail closed through validation/policy.

---

## P.3 — Agent Creator Spec-Only Role

**Goal.** Add the first spec-defined role: `agent_creator`.

**Scope.** Code add: planned `backend/app/agents/creator.py`, `config/agents/specs/agent_creator.yaml`, and `config/prompts/agents/agent_creator.md`. Agent Creator creates and validates agent specs only.

**Must not do.** Agent Creator must not create Python code, write runtime modules, auto-enable agents, execute agents, call tools, change normal conversation behavior, or bypass policy.

**Acceptance.** Unit tests prove Agent Creator can produce one valid disabled `JarvisAgentSpec` for a ProjectVision-aligned role and records the design/creation event in the agent ledger. The produced spec is disabled by default.

---

## P.4 — Convert Group O Default Roles Into Disabled Specs

**Goal.** Demote planner, executor, critic, curator, and learner from framework concepts into disabled default specs.

**Scope.** Convert `config/agents/roles.yaml` semantics into spec files or a spec list. Existing dry-run helper modules may remain implementation helpers, but they must resolve role identity through `JarvisAgentSpec` rather than hardcoded framework role membership.

**Acceptance.** Planner/executor/critic/curator/learner appear as disabled specs by default. Their prior Group O dry-run behavior still validates where applicable, but no spec is auto-enabled and no hidden/background behavior is introduced.

---

## P.5 — Spec-Aware Policy Gate and API Truth Surface

**Goal.** Make policy and status report spec-defined agents truthfully.

**Scope.** Extend the existing policy/status surfaces in `backend/app/agents/policy.py`, `backend/app/api/routes/agents.py`, and `backend/app/api/schemas/agents.py` so allowed roles/tools are derived from policy plus known specs. API diagnostics may list available specs and enabled/disabled state, but must remain read-only unless separately approved.

**Acceptance.** API tests prove `/agents/status` remains truthful, all generated/default specs are disabled by default, policy-allowed specs are reported explicitly, and unknown specs/tools fail closed.

---

## P.6 — Spec Event Ledger Integration

**Goal.** Record spec creation/design/validation events in the existing agent ledger.

**Scope.** Reuse `backend/app/agents/ledger.py` rather than adding a new store. Add record payloads or record types as needed for spec-designed, spec-validated, spec-rejected, and policy-denied events.

**Acceptance.** Unit tests prove Agent Creator and spec validation write reconstructable ledger records. Ledger records do not imply execution and do not enable specs.

---

## P.7 — Validation, Inventory Correction, and Closeout

**Goal.** Close the correction only after the spec-first agent system is validated and repository truth ledgers are accurate.

**Validation path.**
- Focused agent spec/creator/policy/ledger/API tests.
- Existing Group O focused tests that should remain green after refactor.
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py regression`
- `git diff --check`

**Governance closeout.** Append `CHANGE_LOG.md` after validation evidence exists. Update `SYSTEM_INVENTORY.md` only after implementation passes validation, using append-only correction/clarification if existing Group O entries need qualification. Do not rewrite prior history. Do not use `slices.md` as a completion ledger.

**Finish line.** Agent roles are spec-defined; Agent Creator can create valid disabled specs; Group O status/ledger behavior still works; planner/executor/critic/curator/learner are disabled specs, not privileged framework concepts; no autonomous/background execution, tool-using agents, semantic memory, model routing, desktop UI, or normal conversation changes are introduced.

---

# Group Q — Ollama.cpp / Local LLM Runtime

**Why this group exists here.** Local LLM service work has distinct resource and build-environment constraints that must be assessed independently of voice acceleration. The local LLM runtime boundary owns ARM64 memory limits, model quantization choices, and server binary availability so they are evaluated against a mature, stable system rather than folded into the hardware acceleration boundary.

**Local-first preference.** Prefer prebuilt server binaries or existing runtime packages over source-build Docker routes unless source-build is separately proven viable on both host classes.

## Q.0 — Local LLM Viability Census

**Goal.** Non-mutating census: what quantized model formats are available within the ARM64 memory budget; whether a prebuilt local LLM server binary exists for Windows ARM64 without source compilation; what the minimum viable operator setup is.

**Scope.**
- Enumerate available GGUF quantization levels (Q4, Q5, Q8) against ARM64 memory budget.
- Confirm whether `ollama serve` (already operational) is sufficient or whether a separate llama.cpp-compatible server is needed.
- If a prebuilt binary is available for Windows ARM64: document operator install path.
- If source-build is required on ARM64: document as a `Degraded-memory-constrained` or `SKIP-build-toolchain` candidate.
- Census recorded in `CHANGE_LOG.md` before Q.1 begins.

**Acceptance.** Census table produced with close states for both host classes. No code changes.

---

## Q.1 — Local LLM Service + Runtime Adapter

**Depends on:** Q.0 census closes as viable on at least one host class.

**Goal.** Local LLM turn completes via the local runtime; Ollama remains the explicit fallback; selector reports the correct active runtime.

**Scope.**
- Activate `LlamaCppLLM.is_available()` and `generate()` in `backend/app/runtimes/llm/local_runtime.py` (was `NotImplementedError` since B.3).
- Local server endpoint configurable via `.env`; modeled after the Ollama endpoint pattern.
- Selector updated to prefer local → Ollama → cloud per `config/app/policies.yaml`.
- `BackendReadiness.llm_local_ready` and `llm_selected_runtime` populated from real probe evidence.
- ARM64 acceptance: if model runs but is memory-constrained, close Q.1 on ARM64 as `Degraded-memory-constrained` with documented memory parameters. This is a valid closeout state, not a failure.

**Out of scope.** LLM device acceleration belongs to the local LLM runtime boundary as a separate capability decision.

**Acceptance.** Runtime live: turn completes via local LLM on at least x64; Ollama fallback proven. ARM64: `PASS`, `Degraded-memory-constrained`, or `SKIP-no-viable-binary` — all acceptable with documentation.

**Finish line.** Local LLM is the preferred runtime on hosts where it is viable. Ollama remains the reliable fallback everywhere.

---

# Global Acceptance Model

- **Validation hierarchy** (per `ProjectVision.md`): live runtime > capability profile correctness > targeted functional tests > build/test harness results > logs > documentation.
- **Minimum real acceptance per slice**: highest relevant surface green on every host class the slice targets; regression green on both x64 and ARM64.
- **No slice claims completion** without evidence in `SYSTEM_INVENTORY.md` and `CHANGE_LOG.md` with repo-path-accurate Location and Validation fields.
- **Governance docs are not conflated**: `ProjectVision.md` = target state; `SYSTEM_INVENTORY.md` = observable capabilities now; `CHANGE_LOG.md` = completed work with evidence; `slices.md` (this doc) = planned sequencing.

---
