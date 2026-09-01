# 0001 - Know the Machine

## Status

Accepted, living.

## Context

JARVISv7 is a local-first, voice-first assistant that reports hardware and runtime capability from backend-owned host evidence. Runtimes, scripts, desktop surfaces, and model catalogs consume the shared host profile and readiness result.

The first project promise is that the assistant understands the machine before it claims readiness. That includes operating system, architecture, CPU, memory, GPU, CUDA, NPU, installed runtime packages, model artifacts, DLL/provider availability, and selected runtime paths.

## Decision

JARVISv7 centralizes host knowledge in the backend hardware and startup layers, then makes every runtime, setup path, readiness surface, and validation claim consume that shared evidence.

The host capability flow is:

1. `backend/app/hardware/profiler.py` detects host facts and derives broad capability flags.
2. `backend/app/hardware/provisioning.py` maps the detected profile to required dependency extras.
3. `scripts/provision.py` installs or verifies dependencies from `pyproject.toml`.
4. `backend/app/hardware/preflight.py` probes installed imports, execution providers, DLL paths, and runtime prerequisites.
5. `backend/app/hardware/readiness.py` derives selected device readiness for STT, TTS, LLM, and wake.
6. `backend/app/services/startup_context.py` packages profile, extras, preflight, and readiness for backend startup, scripts, diagnostics, and runtime selection.

Runtime families receive selected devices, degraded-state reasons, and readiness evidence from this pipeline.

Future daemon startup and discovery must report this same startup-context truth. A running process will only prove that the daemon is reachable; readiness must still come from profile, provisioning, preflight, and readiness evidence.

## Current Design

`pyproject.toml` is the dependency source of truth. Hardware/runtime extras are declared there, using environment markers where Python packaging can express them. Vendor-specific selection that packaging markers cannot express is resolved by `backend/app/hardware/provisioning.py`.

The backend owns hardware truth:

- `HardwareProfile` records OS, architecture, CPU, memory, GPU, CUDA, NPU, profile ID, and profile timestamp.
- `CapabilityFlags` records broad support such as local STT/TTS/LLM, wake word, desktop shell, CUDA, QNN, DirectML candidate, and degraded-mode requirement.
- The profiler tolerates detector failure by keeping unknown/default facts and reporting degraded evidence.
- Profile IDs are deterministic for the same observed facts, excluding timestamp.

Preflight owns operational proof:

- Import tokens prove installed Python runtime packages.
- Execution-provider tokens prove ONNX Runtime device providers such as CUDA, DirectML, and QNN.
- DLL discovery records Windows CUDA/QNN/OpenCL path setup.
- Probe errors become degraded/readiness evidence with explicit startup status.

Readiness owns selected runtime paths:

- STT can select QNN, CUDA, DirectML, or CPU based on profile and preflight evidence.
- TTS can select CUDA, DirectML, QNN, or CPU based on the same shared evidence.
- Wake is CPU-only and reports unavailable when `openwakeword` is missing.
- LLM local sidecar readiness is catalog/profile driven and reports unavailable or degraded when the selected local runtime path cannot be proven.

Model catalogs may define host-class profiles before validation hardware is available. Such entries must be explicit about their state, using labels such as `validated`, `declared-not-validated`, or `declared-degraded`. Defined-but-unvalidated wiring is allowed when it captures researched configuration, provisioning shape, readiness behavior, fallback behavior, and deterministic skip/degraded reasons.

Validation claims remain narrower than configuration. A host-class path becomes validated only after observable evidence exists from that host class.

Desktop, CLI/script, and future TUI clients display backend readiness, selected accelerators, degraded states, and unavailable reasons from backend APIs.

## Host Classes

The current architecture recognizes host classes through observed profile dimensions. The main supported classes are:

- Windows AMD64
- Windows ARM64
- Linux AMD64

Linux ARM64 and additional accelerator-specific profiles may be defined where the catalog captures researched setup and deterministic unavailable/degraded behavior. Those definitions are framework support, not validation claims.

CPU fallback is part of the design. Accelerator paths degrade to the appropriate CPU or unavailable state when prerequisites are missing.

## Consequences

Benefits:

- Setup, startup, runtime selection, diagnostics, and validation share one host-truth pipeline.
- Dependency selection is reproducible because `pyproject.toml` and the provisioning resolver own install intent.
- Runtime modules remain simpler because they receive selected devices and readiness evidence.
- Unsupported or incomplete host paths can be represented honestly with skip/degraded reasons.
- Future host-class work can be wired before validation hardware is available, while still preventing unsupported evidence claims.

Costs:

- Hardware support requires coordinated changes across profiler, provisioning, preflight, readiness, model catalogs, tests, and docs.
- Catalog entries can become stale if declared-but-unvalidated paths are not revisited.
- Readiness is only as good as the probes; provider availability, DLL discovery, and runtime artifact checks must stay explicit.
- The architecture favors truthful degradation over optimistic startup, so missing dependencies or artifacts may block full readiness even when partial functionality exists.
- A future daemon can simplify client startup while preserving runtime readiness as backend evidence.

## Remaining Work

- Keep researched host-class configurations wired even when validation hardware is unavailable.
- Keep fallback, skip, and degraded reasons deterministic.
- Expand live validation only when matching host hardware exists.
- Define daemon/client startup around backend readiness APIs.

## Implementation Path

Make host/runtime changes through the existing pipeline, in this order:

1. Change dependencies only in `pyproject.toml`.
2. Resolve host-extra selection in `backend/app/hardware/provisioning.py`.
3. Add proof probes in `backend/app/hardware/preflight.py`.
4. Derive selected runtime readiness in `backend/app/hardware/readiness.py`.
5. Surface the result through `backend/app/services/startup_context.py`, diagnostics, readiness, and desktop status.
6. Add focused tests under `backend/tests/unit/hardware/`, `backend/tests/unit/scripts/`, or the existing runtime family test.
7. Add live validation only under `backend/tests/runtime/` when matching hardware is available.

Dependencies: dependency changes begin in `pyproject.toml`; runtime selection changes pass through provisioning, preflight, readiness, and startup context.

Targets: backend hardware modules, setup scripts, model catalogs, diagnostics/readiness routes, desktop status surfaces, and focused tests.

Exit evidence: unit tests for changed profile/provisioning/preflight/readiness behavior, runtime validation only on matching hardware, and validation claims that state host class, command, outcome, and evidence.

## Guidance

When adding or changing hardware/runtime capability:

1. Update `pyproject.toml` dependency groups or hardware extras first when dependencies change.
2. Extend `backend/app/hardware/provisioning.py` only for selection rules that packaging markers cannot express.
3. Add preflight probes for imports, provider tokens, DLL paths, or runtime artifacts needed to prove the path.
4. Derive readiness in `backend/app/hardware/readiness.py`; keep host policy in the hardware/startup layer.
5. Add or update model-catalog host profiles with explicit validation state and degraded/skip reason.
6. Add focused unit coverage for profile/provisioning/preflight/readiness behavior.
7. Add live/runtime validation only for host classes and devices actually available for proof.
8. Report validation claims with exact host class, command, outcome, and evidence.

Keep researched host-class wiring when the current development machine lacks that hardware. Mark validation state accurately and keep fallback behavior deterministic.

When adding daemon/client behavior:

1. Start or discover the backend through the daemon contract, then read readiness from backend APIs.
2. Keep hardware profiling, accelerator selection, and runtime readiness in backend startup layers.
3. Let clients display backend readiness and degraded state.
4. Treat unavailable host-class configurations as declared framework support until validated on matching hardware.

## Evidence

Implementation:

- `backend/app/core/capabilities.py`
- `backend/app/hardware/profiler.py`
- `backend/app/hardware/provisioning.py`
- `backend/app/hardware/preflight.py`
- `backend/app/hardware/qnn_provider.py`
- `backend/app/hardware/readiness.py`
- `backend/app/models/`
- `backend/app/routing/runtime_selector.py`
- `backend/app/services/local_llm_startup.py`
- `backend/app/services/local_llm_sidecar.py`
- `backend/app/services/startup_context.py`
- `backend/app/api/routes/diagnostics.py`
- `backend/app/api/routes/status.py`
- `scripts/bootstrap.py`
- `scripts/provision.py`
- `scripts/ensure_models.py`
- `scripts/run_backend.py`
- `scripts/run_jarvis.py`
- `scripts/validate_backend.py`
- `pyproject.toml`
- `config/models/llm.yaml`
- `config/models/stt.yaml`
- `config/models/tts.yaml`
- `config/models/wake.yaml`
- `backend/app/runtimes/stt/`
- `backend/app/runtimes/tts/`
- `backend/app/runtimes/wake/`
- `runtimes/llama.cpp/`

Tests:

- `backend/tests/unit/hardware/test_profiler.py`
- `backend/tests/unit/hardware/test_provisioning.py`
- `backend/tests/unit/hardware/test_preflight.py`
- `backend/tests/unit/hardware/test_readiness.py`
- `backend/tests/unit/scripts/test_bootstrap_script.py`
- `backend/tests/unit/scripts/test_provision_script.py`
- `backend/tests/unit/scripts/test_ensure_models_script.py`
- `backend/tests/unit/scripts/test_ensure_models_llm_runtime_artifacts.py`
- `backend/tests/unit/scripts/test_run_backend_script.py`
- `backend/tests/unit/scripts/test_run_jarvis_script.py`
- `backend/tests/unit/scripts/test_validate_backend_script.py`
- `backend/tests/runtime/acceleration_matrix/test_acceleration_matrix.py`
