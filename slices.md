
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
  H.2  ARM64 QNN prerequisite gate (QNN provider/HTP discovery + proven QNN-compatible Whisper artifact path)
  H.3  ARM64 QNN STT activation
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

Group L — Agent Framework

Group M — Ollama.cpp / Local LLM Runtime
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
- NPU vendor detection must distinguish Qualcomm (QNN target), Intel (future DirectML/OpenVINO target), AMD (future ROCm target), and unknown; the profiler never guesses vendor from OS alone.
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
- NPU vendor gating cannot use PEP 508 markers; the resolver must make the call. Document this split clearly so no future maintainer tries to move it into markers.

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

**Why here.** Carry QNN as a first-class definition from day one so later activation is pure wiring. Defining it here forces every runtime family in B to treat `qnn` as one of the device values it must accept.

**Goal.** Activating QNN later (in H.2) requires no manifest / extra / flag / token / schema changes — only runtime code and a quantized model.

**Scope.**
- `hw-npu-qualcomm-qnn` extra in `pyproject.toml`, applied by the resolver on Qualcomm NPU hosts.
- Packages: `onnxruntime-qnn>=2.0.0` (PyPI Windows ARM64 wheels confirmed for CPython 3.11/3.12/3.13).
- Evidence tokens added to `resolve_backend_evidence_tokens()`: `import:onnxruntime-qnn`, `ep:QNNExecutionProvider`, `dll:QnnHtp` — all returning "defined but not wired" until H.2.
- `CapabilityFlags.qnn_available` set from NPU vendor detection.
- `qnn` accepted as a valid `selected_device` value in STT readiness; selector emits a clear "defined, inference pending H.2" reason and refuses to select it for actual work.
- Operator prerequisites documented in `.env.example` and `config/hardware/notes.md`: QAIRT SDK install path, backend `.dll` location.

**Out of scope.** Inference code. Quantized model catalog entries (placeholder only). All deferred to H.2.

**Boundaries.**
- Owns: the extra entry, token definitions, the `qnn_available` flag, documentation.
- Must not touch: runtime implementations.

**Key design decisions.**
- Define the slot, not the implementation — prevents the "QNN as retrofit" failure mode without blocking on SDK availability or hardware access.
- Quantization tooling notes included in `config/hardware/notes.md`: per ORT QNN docs the `onnx` package has ARM64 install issues, so quantization runs on x64; this is documented as a future operator workflow, not a blocker here.

**Acceptance.** Unit tests confirm Qualcomm host synthetic profiles produce the expected "defined but not wired" readiness claims.

**Finish line.** QNN is present in the architecture as a slot every later decision is aware of.

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
- Secondary runtime: `onnx-asr` (`istupakov/onnx-asr`). Supports Windows/Linux/macOS on x86/Arm CPUs with CUDA/TensorRT/CoreML/DirectML/ROCm/WebGPU backends per its PyPI listing. Kept behind a runtime flag for non-Whisper model families (Parakeet/Canary/NeMo), lower-latency streaming scenarios, and future non-English coverage.
- Selector in `backend/app/runtimes/stt/stt_runtime.py` dispatches on `(runtime_family, device)` from profiler/readiness output.
- Catalog entries in `config/models/stt.yaml`:
  - `whisper-small-onnx` (CPU/CUDA/DirectML).
  - `whisper-small-onnx-qnn-qdq` (placeholder; artifact acquired in H.2).
  - One Parakeet-family ONNX model for the `onnx-asr` path.
- Cache keying is `(runtime_family, model_name, device)` so runtimes never collide in cache.

**Out of scope.** QNN inference (H.2). QNN-target quantization tooling (H.2). Streaming partial transcripts (future polish).

**Assumptions.**
- ONNX Whisper `small` is available on HuggingFace in a layout compatible with `onnxruntime`.
- `onnx-asr` installs cleanly on both x64 and ARM64 with its stated dependency bounds.
- `onnxruntime-directml` wheels available for target CPython versions on Windows GPU hosts.

**Boundaries.**
- Owns: `backend/app/runtimes/stt/{base.py, onnx_whisper_runtime.py, onnx_asr_runtime.py, stt_runtime.py, barge_in.py}`, `config/models/stt.yaml`.
- Must not touch: TTS, LLM, wake, services.

**Key design decisions.**
- One ONNX Whisper runtime file holds all device branches; `faster-whisper` is not included in the base strategy (may be added later as a second runtime if ONNX coverage proves insufficient for a specific need, but it is not default).
- Selector refuses to pick an unready device with a clear reason rather than falling through silently.
- `onnx-asr` is present from day one, not deferred, because bringing it in later is more work than defining its slot now.

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
- PyTorch-based Kokoro is not default (x64-only path). If future need arises it can be added as a second runtime on x64, but single-stack is the goal.
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
- Custom "jarvis"-only training (no "hey" prefix) is deferred future polish. Documented as a Linux/WSL/Colab operator task per openWakeWord's notebook ("automated model training is only supported on linux systems due to the requirements of the text to speech library used for synthetic sample generation (Piper)"). Trained `.onnx` output is arch-independent.

**Out of scope.** Training custom openWakeWord models. NPU-accelerated wake (wake runs on CPU for both providers).

**Assumptions.**
- openWakeWord v0.5.1 release asset URLs remain reachable.
- `pvporcupine` installs cleanly on Windows ARM64 when the optional extra is selected (validate at extra installation time).

**Boundaries.**
- Owns: `backend/app/runtimes/wake/{base.py, openwakeword_runtime.py, porcupine_runtime.py, wake_runtime.py}`, `config/models/wake.yaml`.

**Key design decisions.**
- openWakeWord default because arch-independence + pre-trained `hey_jarvis` gives the best baseline UX with no operator setup.
- Porcupine kept as an optional alternative because its dev-tier single-keyword limit doesn't fit a primary multi-keyword surface but may be right for specific deployments.
- Custom-keyword training deferred — not a precondition for any C–H slice.

**Acceptance.**
- Unit: selector dispatch; runtime fail-closed when models missing.
- Runtime live: openWakeWord detects "hey jarvis" on both host classes. Porcupine runtime smoke-tested when `hw-wake-porcupine` extra is installed.

**Finish line.** Wake detection works out-of-box on both host classes via openWakeWord. Porcupine available as drop-in when the extra is installed.

**Risks.**
- openWakeWord false-reject rate in noisy environments may push users toward custom verifier models later; that path is documented but not required.

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

**Out of scope.** Wake-during-speech (future polish).

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

**Risks.** Wake concurrent with SPEAKING (barge-by-wake) — out of scope for this slice; documented as future polish.

---

## D.5 — Personality / Presence Polish

**Goal.** Personality profile switch is visible in the shell and reflected in the next turn's response style.

**Scope.**
- Personality shaping controls in shell (profile picker).
- Assistant presence behaviors (acknowledgment phrases, response pacing hints consumed by TTS).
- Overlay / ambient presence patterns defined in `docs/` but implementation deferred.

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
- Tool contract supports arbitrary future tool addition without redesign.
- Tool invocations explicit and logged; no hidden side effects.

**Boundaries.**
- Owns: `backend/app/tools/**`.

**Key design decisions.**
- Filesystem tool is read-only at this slice's scope. Write tools are a separate future decision with their own policy gates.
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

**Out of scope.** Semantic memory (future). Cross-session summarization beyond recency-based recall.

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

# Group H — Voice Acceleration

**Why this group exists here.** Voice acceleration (STT/TTS on GPU/NPU) belongs after the core loop, tools, memory, and episodic retrieval are stable. Acceleration work at this stage is a clean device-branch substitution inside already-proven runtime families — not new architecture. Local LLM service work is deferred to Group M because it has distinct resource and build constraints that must be assessed independently after acceleration is proven.

**Voice-first ordering.** H works only on STT and TTS device uplift. LLM runtime selection (Ollama) is unchanged. Wake remains CPU-only.

**Viability-gate discipline.** Each acceleration variant (QNN, CUDA, DirectML) begins with a non-mutating viability gate that produces documented evidence before any wiring code is written. An unproven host or missing prerequisite closes as `SKIP-no-host`, `SKIP-prereq-missing`, or `Deferred` — never as `BLOCKED-*`.

**Close states for hardware/provider sub-slices:**
- `PASS` — proven on the target host with the target device
- `SKIP-no-host` — no host with the required hardware was available
- `SKIP-prereq-missing` — required SDK, DLL, or package not present; not a blocker if clearly documented
- `Deferred` — capability is defined and slotted; activation explicitly moved to a named later sub-slice
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

**Why here.** QNN slot was defined in A.6. Before activation code is written, QNN prerequisite enablement must be proven: provider/plugin discovery, HTP backend discovery, and a proven QNN-compatible Whisper artifact/runtime contract path.

**Goal.** Confirmed: QAIRT SDK installed, `QnnHtp.dll` discoverable, and a proven QNN-compatible Whisper artifact/runtime contract (for example `whisper-small-qnn-qdq`, QNN-compatible QDQ artifact, or precompiled QNN ONNX artifact) is available for ARM64 QNN STT.

**Scope.**
- Non-mutating verification: `QAIRT_SDK_PATH` set, DLL probe succeeds, `onnxruntime-qnn` imports on ARM64.
- QNN-compatible artifact acquisition/build and proof path must be documented and must establish compatibility before activation.
- If any prerequisite is missing: close H.2 as `SKIP-prereq-missing` with an explicit checklist of what is missing. H.3 cannot start until H.2 closes as `PASS`.

**Acceptance.** Gate closes as `PASS` (all prerequisites confirmed) or `SKIP-prereq-missing` (missing items documented). `BLOCKED-*` is not an acceptable state.

---

## H.3 — ARM64 QNN STT Activation

**Depends on:** H.2 `PASS`.

**Goal.** Voice turn on the Qualcomm ARM64 host completes with `selected_device="qnn"` for STT. CPU-EP regression still green on the same host.

**Scope.**
- Activate QNN STT by loading the proven artifact from H.2 and selecting QNN only when readiness and artifact proof are both present.
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
- If H.5 was `SKIP-*`: H.6 closes as `Deferred` without any code change.

**Acceptance.** Runtime live with DirectML device on proven host, or `Deferred` if H.5 was `SKIP-*`.

---

## H.7 — TTS Acceleration Viability / Device Slot Normalization

**Goal.** TTS device options normalized alongside STT. CPU proven on both hosts. CUDA/DirectML where H.4/H.6 proved viable. QNN TTS explicitly deferred.

**Scope.**
- TTS CPU live test reconfirmation on both host classes.
- TTS CUDA / DirectML branches activated where the corresponding STT gate (H.4 / H.6) proved the EP.
- QNN TTS: explicitly `Deferred` — no verified Kokoro HTP quantization exists. Document in `config/hardware/notes.md`.

**Acceptance.** TTS CPU `PASS` on both hosts. Acceleration variants `PASS` or `Deferred` with reason.

---

## H.8 — Voice Acceleration Live Turn Matrix

**Goal.** All H sub-slices reconciled into a recorded `(family × device × host_class)` state table. No `BLOCKED-*` cells at closeout.

**Scope.**
- Run `validate_backend.py matrix` on both host classes.
- Every cell is `PASS`, `SKIP-*`, or `Deferred`. Any `FAIL` blocks Group H closeout.
- Matrix recorded in `SYSTEM_INVENTORY.md` as the Group H gate entry.

**Acceptance.** Matrix green on both host classes (allowing SKIP/Deferred cells with reasons). Regression ≥ 96.

**Finish line.** Group I hardware-path normalization may begin.

---

# Group I — Hardware Path Normalization

**Why this group exists here.** Group H produces evidence of what actually works per device per host class. Group I consumes that evidence to normalize the selector, readiness deriver, and preflight reporting into coherent, documented acceleration paths for both host classes. Future hardware variants (Intel NPU, additional AMD GPUs) are represented as defined-but-deferred slots following the A.6 / H.2 pattern — not over-built.

## I.1 — ARM Acceleration Sequence Normalization

**Goal.** ARM64 path fully documented and normalized: CPU → QNN (if H.3 passed) → fallback chain. Selector and readiness deriver reflect the proven evidence from H.

**Scope.**
- Normalize `derive_stt_device_readiness()` and `derive_tts_device_readiness()` to prefer QNN when H.3 proved it, fall back to CPU cleanly.
- Intel NPU (future) and other ARM NPU variants represented as defined-but-deferred slots.
- No new runtime families; this is selector and readiness normalization only.
- Document the ARM64 path in `config/hardware/notes.md`.

**Acceptance.** Unit: ARM64 readiness derivation correct for all acceleration states from H. Runtime live: ARM64 host selects the best proven device and falls back cleanly.

---

## I.2 — x64 Acceleration Sequence Normalization

**Goal.** x64 path fully normalized: CPU → CUDA (if H.4 passed) → DirectML (if H.6 passed) → fallback chain.

**Scope.**
- Normalize x64 readiness derivers to prefer CUDA → DirectML → CPU in documented order.
- Non-NVIDIA GPU variants (Intel iGPU, AMD without DirectML) represented as defined-but-deferred slots.
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

# Group J — Runtime/Readiness UX + Degraded-State Surfacing

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

# Group K — UI Controls + Operator Settings

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

# Group L — Agent Framework

**Why this group exists here.** Agents belong after the core loop, tools, memory, acceleration normalization, readiness surfacing, and UI controls are stable. The agent framework is a role-separated orchestration layer on top of the turn engine, tool registry, memory, and turn artifacts already proven in C/F/G/H/I. Placing it here reduces the risk of agents being built against an unstable acceleration or readiness surface.

Aligns with the Explicit Cognition Framework principles in `ProjectVision.md`.

## L.1 — Agent Role Contracts + Typed Message Protocol

**Goal.** Five canonical agent roles with stable input/output schemas and a typed message protocol.

**Scope.** Canonical roles: Planner, Executor, Critic, Curator, Learner. Typed `AgentMessage` protocol. Role configs in `config/agents/roles.yaml`. Role system prompts in `config/prompts/agents/`.

**Acceptance.** Unit: message schema validation + role contract surface for all five roles.

---

## L.2 — Agent Ledger

**Goal.** Persisted, queryable, restart-surviving message substrate for agent coordination.

**Scope.** `backend/app/agents/ledger.py` — SQLite-backed. E.2 Redis used for caching; Redis-unavailable falls back to direct SQLite. Trace IDs connect a goal through the role chain.

**Acceptance.** Unit + runtime live: messages post, query, survive restart; trace assembly works.

---

## L.3 — Planner + Executor + Critic on Live Path

**Goal.** A multi-step request completes via Planner → Executor → Critic with all messages in the ledger and a full trace reconstructable.

**Scope.** Turn engine consults `config/app/policies.yaml` for agent-opt-in. Non-agent turns continue to work unchanged. Agent decisions in turn artifacts via the optional `agent_trace` field.

**Acceptance.** Runtime live: multi-step request completes via full planner → executor → critic chain.

---

## L.4 — Curator + Learner Roles

**Goal.** Curator and Learner run end-to-end in dry-run, producing a mixed training dataset and a proposed (not deployed) adapter.

**Scope.** Curator mines turn artifacts; Learner orchestrates training cycle gated by regression suite. Regression gate (`validate_backend.py regression`) is non-negotiable before any adapter deploys.

**Acceptance.** Unit: curator scoring + dedup. Runtime live: dry-run cycle produces a mixed dataset.

**Finish line.** Agent framework runnable end-to-end as an optional orchestration layer. Non-agent turns unchanged.

---

# Group M — Ollama.cpp / Local LLM Runtime

**Why this group exists here.** Local LLM service work has distinct resource and build-environment constraints that must be assessed independently of voice acceleration. Deferring to M ensures that ARM64 memory limits, model quantization choices, and server binary availability are evaluated against a mature, stable system — not retrofitted into Group H.

**Local-first preference.** Prefer prebuilt server binaries or existing runtime packages over source-build Docker routes unless source-build is separately proven viable on both host classes.

## M.0 — Local LLM Viability Census

**Goal.** Non-mutating census: what quantized model formats are available within the ARM64 memory budget; whether a prebuilt local LLM server binary exists for Windows ARM64 without source compilation; what the minimum viable operator setup is.

**Scope.**
- Enumerate available GGUF quantization levels (Q4, Q5, Q8) against ARM64 memory budget.
- Confirm whether `ollama serve` (already operational) is sufficient or whether a separate llama.cpp-compatible server is needed.
- If a prebuilt binary is available for Windows ARM64: document operator install path.
- If source-build is required on ARM64: document as a `Degraded-memory-constrained` or `SKIP-build-toolchain` candidate.
- Census recorded in `CHANGE_LOG.md` before M.1 begins.

**Acceptance.** Census table produced with close states for both host classes. No code changes.

---

## M.1 — Local LLM Service + Runtime Adapter

**Depends on:** M.0 census closes as viable on at least one host class.

**Goal.** Local LLM turn completes via the local runtime; Ollama remains the explicit fallback; selector reports the correct active runtime.

**Scope.**
- Activate `LlamaCppLLM.is_available()` and `generate()` in `backend/app/runtimes/llm/local_runtime.py` (was `NotImplementedError` since B.3).
- Local server endpoint configurable via `.env`; modeled after the Ollama endpoint pattern.
- Selector updated to prefer local → Ollama → cloud per `config/app/policies.yaml`.
- `BackendReadiness.llm_local_ready` and `llm_selected_runtime` populated from real probe evidence.
- ARM64 acceptance: if model runs but is memory-constrained, close M.1 on ARM64 as `Degraded-memory-constrained` with documented memory parameters. This is a valid closeout state, not a failure.

**Out of scope.** LLM device acceleration (separate future decision).

**Acceptance.** Runtime live: turn completes via local LLM on at least x64; Ollama fallback proven. ARM64: `PASS`, `Degraded-memory-constrained`, or `SKIP-no-viable-binary` — all acceptable with documentation.

**Finish line.** Local LLM is the preferred runtime on hosts where it is viable. Ollama remains the reliable fallback everywhere.

---

# Global Acceptance Model

- **Validation hierarchy** (per `ProjectVision.md`): live runtime > capability profile correctness > targeted functional tests > build/test harness results > logs > documentation.
- **Minimum real acceptance per slice**: highest relevant surface green on every host class the slice targets; regression green on both x64 and ARM64.
- **No slice claims completion** without evidence in `SYSTEM_INVENTORY.md` and `CHANGE_LOG.md` with repo-path-accurate Location and Validation fields.
- **Governance docs are not conflated**: `ProjectVision.md` = target state; `SYSTEM_INVENTORY.md` = observable capabilities now; `CHANGE_LOG.md` = completed work with evidence; `slices.md` (this doc) = planned sequencing.

---
