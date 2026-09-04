# 0001 - Know the Machine

Date: 2026-09-01
Status: Implemented
Related: 0002, 0005

## Context and Problem Statement

JARVISv7 is a local-first, voice-first desktop assistant. Before it can select STT, TTS, wake, LLM, desktop, daemon, or validation behavior, it needs one backend-owned account of the host it is running on.

The system needs to know operating system, architecture, CPU, memory, GPU, CUDA, NPU, installed runtime packages, model artifacts, DLL/provider availability, selected runtime paths, and degraded/unavailable reasons. That truth must not be guessed separately by scripts, runtimes, desktop code, or model catalogs.

## Decision Drivers

- Runtime readiness claims must come from observable host evidence.
- Dependency selection must be reproducible from repo-owned metadata.
- Runtime families need selected device/readiness inputs rather than local host-policy branches.
- Desktop and script surfaces need the same backend readiness truth.
- Defined host-class support must distinguish researched configuration from live validation.

## Considered Options

- Let each runtime detect its own hardware and dependency state.
- Put readiness and runtime selection policy in desktop or launch scripts.
- Centralize host profile, provisioning, preflight, readiness, and startup context in the backend.

## Decision Outcome

Chosen option: `Centralize host profile, provisioning, preflight, readiness, and startup context in the backend`.

JARVISv7 centralizes host knowledge in backend hardware and startup layers. Runtimes, setup scripts, diagnostics, readiness APIs, desktop status surfaces, and validation claims consume that shared evidence.

The committed host capability flow is:

1. `backend/app/hardware/profiler.py` detects host facts and derives broad capability flags.
2. `backend/app/hardware/provisioning.py` maps the detected profile to required dependency extras.
3. `scripts/provision.py` installs or verifies dependencies from `pyproject.toml`.
4. `backend/app/hardware/preflight.py` probes installed imports, execution providers, DLL paths, and runtime prerequisites.
5. `backend/app/hardware/readiness.py` derives selected device readiness for STT, TTS, LLM, and wake.
6. `backend/app/services/startup_context.py` packages profile, extras, preflight, and readiness for backend startup, scripts, diagnostics, runtime selection, and client surfaces.

## Consequences

Positive:
- Setup, startup, runtime selection, diagnostics, and validation share one host-truth pipeline.
- Dependency selection is reproducible because `pyproject.toml` and the provisioning resolver own install intent.
- Runtime modules receive selected devices and readiness evidence instead of inventing host policy locally.
- Unsupported or incomplete host paths can be represented honestly with deterministic degraded or unavailable reasons.
- Host-class configuration can exist before live validation hardware is available without turning into a validation claim.

Negative:
- Hardware support requires coordinated changes across profiler, provisioning, preflight, readiness, model catalogs, tests, and docs.
- Readiness quality depends on explicit probes for imports, execution providers, DLL paths, runtime artifacts, and external provider configuration.
- Catalog entries can become stale if declared-but-unvalidated paths are not revisited.
- The architecture favors truthful degradation over optimistic startup, so missing dependencies or artifacts may block full readiness even when partial functionality exists.

## Implementation

`pyproject.toml` is the dependency source of truth. Hardware/runtime extras are declared there with environment markers where packaging can express the rule. Vendor-specific selection that packaging markers cannot express is resolved by `backend/app/hardware/provisioning.py`.

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
- Operator-configured LLM providers can supersede managed local-sidecar catalog readiness; readiness reports that configuration state rather than pretending the catalog applies.

Model catalogs in `config/models/llm.yaml`, `config/models/stt.yaml`, `config/models/tts.yaml`, and `config/models/wake.yaml` carry `validation_status` values such as `validated`, `declared-not-validated`, and `declared-degraded`. Validation claims remain narrower than configuration: a path is validated only after observable evidence exists for that host class/device path.

The current architecture recognizes these main host classes through observed profile dimensions:

- Windows AMD64
- Windows ARM64
- Linux AMD64

Linux ARM64 and additional accelerator-specific profiles may be declared where the catalog captures researched setup and deterministic unavailable/degraded behavior. Those declarations are framework support, not live validation claims.

Backend API and client surfaces consume this backend-owned truth:

- `backend/app/api/app.py` builds startup state from `load_startup_context()`, then selects STT, TTS, wake, and LLM runtimes from that state.
- `/diagnostics/profile`, `/diagnostics/preflight`, `/readiness`, `/status/desktop`, `/status/wake`, and `/daemon/status` expose profile, readiness, degraded state, and daemon identity without moving runtime selection policy into clients.
- `scripts/run_backend.py`, `scripts/run_jarvis.py`, `scripts/bootstrap.py`, `scripts/provision.py`, `scripts/ensure_models.py`, and `scripts/validate_backend.py` use the same backend/source-of-truth model.
- `desktop/src/components/readiness-panel.js`, `desktop/src/api-client.js`, and `desktop/src-tauri/src/backend.rs` display and transport backend readiness rather than profiling hardware independently.

## Confirmation

Implementation files:
- `backend/app/core/capabilities.py`
- `backend/app/hardware/profiler.py`
- `backend/app/hardware/provisioning.py`
- `backend/app/hardware/preflight.py`
- `backend/app/hardware/qnn_provider.py`
- `backend/app/hardware/readiness.py`
- `backend/app/models/`
- `backend/app/routing/runtime_selector.py`
- `backend/app/services/startup_context.py`
- `backend/app/services/local_llm_startup.py`
- `backend/app/services/local_llm_sidecar.py`
- `backend/app/api/app.py`
- `backend/app/api/routes/diagnostics.py`
- `backend/app/api/routes/readiness.py`
- `backend/app/api/routes/status.py`
- `backend/app/api/routes/daemon.py`
- `config/models/llm.yaml`
- `config/models/stt.yaml`
- `config/models/tts.yaml`
- `config/models/wake.yaml`
- `pyproject.toml`
- `scripts/bootstrap.py`
- `scripts/provision.py`
- `scripts/ensure_models.py`
- `scripts/run_backend.py`
- `scripts/run_jarvis.py`
- `scripts/validate_backend.py`
- `desktop/src/components/readiness-panel.js`
- `desktop/src/api-client.js`
- `desktop/src-tauri/src/backend.rs`

Test coverage:
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

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py profile`
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families ... --devices ...` for live host/device validation claims

## Follow-up

None for this ADR.

Future host classes, new accelerators, new runtime families, or changes to validation semantics should update this ADR when they preserve the same architecture, or create/supersede an ADR when they change the architecture.
