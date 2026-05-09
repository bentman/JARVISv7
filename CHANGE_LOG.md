# CHANGE_LOG.md
> :
> No edits/reorders/deletes of past entries. If an entry is wrong, append a corrective entry.

## Rules
- Write an entry only after task objective is “done” and supported by evidence.
- **Ordering:** Entries are maintained in **descending chronological order** (newest first, oldest last).
- **Append location:** New entries must be added **at the top of the Entries section**, directly under `## Entries`.
- Each entry must include:
  - Timestamp: `YYYY-MM-DD HH:MM`
  - Summary: 1–2 lines, past tense
  - Scope: files/areas touched
  - Host class(es): validated on (e.g., `Windows x64`, `Windows ARM64`, or both)
  - Evidence: exact command(s) run + a minimal excerpt pointer (or embedded excerpt ≤10 lines)
- If a change is reverted, append a new entry describing the revert and why.

---

## Entries

- 2026-05-09 18:58
  - Summary: Fixed `scripts/provision.py verify` false missing-package drift by applying consistent canonical package-name normalization for expected and installed requirement names.
  - Scope: `scripts/provision.py`, `backend/tests/unit/scripts/test_provision_script.py`
  - Host class(es): Windows ARM64
  - Evidence: Pre-changelog status `git status --short` showed only `M backend/tests/unit/scripts/test_provision_script.py` and `M scripts/provision.py`; `backend\.venv\Scripts\python scripts\provision.py verify` PASS with no `missing` output; `backend\.venv\Scripts\python -m pytest backend/tests/unit/scripts/test_provision_script.py -q` PASS (`6 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`102 passed, 3 deselected`).

- 2026-05-07 19:22
  - Summary: Windows x64 H.2 live-gate collection behavior was corrected by removing module-scope `onnx` import from `backend/tests/runtime/hardware/test_qnn_gate_live.py` and moving `onnx` imports into ONNX-dependent helper execution paths so ARM64/live/QNN gating can skip correctly on x64 during collection. H.2 strict proof semantics were preserved (CPU fallback disabled, QNN primary-provider assertion, EPContext diagnostics, helper/direct comparison diagnostics).
  - Scope: `backend/tests/runtime/hardware/test_qnn_gate_live.py`
  - Host class(es): Windows x64
  - Evidence: `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`101 passed, 3 deselected in 0.91s`); `backend\.venv\Scripts\python -m pytest backend/tests/runtime/hardware/test_qnn_gate_live.py -q` PASS (`3 skipped in 0.57s`); `backend\.venv\Scripts\python -m pytest backend/tests/unit/hardware/test_qnn_prerequisite.py backend/tests/unit/hardware/test_qnn_slot.py -q` PASS (`11 passed in 0.02s`).
  - Note: This entry records only the x64 collection/skip fix and does not claim H.3 work.

- 2026-05-07 15:05
  - Summary: Final H.2 corrective/pass was completed on Windows ARM64: the H.2 live-gate provider assertion was corrected from an exact-provider-list requirement to a primary-provider requirement, matching ONNX Runtime provider-priority semantics. H.2 QNN prerequisite/live gate is now PASS with CPU fallback still disabled, QNN primary for encoder/decoder, and regression remained PASS; H.3 may resume.
  - Scope: `pyproject.toml`, `scripts/validate_backend.py`, `backend/app/hardware/qnn_provider.py`, `backend/app/runtimes/stt/onnx_whisper_runtime.py`, `backend/tests/runtime/hardware/test_qnn_gate_live.py`, `backend/tests/unit/hardware/test_qnn_prerequisite.py`, `backend/tests/unit/hardware/test_qnn_slot.py` (preserved intact), `backend/tests/runtime/hardware/test_qnn_session_init_live.py` (removed)
  - Host class(es): Windows ARM64
  - Evidence: `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`101 passed, 3 deselected in 2.08s`); `$env:JARVISV7_LIVE_TESTS="true"; backend\.venv\Scripts\python -m pytest backend/tests/runtime/hardware/test_qnn_gate_live.py -q -s` PASS (`3 passed in 2.74s`); direct providers logged as encoder/decoder `['QNNExecutionProvider', 'CPUExecutionProvider']`, helper path methods logged as `add_provider_for_devices` for encoder/decoder with the same provider ordering, and corrected H.2 proof accepted QNN as primary provider with CPU fallback disabled.
  - Note: This entry records H.2 completion only and does not claim H.3 transcript activation or H.3 completion.

- 2026-05-07 12:19
  - Summary: Corrective H.2 test-surface alignment entry appended to correct the prior `2026-05-05 12:30` record mismatch between H.2-required runtime/unit test surfaces and substituted files. Runtime and unit H.2 surfaces were corrected without claiming H.2 proof or H.3 activation.
  - Scope: `CHANGE_LOG.md` (corrective entry only); corrected test surfaces referenced: `backend/tests/runtime/hardware/test_qnn_gate_live.py` (added), `backend/tests/runtime/hardware/test_qnn_session_init_live.py` (removed), `backend/tests/unit/hardware/test_qnn_prerequisite.py` (added), `backend/tests/unit/hardware/test_qnn_slot.py` (preserved intact)
  - Host class(es): Windows ARM64
  - Evidence: Runtime H.2 live gate correction status recorded against prior `2026-05-05 12:30`: stale substituted `test_qnn_session_init_live.py` removed and slice-aligned `test_qnn_gate_live.py` added; live gate exists and ran, but strict QNN artifact/session proof remains FAIL with CPU fallback disabled, therefore H.2 is not proven and H.3 may not resume. Unit H.2 prerequisite correction evidence: `backend\.venv\Scripts\python -m pytest backend/tests/unit/hardware/test_qnn_prerequisite.py -q` PASS (`3 passed in 0.02s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`101 passed, 3 skipped in 2.07s`). Current validation for this corrective log update: `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`101 passed, 3 skipped in 2.07s`); `git status --short` shows `D backend/tests/runtime/hardware/test_qnn_session_init_live.py`, `?? backend/tests/runtime/hardware/test_qnn_gate_live.py`, `?? backend/tests/unit/hardware/test_qnn_prerequisite.py`, and `M CHANGE_LOG.md`.

- 2026-05-07 20:01
  - Summary: H.3 QNN STT follow-up corrections were completed on Windows ARM64 by aligning the QNN precompiled model catalog and runtime file expectations with the extracted artifact layout, wiring QNN runtime dispatch, updating STT QNN readiness selection, adjusting validator readiness summary derivation to selected-path relevance without suppressing diagnostics, and updating the superseded QNN readiness unit assertion/test name. A scoped cleanup also updated the deferred transcription message to H.3.2 and set the QNN model catalog runtime key to `qnn_whisper`.
  - Scope: `config/models/stt.yaml`, `backend/app/runtimes/stt/onnx_whisper_runtime.py`, `backend/app/runtimes/stt/stt_runtime.py`, `backend/app/hardware/readiness.py`, `scripts/validate_backend.py`, `backend/tests/unit/hardware/test_qnn_slot.py`
  - Host class(es): Windows ARM64
  - Evidence: `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only --family stt` PASS (`"whisper-tiny-qnn-precompiled-snapdragon-x-elite" missing=[] ready=true` with nested present paths including `.../encoder.onnx` and `.../decoder.onnx`); `backend\.venv\Scripts\python -c "from backend.app.runtimes.stt.onnx_whisper_runtime import QnnWhisperRuntime; r=QnnWhisperRuntime(model_name='whisper-tiny-qnn-precompiled-snapdragon-x-elite'); print('is_available=', r.is_available())"` PASS (`is_available= True`); `backend\.venv\Scripts\python -c "... select_stt_runtime ...; print(type(runtime).__name__, runtime.device)"` PASS (`QnnWhisperRuntime qnn`); `backend\.venv\Scripts\python -c "... derive_stt_device_readiness ...; print(...)"` PASS (`('qnn', True, 'qnn prerequisites proven; selecting qnn')`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\hardware\test_qnn_slot.py -q` PASS (`8 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py profile` PASS with fingerprint readiness `ready; tokens=19`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`98 passed, 1 skipped in 2.11s`).

- 2026-05-05 12:30
  - Summary: Sub-Slice H.3 QNN STT Runtime Implementation Enablement - fixing the QNN plugin discrepancy between repo implementation and the external TempTransfers/ARM64-QNN reference. A hybrid QNN provider initialization strategy was implemented that passes `backend_path` in `provider_options` to `InferenceSession()`, enabling sessions to load successfully with the plugin installed outside the repo. New `backend/app/hardware/qnn_provider.py` module added with `get_qnn_provider_options()` and `create_qnn_session()` helpers; `QnnWhisperRuntime` class added for QNN-accelerated STT with encoder/decoder session initialization; preflight probe updated to capture QNN library path token; test updated to use new provider helper; and two unrelated failing tests fixed (LLM error message match, path handling in ensure_models verification).
  - Scope: `backend/app/hardware/qnn_provider.py` (new), `backend/app/hardware/preflight.py`, `backend/app/runtimes/stt/onnx_whisper_runtime.py`, `backend/tests/runtime/hardware/test_qnn_session_init_live.py`, `backend/tests/unit/runtimes/llm/test_llm_runtime.py`, `scripts/ensure_models.py`, `config/models/stt.yaml`
  - Host class(es): Windows ARM64
  - Evidence: `backend\.venv\Scripts\python scripts\validate_backend.py profile` PASS with fingerprint `arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=degraded`; `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`324 passed in 1.16s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`96 passed`); `$env:JARVISV7_LIVE_TESTS='1'; backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt --devices cpu` PASS (`4 passed, 1 skipped, 20 deselected in 29.71s`); `$env:JARVISV7_LIVE_TESTS='1'; backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt --devices qnn` PASS (`1 skipped, 24 deselected in 0.80s`). QNN session init test skipped due to missing QAIRT SDK readiness (expected on non-Snapdragon hosts without plugin); CPU STT paths remain green and functional; full QNN transcription inference deferred to H.3.2 implementation scope.
  - Note: `create_qnn_session()` implements hybrid strategy: attempts `SessionOptions.add_provider_for_devices()` first (preferred), falls back to provider list with explicit `backend_path` in `provider_options` (external plugin pattern). Encoder/decoder sessions load via QNN provider with CPU fallback disabled; sessions auto-cleanup (unregister) after creation. `QnnWhisperRuntime` proof-validates session initialization; full transcription (audio preprocessing, tokenization, decoder loop) deferred to H.3.2. Existing CPU STT, CUDA STT (x64), and DirectML STT behaviors preserved; no model export/download/mutation, no API/schema changes, no desktop/shell rendering, and no Group I agent behavior introduced.


- 2026-05-03 19:54
  - Summary: Sub-Slice H.2 (ARM64 QNN Prerequisite Gate) was closed as prerequisite enablement only. ARM64 QNN ONNX Runtime ownership/provisioning was corrected enough for `onnxruntime-qnn` presence, QNN preflight discovery was updated for ONNX Runtime QNN 2.x plugin behavior, and profile evidence now reports plugin/library/HTP/EP-device prerequisites as proven. A QNN-targeted quantized Whisper catalog placeholder was added for H.3 handoff without claiming artifact presence.
  - Scope: `backend/app/hardware/preflight.py`, `backend/tests/unit/hardware/test_qnn_slot.py`, `pyproject.toml`, `backend/app/hardware/provisioning.py`, `backend/tests/unit/hardware/test_provisioning.py`, `scripts/provision.py`, `config/models/stt.yaml`
  - Host class(es): Windows ARM64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\hardware -q` PASS (`46 passed`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\runtimes\stt\test_stt_runtime.py -q` PASS (`10 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py profile` PASS with fingerprint `arch=arm64` and readiness `ready`, tokens including `import:onnxruntime-qnn`, `qnn:plugin_library`, `qnn:htp_path`, `dll:QnnHtp`, `ep:QNNExecutionProvider`, `qnn:ep_device`; `$env:JARVISV7_LIVE_TESTS='1'; backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt --devices cpu` PASS (`4 passed, 20 deselected, 1 warning`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`96 passed`). Plugin probe evidence: `onnxruntime_qnn\onnxruntime_providers_qnn.dll` and packaged `onnxruntime_qnn\QnnHtp.dll` discovered; EP devices included `QNNExecutionProvider` (NPU/GPU/CPU) after plugin registration.
  - Note: H.2 added catalog placeholder `whisper-small-onnx-qnn-int8` with `devices: [qnn]` and `local_path: models/stt/whisper-small-onnx-qnn-int8`; artifact presence was explicitly not claimed, default STT model remained `whisper-small-onnx`, CPU STT fallback remained green, H.3 QNN STT inference activation was not implemented, no live QNN transcript acceptance was attempted, and no model export/download/mutation occurred.

- 2026-05-03 18:52
  - Summary: Sub-Slice H.4 (x64 CUDA STT Readiness / Regression Guard) was closed by resolving the x64 CUDA ONNX Runtime ownership/provisioning conflict and restoring a CUDA-capable ORT state for the x64 NVIDIA CUDA profile. `CUDAExecutionProvider` became visible in `backend/.venv`, profile evidence included `ep:CUDAExecutionProvider`, `kokoro_onnx` import viability remained intact under GPU ORT ownership, and CUDA STT live validation was added and executed (not all-deselected).
  - Scope: `CHANGE_LOG.md` only; H.4 closeout documentation from existing validation evidence.
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64 — `backend/.venv/Scripts/python -m pytest backend/tests/runtime/voice/test_stt_live.py -q` PASS (`2 passed`); `$env:JARVISV7_LIVE_TESTS='1'; backend/.venv/Scripts/python scripts/validate_backend.py runtime --families stt --devices cuda` PASS (`1 passed, 23 deselected`); `$env:JARVISV7_LIVE_TESTS='1'; backend/.venv/Scripts/python scripts/validate_backend.py runtime --families stt --devices cpu` PASS (`4 passed, 20 deselected`); `backend/.venv/Scripts/python scripts/validate_backend.py regression` PASS (`96 passed`); provider evidence: `onnxruntime.get_available_providers()` included `CUDAExecutionProvider` and `CPUExecutionProvider`. Windows ARM64 — fingerprint `arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`; `$env:JARVISV7_LIVE_TESTS='1'; backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt --devices cpu` PASS (`4 passed, 20 deselected, 1 warning`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`96 passed`).
  - Note: H.4 scope was x64 CUDA STT only. No QNN, DirectML, or TTS acceleration was implemented; no model export/download/mutation occurred; CPU STT remains fallback authority; ARM64 CUDA was not attempted.

- 2026-05-02 22:10
  - Summary: Sub-Slice G.3 (Redis-Cached Retrieval) was closed by adding Redis-backed retrieval acceleration in `RetrievalManager.retrieve()` while preserving disk-backed episodic memory as the durable authority. Retrieval cache use follows fail-closed behavior through `CacheManager` (cache unavailable/stopped falls back to direct episodic disk retrieval), and cached values serialize/deserialize `RetrievedFact` lists via JSON-safe dict payloads.
  - Scope: `backend/app/memory/retrieval.py`, `backend/app/conversation/engine.py`, `backend/app/api/app.py`, `backend/tests/unit/memory/test_retrieval.py`, `backend/tests/runtime/services/test_retrieval_cached_live.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64 — `backend\.venv\Scripts\python -m compileall backend\app\memory\retrieval.py backend\app\conversation\engine.py backend\app\api\app.py` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit\memory\test_retrieval.py -q` PASS (`13 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`322 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`96 passed`); `docker compose up -d redis` and `docker compose ps redis` PASS (`jarvisv7-redis` healthy); `$env:JARVISV7_LIVE_TESTS="1"; backend\.venv\Scripts\python -m pytest backend\tests\runtime\services\test_retrieval_cached_live.py -q` PASS (`2 passed`); post-live `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`96 passed`); Redis-stopped fallback live test restored Redis afterward. Windows ARM64 — fingerprint `arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`; `backend\.venv\Scripts\python -m compileall backend\app\memory\retrieval.py backend\app\conversation\engine.py backend\app\api\app.py` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit\memory\test_retrieval.py -q` PASS (`13 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`322 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`96 passed`); `docker compose up -d redis` and `docker compose ps redis` PASS (`jarvisv7-redis` healthy); `powershell -NoProfile -Command "$env:JARVISV7_LIVE_TESTS='1'; backend\.venv\Scripts\python -m pytest backend\tests\runtime\services\test_retrieval_cached_live.py -q"` PASS (`2 passed`); post-live `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`96 passed`); final Redis check confirmed `jarvisv7-redis` healthy/restored.
  - Note: Cache keys follow existing key-helper conventions with `NS_RETRIEVAL` and `make_key(...)`, distinguishing retrieval mode, query hash (keyword mode), and `n`. Cache misses compute from episodic disk retrieval then attempt cache population; cache hits return cached retrieved facts. G.1 episodic write/retrieve behavior and G.2 prompt injection plus `retrieved_memory_refs` provenance behavior were preserved; prompt format was not changed. No durable storage contract changes, API/schema/route changes, desktop/text shell rendering changes, Slice F tool/executor changes, semantic/vector memory, new packages, new external services, Group I agent behavior, autonomous memory decisions, or tool behavior were introduced. `SYSTEM_INVENTORY.md` was not updated pending Slice G group closeout review.

- 2026-05-02 21:30
  - Summary: Sub-Slice G.2 (Retrieval Injected into Prompt Assembly) was closed by adding additive retrieved-context support to prompt assembly and wiring retrieval-before-generation in `TurnEngine` when retrieval is available. Retrieved episodic facts are injected with provenance, `TurnArtifact.retrieved_memory_refs` is populated from retrieval provenance used in prompt assembly, existing working-memory prompt behavior is preserved, no-retrieval behavior remains compatible, and G.1 episodic write/retrieve behavior was preserved.
  - Scope: `backend/app/cognition/prompt_assembler.py`, `backend/app/conversation/engine.py`, `backend/tests/unit/cognition/test_prompt_assembler.py`, `backend/tests/unit/conversation/test_engine.py`, `backend/tests/runtime/turn/test_retrieval_live.py`
  - Host class(es): Windows ARM64, Windows x64
  - Evidence: ARM64 fingerprint `arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`; `backend\.venv\Scripts\python -m compileall backend\app\cognition\prompt_assembler.py backend\app\conversation\engine.py` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit\cognition\test_prompt_assembler.py -q` PASS (`6 passed`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\conversation\test_engine.py -q` PASS (`35 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`313 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`96 passed`); `powershell -NoProfile -Command "$env:JARVISV7_LIVE_TESTS='1'; backend\.venv\Scripts\python -m pytest backend\tests\runtime\turn\test_retrieval_live.py -q"` PASS (`3 passed`). x64 fingerprint `arch=amd64 python=3.12.10 extras=[hw-cpu-base,hw-x64-base,hw-gpu-nvidia-cuda,dev] readiness=ready`; same command set PASS with counts `6 passed`, `35 passed`, `313 passed`, `96 passed`, and live `3 passed`.
  - Note: G.3 scope was not introduced: no Redis/cache acceleration behavior, no durable storage contract changes, no API/schema/route changes, no desktop/text shell rendering changes, no Slice F tool/executor changes, no semantic/vector memory, no new packages or external services, and no Group I agent behavior/autonomous memory decisions/tool behavior.

- 2026-05-02 21:06
  - Summary: Sub-Slice G.1 (Episodic Write + Retrieve) was closed by adding disk-backed episodic memory surfaces in `backend/app/memory/episodic.py` and `backend/app/memory/retrieval.py`, extending `WritePolicy` with explicit episodic write controls, and wiring `TurnEngine` for optional post-turn episodic writes after artifact recording. Episodic write failures fail closed without failing the turn; working-memory behavior, turn-artifact schema, and storage contracts were preserved.
  - Scope: `backend/app/memory/episodic.py`, `backend/app/memory/retrieval.py`, `backend/app/memory/write_policy.py`, `backend/app/conversation/engine.py`, `backend/tests/unit/memory/`, `backend/tests/unit/conversation/test_engine.py`, `backend/tests/runtime/turn/test_retrieval_live.py`, `pyproject.toml`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64 — `backend\.venv\Scripts\python -m compileall backend\app\memory backend\app\conversation\engine.py` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit\memory -q` PASS (`17 passed`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\conversation\test_engine.py -q` PASS (`31 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`306 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`96 passed`); `$env:JARVISV7_LIVE_TESTS="1"; backend\.venv\Scripts\python -m pytest backend\tests\runtime\turn\test_retrieval_live.py -q -k "not g2_required"` PASS (`2 passed, 1 deselected`) with no `PytestUnknownMarkWarning`. Windows ARM64 — fingerprint `arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`; `backend\.venv\Scripts\python -m compileall backend\app\memory backend\app\conversation\engine.py` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit\memory -q` PASS (`17 passed`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\conversation\test_engine.py -q` PASS (`31 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`306 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`96 passed`); `powershell -NoProfile -Command "$env:JARVISV7_LIVE_TESTS='1'; backend\.venv\Scripts\python -m pytest backend\tests\runtime\turn\test_retrieval_live.py -q -k \"not g2_required\""` PASS (`2 passed, 1 deselected`) with no `PytestUnknownMarkWarning`.
  - Note: Entries are written under `data/memory/episodic/<session_id>/<turn_id>.json` and are idempotent for the same `turn_id`; G.1 includes recency retrieval and simple case-insensitive keyword retrieval for direct proof; retention is session-count based, timestamp-safe, and prunes only under `data/memory/episodic/`; `g2_required` marker was registered in `pyproject.toml` to avoid unknown-marker warnings for guarded future G.2 assertions. G.2/G.3 scope was not introduced: no prompt injection, no `TurnArtifact.retrieved_memory_refs` population, no Redis/cache behavior, no API/schema/route changes, no desktop/text shell rendering changes, no semantic/vector memory, no new packages or external services, and no Group I agent/tool behavior.

- 2026-05-02 17:42
  - Summary: Sub-Slice F.3 (Tool Result Rendering in Desktop + Text Shells) was closed by adding additive optional tool-call metadata schemas for task/voice responses, mapping existing `TurnResult.tool_calls` into task/voice route response summaries, and rendering concise optional tool metadata in both `scripts/run_jarvis.py` and the existing desktop append/render flow. Presentation-only shell/API behavior was added while preserving F.1 ACTING/executor behavior, F.2 tool behavior, and normal non-tool turn compatibility.
  - Scope: `backend/app/api/schemas/`, `backend/app/api/routes/{task.py,voice.py}`, `scripts/run_jarvis.py`, `desktop/src/main.js`, `backend/tests/unit/api/test_routes.py`, `backend/tests/unit/desktop/test_desktop_static_contract.py`, `backend/tests/unit/scripts/test_run_jarvis_script.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64 — `backend\.venv\Scripts\python -m compileall backend\app backend\tests` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit -q` PASS (`292 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`292 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`96 passed`). Windows ARM64 — fingerprint `arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`; `backend\.venv\Scripts\python -m compileall backend\app backend\tests` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit -q` PASS (`292 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`292 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`96 passed`).
  - Note: No tool invocation semantics were changed; shells/API do not invoke tools directly. No new tools, filesystem search/indexing, Slice E runtime/provider changes, LLM-driven tool selection, model-side function calling, Group I agent behavior, memory retrieval, autonomous agents, new packages, new providers, new runtimes, or new services were introduced.

- 2026-05-02 18:03
  - Summary: Recovery for the missed Slice F live gate was completed by adding `backend/tests/runtime/turn/test_acting_live.py` and validating a live ACTING/tool path using explicit deterministic `tool_name` dispatch. The new live test proves the registered `time` tool is invoked through the current F.1/F.2 path, with tool-call/tool-result evidence in `TurnResult` and persisted artifact evidence in `tools_invoked` and `agent_trace`.
  - Scope: `backend/tests/runtime/turn/test_acting_live.py`
  - Host class(es): Windows x64
  - Evidence: `backend\.venv\Scripts\python -m compileall backend\tests\runtime\turn\test_acting_live.py` PASS; `$env:JARVISV7_LIVE_TESTS="1"; backend\.venv\Scripts\python -m pytest backend\tests\runtime\turn\test_acting_live.py -q` PASS (`1 passed in 24.52s`); `$env:JARVISV7_LIVE_TESTS="1"; backend\.venv\Scripts\python scripts\validate_backend.py runtime --families turn` PASS (`5 passed, 14 deselected in 42.00s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`PASS: unit: 96 tests`, `96 passed in 0.25s`). Minimal tool excerpt from the new live test assertions: `result.tool_calls[0]["tool_name"] == "time"`; `result.tool_results[0]["tool_name"] == "time"`; `result.tool_results[0]["success"] is True`; `"time" in artifact.tools_invoked`; `artifact.agent_trace` includes `tool_calls` and `tool_results`.
  - Note: No source/runtime behavior changes were introduced beyond the missing live test file. No LLM-driven tool selection, model-side function calling, Group I agent behavior, new tools, API/schema changes, shell rendering changes, Slice E provider/runtime changes, or `SYSTEM_INVENTORY.md` updates were introduced. ARM64 live validation was not run in this entry; this entry is not full Slice F group closeout.

- 2026-05-02 17:20
  - Summary: Sub-Slice F.2 (Tool Registry + First Tool Set) was closed by adding `backend/app/tools/` with a deterministic registry/base surface and first tool modules, while preserving F.1 ACTING/executor behavior and normal non-tool turns. Deterministic `register`/`invoke`/`list` behavior was added; duplicate registration and unknown-tool paths fail deterministically; internet-search output remained provider-agnostic and fail-closed through the existing Slice E selector tuple contract (`runtime, _trace = select_search_runtime(settings)`).
  - Scope: `backend/app/tools/`, `backend/app/core/settings.py`, `.env.example`, `backend/tests/unit/tools/`, `backend/tests/unit/conversation/test_engine.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64 — `backend\.venv\Scripts\python -m compileall backend\app\tools backend\app\core\settings.py` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit -q` PASS (`289 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`289 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`95 passed`). Windows ARM64 — fingerprint `arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`; `backend\.venv\Scripts\python -m compileall backend\app\tools backend\app\core\settings.py` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit\tools -q` PASS (`12 passed`); `backend\.venv\Scripts\python -m pytest backend\tests\unit -q` PASS (`289 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`289 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`95 passed`).
  - Note: First tool set includes time/date, hardware-info, `filesystem.read` (read-only sandboxed) and internet-search adapter over existing Slice E runtime; filesystem sandbox default was narrowed to `data/tool_sandbox/` with `TOOL_FILESYSTEM_SANDBOX_PATH` in `.env.example` and settings support; `filesystem.read` rejects traversal/out-of-sandbox access, sibling internal data dirs, missing files, binary/invalid UTF-8 reads, and write behavior. F.3 scope was not introduced (no API schema/route expansion, no desktop/text shell rendering). No LLM-driven tool selection, model-side function calling, Group I agent behavior, memory retrieval, autonomous agents, new packages, new providers, new runtimes, or new services were introduced.

- 2026-05-02 16:33
  - Summary: Sub-Slice F.1 (Executor + ACTING State) was closed with deterministic ACTING wiring in the live `_run_reasoning_path()` lifecycle using explicit `tool_name` and optional tool input, while preserving normal non-tool turn behavior. Additive `TurnResult` tool metadata defaults were introduced, tool execution now populates `TurnArtifact.tools_invoked` and `agent_trace`, and missing-tool/tool-exception paths fail closed.
  - Scope: `backend/app/cognition/executor.py`, `backend/app/conversation/engine.py`, `backend/tests/unit/cognition/test_executor.py`, `backend/tests/unit/conversation/test_engine.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64 — `backend\.venv\Scripts\python -m compileall backend\app\cognition\executor.py backend\app\conversation\engine.py` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit\cognition\test_executor.py -q` PASS (`4 passed`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\conversation\test_engine.py -q` PASS (`29 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`277 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`95 passed`). Windows ARM64 — fingerprint `arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`; same command sequence PASS with `4 passed`, `29 passed`, `277 passed`, and regression `95 passed`.
  - Note: F.2/F.3 scope was not introduced: no `backend/app/tools/`, no real tool registry/toolset, no search/filesystem/time/hardware tools, no API schema/route expansion, no desktop/text shell rendering, no LLM-driven tool selection, and no Group I agent behavior.

- 2026-05-01 01:05
  - Summary: Slice E grouped closeout was recorded as verified across Windows x64 and Windows ARM64 for E.1-E.5. Slice E infrastructure and internet-search substrate evidence includes 95 passing regression on both hosts, live Redis roundtrip, live SearXNG search, and live DDGS/Tavily provider proof.
  - Scope: `docker-compose.yml`, `config/search/searxng/`, `backend/app/core/settings.py`, `backend/app/cache/`, `backend/app/runtimes/internetsearch/`, `backend/app/routing/runtime_selector.py`, `backend/tests/runtime/services/`, `backend/tests/unit/runtimes/internetsearch/`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: E.1 through E.5 entries in `CHANGE_LOG.md` record x64+ARM64 validation with URL grep checks no hits for scoped SearXNG hardcoded locals, internetsearch unit `6 passed`, validator unit `269 passed`, regression `95 passed` on both hosts, and live search tests `3 passed` (`3 passed in 2.70s` on x64).
  - Note: No F/G/H/I scope was introduced; no prompt/turn/conversation behavior, tool-call/agent behavior, or memory-retrieval behavior was added.

- 2026-05-01 00:29
  - Summary: E.5 Search Wiring was completed across Windows x64 and Windows ARM64. A fail-closed internet search runtime family was added under `backend/app/runtimes/internetsearch/` with `SearchResult`, `SearchBase`, and `NullSearchRuntime`; SearXNG runtime uses `httpx` and `settings.searxng_base_url`; DDGS runtime uses `from ddgs import DDGS`; Tavily runtime uses `httpx`, `USE_TAVILY`, and `TAVILY_API_KEY`; `select_search_runtime(settings)` was added with provider priority SearXNG → DDGS → Tavily → Null; provider unavailable/error paths fail closed to empty results; hardcoded SearXNG local URL values were removed from scoped E.5 tests so URL ownership flows through settings; and live provider proof passed for SearXNG, DDGS, and Tavily.
  - Scope: `backend/app/runtimes/internetsearch/`, `backend/app/routing/runtime_selector.py`, `backend/tests/unit/runtimes/internetsearch/test_search_runtime.py`, `backend/tests/runtime/services/test_search_live.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows ARM64: URL grep checks no hits; internetsearch unit `6 passed`; validator unit `269 passed`; regression `95 passed`; live search tests `3 passed`. Windows x64: URL grep checks no hits; internetsearch unit `6 passed`; validator unit `269 passed`; regression `95 passed`; live search tests `3 passed in 2.70s`.
  - Note: No prompt/turn/conversation behavior, tools/agents behavior, memory retrieval behavior, Docker Compose, `.env`, `.env.example`, or `SYSTEM_INVENTORY.md` update was added; Tavily key was not printed or logged.

- 2026-04-30 23:20
  - Summary: Corrective Slice E search wiring alignment was completed on Windows x64. `duckduckgo-search>=6.0` was replaced with `ddgs>=9.10` in `pyproject.toml`, and `20260430-slice_e.md` was corrected to preserve old package references only as strikethrough while documenting `ddgs` and `from ddgs import DDGS`.
  - Scope: `pyproject.toml`, `20260430-slice_e.md`
  - Host class(es): Windows x64
  - Evidence: `git grep -n --fixed-strings "duckduckgo_search"` PASS (no tracked hits); `git grep -n --fixed-strings "duckduckgo-search"` PASS (remaining hits only in intentional strikethrough text in `20260430-slice_e.md` and historical `CHANGE_LOG.md`); `backend\.venv\Scripts\python scripts\provision.py install` PASS with `Collecting ddgs>=9.10`; `backend\.venv\Scripts\python -c "from ddgs import DDGS; import importlib.metadata as m; print(m.version('ddgs'), DDGS)"` PASS with `9.14.1 <class 'ddgs._DDGSProxy'>`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `95 passed in 0.19s`.
  - Note: No source search runtime, tests, `SYSTEM_INVENTORY.md`, or Slice E implementation behavior was changed. Historical `CHANGE_LOG.md` references to `duckduckgo-search` were intentionally preserved.

- 2026-04-30 21:08
  - Summary: E.4 Search Escalation Service Configuration was completed across Windows x64 and Windows ARM64. Search settings were added to `backend/app/core/settings.py`, settings loading follows `.env` with `.env.example` fallback, `.env.example` coverage includes `USE_SEARXNG`, `SEARXNG_BASE_URL`, `USE_DDGS`, `USE_TAVILY`, and `TAVILY_API_KEY`, `duckduckgo-search>=6.0` was added to base dependencies, dependency provisioning was validated through `scripts/provision.py install`, import/version was validated as `8.1.1`, and placeholder config directories were added at `config/search/ddgs/.gitkeep` and `config/search/tavily/.gitkeep`.
  - Scope: `backend/app/core/settings.py`, `pyproject.toml`, `backend/tests/unit/core/test_settings.py`, `config/search/ddgs/.gitkeep`, `config/search/tavily/.gitkeep`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64: core tests `11 passed`; provision install PASS; import `8.1.1`; regression `95 passed`. Windows ARM64: core tests `11 passed in 0.05s`; provision install PASS; import `8.1.1`; regression `95 passed in 0.19s`.
  - Note: No search runtime, search wiring, Docker Compose change, backend cache wiring, or `SYSTEM_INVENTORY.md` update was added.

- 2026-04-30 20:26
  - Summary: E.3 Cache Wiring was completed across Windows x64 and Windows ARM64. The `backend/app/cache/` package was added with a Redis-backed `CacheManager`, cache key helpers, and cache policy constants/dataclass; cache manager behavior is fail-closed when Redis is unavailable; FastAPI `ApiState` now includes `cache_manager`; `get_cache_manager` dependency was added; and runtime Redis live proof was added under `backend/tests/runtime/services/`.
  - Scope: `backend/app/cache/`, `backend/app/api/app.py`, `backend/app/api/dependencies.py`, `backend/tests/unit/cache/test_cache_manager.py`, `backend/tests/runtime/services/test_cache_live.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64: unit cache `7 passed`; unit API `21 passed`; validator unit `260 passed`; regression `95 passed`; Redis `PONG`; runtime cache live `3 passed`. Windows ARM64: unit cache `7 passed in 0.06s`; unit API `21 passed in 0.58s`; validator unit `260 passed in 0.84s`; regression `95 passed in 0.19s`; Redis `PONG`; runtime cache live `3 passed in 0.06s`.
  - Note: Default unit/regression validation does not require Redis or Docker. No search runtime, search wiring, memory retrieval behavior, prompt/turn behavior, Docker Compose, or `SYSTEM_INVENTORY.md` update was added.

- 2026-04-30 19:16
  - Summary: E.2 Redis Configuration and Runtime Prerequisite was completed across Windows x64 and Windows ARM64. Redis settings were added in `backend/app/core/settings.py`, settings load path honors `.env` with `.env.example` fallback, `.env.example` documents `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_MAX_CONNECTIONS`, and `REDIS_SOCKET_TIMEOUT`, `redis>=5.0` was added to base dependencies in `pyproject.toml`, Redis import was validated as `7.4.0`, and focused settings tests cover env-loaded values and defaults.
  - Scope: `backend/app/core/settings.py`, `.env.example`, `pyproject.toml`, `backend/tests/unit/core/test_settings.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64: `backend\.venv\Scripts\python -m pytest backend\tests\unit\core -q` PASS (`8 passed`); `backend\.venv\Scripts\python -c "import redis; print(redis.__version__)"` PASS (`7.4.0`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`95 passed`). Windows ARM64: `backend\.venv\Scripts\python -m pytest backend\tests\unit\core -q` PASS (`8 passed in 0.05s`); `backend\.venv\Scripts\python -c "import redis; print(redis.__version__)"` PASS (`7.4.0`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`95 passed in 0.19s`).
  - Note: No backend cache wiring, Redis cache client layer, search runtime, search wiring, Docker Compose changes, or `SYSTEM_INVENTORY.md` update was added.

- 2026-04-30 18:43
  - Summary: E.1 Docker Service Substrate Verification was completed across Windows x64 and Windows ARM64. Docker Compose Redis and SearXNG services were validated; Redis runtime data mount `cache/redis:/data`, SearXNG config mount `config/search/searxng:/etc/searxng`, and SearXNG cache mount `config/search/searxng/cache:/var/cache/searxng` were confirmed; Redis responded `PONG`; SearXNG `settings.yml` enabled `html` and `json`; SearXNG JSON search endpoint returned valid JSON; and `.env.example` documented E.1 Redis/search service settings.
  - Scope: `docker-compose.yml`, `.env.example`, `config/search/searxng/settings.yml`, `config/search/searxng/cache/.gitkeep`, Docker Compose runtime behavior for Redis/SearXNG.
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64: `docker compose config` PASS; `docker compose up -d` PASS; `docker compose ps` healthy; `docker exec jarvisv7-redis redis-cli ping` -> `PONG`; `curl.exe "http://127.0.0.1:8080/search?q=test&format=json"` PASS (valid JSON); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`95 passed`). Windows ARM64: `docker compose config` PASS; `docker compose up -d` PASS; `docker compose ps` healthy; `docker exec jarvisv7-redis redis-cli ping` -> `PONG`; `curl.exe "http://127.0.0.1:8080/search?q=test&format=json"` PASS (valid JSON); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`95 passed in 0.18s`).
  - Note: No backend cache wiring, Redis client/app cache layer, search runtime, search wiring, changelog/inventory behavior, or Python dependency change was added.

- 2026-04-30 11:12
  - Summary: Slice D live-evidence closeout delta was captured for the previously missing D.3/D.4 runtime desktop gap. User-run runtime desktop evidence confirmed D.3 resident session continuity and D.4 deterministic wake integration behavior.
  - Scope: `CHANGE_LOG.md` only; evidence references `backend/tests/runtime/desktop/test_resident_loop_live.py` and `backend/tests/runtime/desktop/test_wake_integration_live.py`.
  - Host class(es): Windows x64
  - Evidence: User-run in a normal terminal (not run by Cline). D.3: `backend\.venv\Scripts\python -m pytest backend\tests\runtime\desktop\test_resident_loop_live.py -q -s` PASS; three `/task/text` turns completed in one active session with the same `session_id`; `/session/status` returned `active=True`, `state='IDLE'`, `turn_count=3`; `/session/close` returned `closed=True` and wrote the session artifact. D.4: `backend\.venv\Scripts\python -m pytest backend\tests\runtime\desktop\test_wake_integration_live.py -q -s` PASS; wake provider configured `openwakeword available=true`; nondetect path reported cleanly; unavailable runtime reported explicit `PTT-only fallback`; deterministic detection set `last_detected=True` and `detection_count=1`; deterministic error reported fallback with `last_error`.
  - Note: This entry records User-run live/runtime evidence only. No open-microphone live wake phrase test is claimed. No `SYSTEM_INVENTORY.md` update was made in this step.

- 2026-04-30 07:56
  - Summary: D.5 Personality / Presence Polish was completed across Windows x64 and Windows ARM64. Selectable `default`, `concise`, and `warm` profiles were validated; all six current personality fields load schema-compatibly; `adapter.py` reaches the live prompt path through `TurnEngine`; prompt guidance includes tone, brevity, formality, and addendum without duplication; `/personality/list` and `/personality/select` were added; profile selection applies to subsequent turns without resident-session reset; and desktop personality selector plus active-profile display with UI-only presence acknowledgments were validated.
  - Scope: `backend/app/personality/{loader.py,adapter.py,schema.py}`, `backend/app/conversation/engine.py`, `backend/app/api/routes/personality.py`, `backend/app/api/schemas/personality.py`, `backend/app/services/session_service.py`, `desktop/src-tauri/src/{backend.rs,lib.rs}`, `desktop/src/{main.js,index.html}`, `backend/tests/unit/{personality/test_personality.py,conversation/test_engine.py,services/test_session_service.py,api/test_routes.py,desktop/test_desktop_static_contract.py}`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Validation passed on both hosts. x64: personality unit `7 passed`; conversation unit `25 passed`; session service unit `12 passed`; API unit `20 passed`; desktop static `11 passed`; validator unit `250 passed`; validator integration `8 passed`; regression `95 passed`. ARM64: personality unit `7 passed in 0.05s`; conversation unit `25 passed in 0.13s`; session service unit `12 passed in 0.11s`; API unit `20 passed in 0.48s`; desktop static `11 passed in 0.04s`; validator unit `250 passed in 0.76s`; validator integration `8 passed in 0.38s`; regression `95 passed in 0.18s`.
  - Note: No model/runtime selection, STT/TTS/LLM runtime, wake runtime, changelog/inventory behavior, or provisioning behavior was changed. Response-style proof is prompt-path and observable-behavior ready; subjective live style judgment is not asserted by unit tests.

- 2026-04-29 14:31
  - Summary: D.4 first-pass and second-pass wake integration progress was validated (not full D.4 completion). Desktop consumes existing `GET /status/wake` through Rust/Tauri `get_wake_status`, displays wake provider/availability/reason including PTT-only fallback messaging, and `SessionService` now carries wake status/detection state.
  - Scope: `desktop/src-tauri/src/{backend.rs,lib.rs}`, `desktop/src/main.js`, `backend/app/services/session_service.py`, `backend/app/api/routes/status.py`, `backend/app/api/schemas/status.py`, `backend/tests/unit/services/test_session_service.py`, `backend/tests/unit/api/test_routes.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Validation passed on both hosts. x64: service unit `11 passed`, API unit `17 passed`, validator unit `241 passed`, regression `95 passed`. ARM64: service unit `11 passed in 0.11s`, API unit `17 passed in 0.43s`, validator unit `241 passed in 0.76s`, regression `95 tests`. `/status/wake` preserves `provider`, `available`, and `reason`, and includes `monitoring`, `last_detected`, `detection_count`, and `last_error`. Deterministic injected-chunk detection updates `last_detected=true` and increments `detection_count`; unavailable/error states return explicit PTT-only fallback status.
  - Note: This is D.4 progress only, not full D.4 completion. No human live wake test was run from Cline; live microphone wake monitoring, wake-triggered capture, and final wake/voice UX remain future D.4 work. No `SYSTEM_INVENTORY.md` update is claimed in this step.

- 2026-04-29 13:18
  - Summary: D.3 first-pass resident session continuity progress was validated (not full D.3 completion). Backend-owned `SessionService` and `GET /session/status` were added; session create/close and text turns now run through the active resident-session boundary; supplied `session_id` is validated when present; and desktop now displays session id and turn count through Tauri `get_session_status`.
  - Scope: `backend/app/services/session_service.py`, `backend/app/api/routes/session.py`, `backend/app/api/schemas/session.py`, `backend/app/api/dependencies.py`, `backend/app/api/routes/task.py`, `desktop/src-tauri/src/{backend.rs,lib.rs}`, `desktop/src/main.js`, `desktop/src/index.html`, `backend/tests/unit/services/test_session_service.py`, `backend/tests/unit/api/test_routes.py`, `backend/tests/integration/api/test_headless_client.py`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Service unit PASS on both hosts (x64 `6 passed in 1.03s`; ARM64 `6 passed in 0.12s`); API unit PASS on both hosts (x64 `15 passed in 0.91s`; ARM64 `15 passed in 0.44s`); API integration PASS on both hosts (x64 `5 passed in 0.38s`; ARM64 `5 passed in 0.36s`); desktop static PASS on both hosts (x64 `9 passed in 0.18s`; ARM64 `9 passed in 0.04s`); validator unit PASS on both hosts (x64 `233 passed`; ARM64 `233 passed`); validator integration PASS on both hosts (x64 `8 passed`; ARM64 `8 passed`); regression PASS on both hosts (x64 `95 passed`; ARM64 `95 tests`). D.3-specific proof: integration test drove three text turns with one `session_id`, and `/session/status` returned `active=true` with `turn_count=3`.
  - Note: This is D.3 first-pass progress only, not full D.3 completion. No live human voice test was run in Cline; voice multi-turn proof remains future D.3 work via user-run live evidence. No `SYSTEM_INVENTORY.md` update is claimed in this step.

- 2026-04-29 10:15
  - Summary: D.2 Durable Desktop Host was closed across Windows x64 and Windows ARM64 using the previously recorded D.2 progress evidence.
  - Scope: `CHANGE_LOG.md` only; closeout delta referencing prior D.2 progress entries.
  - Host class(es): Windows x64 and Windows ARM64
  - Evidence: Prior D.2 progress entries are the evidence source: `2026-04-29 05:32` for Windows x64 and `2026-04-29 06:00` for Windows ARM64.
  - Note: HTT validated the D.2 voice path, but HTT is not the final intended PTT UX; final PTT interaction semantics continue in later D work. Browser capture/WAV path worked, but idealized 16 kHz PCM/downsample quality is not claimed. No `SYSTEM_INVENTORY.md` update was made in this step.

- 2026-04-29 09:36
  - Summary: D.2 Durable Desktop Host was closed across Windows x64 and Windows ARM64 by accepting the previously recorded host-specific progress evidence. The durable npm/Tauri desktop host, backend lifecycle through `scripts/run_backend.py`, readiness display, visible text turn, tray lifecycle menu, robot `.ico`, and HTT voice-path proof are now the D.2 closeout baseline.
  - Scope: `CHANGE_LOG.md` only; closeout delta over prior D.2 evidence in `desktop/` and `backend/tests/unit/desktop/`
  - Host class(es): Windows x64 and Windows ARM64
  - Evidence: Prior D.2 progress entries are the evidence source: `2026-04-29 05:32` for Windows x64 and `2026-04-29 06:00` for Windows ARM64.
  - Note: HTT validated the D.2 voice path, but HTT is not the final intended PTT UX; final PTT interaction semantics continue in later D work. Browser capture/WAV path worked, but idealized 16 kHz PCM/downsample quality is not claimed. No `SYSTEM_INVENTORY.md` update was made in this step.

- 2026-04-29 06:00
  - Summary: D.2 desktop progress previously validated on Windows x64 was also validated on Windows ARM64. Validation confirmed current desktop host progress only (not full D.2 completion): ARM64 dev-runner/toolchain readiness, desktop static/unit checks, lockfile-based npm install, cargo check, backend dry-run/regression, and Tauri dev launch with user-confirmed ARM64 smoke.
  - Scope: `desktop/`, `backend/tests/unit/desktop/`
  - Host class(es): Windows ARM64
  - Evidence: `backend\.venv\Scripts\python scripts\dev_runner.py check --arch arm64` PASS (`SUMMARY arch=arm64 failures=0 warnings=1`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop -q` PASS (`8 passed in 0.03s`); `npm --prefix desktop install` PASS using committed `desktop/package-lock.json`; `npm --prefix desktop test` PASS (desktop static voice checks); `cargo check --manifest-path desktop\src-tauri\Cargo.toml` PASS; `backend\.venv\Scripts\python scripts\run_backend.py --dry-run` PASS; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`95 tests`); `npm --prefix desktop run dev` launch PASS. User-confirmed ARM64 desktop smoke: window opened, backend health/session/readiness loaded, text turn visible, tray menu operational, and HTT voice path reached `/task/voice` with visible result.
  - Note: This is D.2 progress validation only, not full D.2 completion. HTT remains a development-cycle proof path, not final intended PTT UX. No backend API/runtime behavior, scripts, provisioning, routing/policy, tools, agents, wake, resident loop, WebSockets, audio streaming, or shell-side playback was added; no `SYSTEM_INVENTORY.md` promotion is claimed.

- 2026-04-29 05:32
  - Summary: D.2 Windows x64 desktop progress was validated, not full D.2 completion. An npm/Tauri desktop host was added under `desktop/`; it starts the backend through `scripts/run_backend.py`, includes desktop lifecycle startup diagnostics/logging, displays readiness/runtime state, supports visible text turns, provides an operational tray menu (`Start Backend`, `Stop Backend`, `Show Window`, `Quit`), uses the robot `.ico` for desktop/tray icon, and includes a development-cycle Hold-to-Talk proof path using browser `getUserMedia`, frontend WAV encoding, raw WAV POST to `/task/voice`, and visible transcript/response/degraded/failure fields. HTT is not the final intended PTT UX and will be built upon in later D work.
  - Scope: `desktop/`, `backend/tests/unit/desktop/`
  - Host class(es): Windows x64 only
  - Evidence: x64 dev runner PASS (`SUMMARY arch=x64 failures=0 warnings=1`); desktop static tests PASS (`8 passed`); npm static voice checks PASS; `cargo check --manifest-path desktop\src-tauri\Cargo.toml` PASS; `backend\.venv\Scripts\python scripts\run_backend.py --dry-run` PASS; backend regression PASS (`95 passed`); Tauri dev smoke PASS by user confirmation: app launched, backend health/session/readiness OK, text turn visible in UI, tray menu operational, and `/task/voice` reached with visible voice result.
  - Note: No full D.2 completion or ARM64 validation is claimed. No backend API/runtime behavior, scripts, provisioning, routing/policy, tools, agents, wake, resident loop, WebSockets, audio streaming, or shell-side playback was added.

- 2026-04-28 21:22
  - Summary: D.2-enabling method-viability tooling was added (not D.2 desktop implementation): stdlib-only `scripts/dev_runner.py` and `backend/tests/unit/scripts/test_dev_runner.py`. The runner validates architecture-sensitive desktop prerequisites before Tauri work, supports `check --arch x64`, `check --arch arm64`, and `check --arch x64-arm64`, dynamically discovers Visual Studio/MSVC via `vswhere`/candidate installs, captures full MSVC environment with `vcvarsall.bat <arg> && set`, checks Node/npm/Rust/Cargo/selected Rust target/MSVC env/`cl`/`link`/WebView2, treats pnpm as optional/non-failing, and treats uncertain WebView2 detection as WARN rather than false hard fail.
  - Scope: `scripts/dev_runner.py`, `backend/tests/unit/scripts/test_dev_runner.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64 and Windows ARM64: compileall PASS; focused dev_runner unit PASS; runner check PASS where applicable; regression PASS. x64: focused unit `18 passed in 0.04s`; `check --arch x64` PASS (`SUMMARY arch=x64 failures=0 warnings=1`); `check --arch x64-arm64` expected method evidence with `FAIL:rust-target-missing` for missing `aarch64-pc-windows-msvc` while MSVC cross env passed with `target=arm64`; regression `95 passed in 0.53s`. ARM64: focused unit `18 passed in 0.06s`; `check --arch arm64` PASS (`SUMMARY arch=arm64 failures=0 warnings=1`); selected VS path `C:\Program Files\Microsoft Visual Studio\18\Community`; captured target `target=arm64`; regression `95 passed in 0.23s`.
  - Note: This validates the runner method only and does not validate or implement the D.2 desktop/Tauri host. x64-to-ARM64 cross-target remains unavailable until `aarch64-pc-windows-msvc` is installed through separately approved action.

- 2026-04-28 11:36
  - Summary: Slice D.1 Application Shell Contract was completed by adding the backend FastAPI shell contract under `backend/app/api/`, including typed shell-facing schemas and route groups for health, readiness, session create/close, text turn, voice turn, diagnostics, disabled/read-only agents status, and wake status. `scripts/run_backend.py` was added as the backend-only API launcher, preserving fingerprint-first dry-run behavior; `/session/tick` remains excluded; route handlers remain thin service/engine/app-state adapters; and uploaded WAV decoding uses stdlib `wave` plus `numpy`.
  - Scope: `backend/app/api/`, `scripts/run_backend.py`, `backend/tests/unit/api/`, `backend/tests/integration/api/`, `backend/tests/unit/scripts/test_run_backend_script.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64 and Windows ARM64: compileall PASS; API unit PASS; run_backend script unit PASS; API integration PASS; run_backend dry-run PASS with fingerprint first; unit validator PASS; integration validator PASS; regression PASS. Counts — x64: `12 passed`, `3 passed`, `4 passed`, `197 passed`, `7 passed`, `77 passed`; ARM64: `12 passed`, `3 passed`, `4 passed`, `197 passed`, `7 passed`, `77 passed`; fingerprint excerpt: `[fingerprint] arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready; tokens=15`.
  - Note: D.1 does not add desktop/Tauri, resident loop, wake monitoring, tools, agents, routing/policy, authentication, dependency, provisioning, or inventory changes.

- 2026-04-28 06:04
  - Summary: Slice C.6 Developer Usability Surface / Proving Host was completed by adding `scripts/run_jarvis.py` as a developer/proving-host diagnostic script. It emits host fingerprint as first stdout line; supports `--verbose`, `--dry-run`, `--trace-to`, `--profile`, `--turns`, `--voice-only`, `--text-only`, and `--policy-override`; runs startup diagnostics through existing profiler/extras-resolver/preflight/readiness surfaces; uses existing text/voice service boundaries including `voice_service.capture_audio`; uses existing trace writer for `--trace-to`; reports named failures (`STT_UNAVAILABLE`, `LLM_UNAVAILABLE`, `AUDIO_DEVICE_ERROR`); and keeps `--policy-override` parsed but not applied.
  - Scope: `scripts/run_jarvis.py`, `backend/tests/unit/scripts/test_run_jarvis_script.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64 and Windows ARM64: compileall PASS; focused C.6 script unit PASS; dry-run PASS with fingerprint first; profile PASS with fingerprint first; unit validator PASS; regression PASS. Counts — x64: `11 passed`, `182 passed`, `74 passed`; ARM64: `11 passed`, `182 passed`, `74 passed`; fingerprint excerpt: `[fingerprint] arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready; tokens=15`.
  - Note: C.6 does not create a durable application surface, API, desktop shell, resident loop, tools, agents, new runtime family, routing/policy implementation, or inventory change.

- 2026-04-27 15:41
  - Summary: Slice C.5 Interruption / Barge-In was completed. `BargeInDetector` was promoted from stub behavior to deterministic RMS/guard-time detection; a minimal non-blocking playback-start boundary was added while preserving existing blocking `play()` behavior; additive `TurnResult` interruption fields were added; interruption events are recorded into existing `TurnArtifact.interruption_events`; and unit coverage proves deterministic interruption behavior including playback stop invocation, interruption-event recording, and recovery to `IDLE`. Existing non-interrupted C.2/C.3/C.4 behavior was preserved.
  - Scope: `backend/app/runtimes/stt/barge_in.py`, `backend/app/runtimes/tts/playback.py`, `backend/app/conversation/engine.py`, `backend/app/artifacts/turn_artifact.py`, `backend/tests/unit/runtimes/stt/test_stt_runtime.py`, `backend/tests/unit/conversation/test_engine.py`, `backend/tests/runtime/turn/test_interruption_live.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64 and Windows ARM64: focused STT detector unit PASS; focused engine unit PASS; unit validator PASS; runtime validator PASS; regression PASS. Counts — x64: `10 passed`, `24 passed`, `171 passed`, `5 passed, 4 deselected`, `63 passed`; ARM64: `10 passed`, `24 passed`, `171 passed`, `5 passed, 4 deselected`, `63 passed`; fingerprint excerpt: `[fingerprint] arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready; tokens=15`.
  - Note: C.5 does not claim full acoustic microphone barge-in validation or physical audio-output validation.

- 2026-04-27 14:11
  - Summary: Slice C.4 Live Multi-Turn Spoken Continuity was completed by adding live-gated runtime acceptance coverage in `backend/tests/runtime/turn/test_multiturn_live.py`. The test validates two spoken turns in one `SessionManager`, validates both turns complete without error, validates turn artifacts are written only under `tmp_path`, and validates second-turn working-memory injection through persisted `final_prompt_text`.
  - Scope: `backend/tests/runtime/turn/test_multiturn_live.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64: compileall PASS; runtime validator PASS (`5 passed, 3 deselected in 36.09s`); regression PASS (`63 passed in 0.09s`). Windows ARM64: compileall PASS; runtime validator PASS (`5 passed, 3 deselected in 30.15s`); regression PASS (`63 passed in 0.09s`); fingerprint excerpt: `[fingerprint] arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready; tokens=15`.
  - Note: C.4 explicitly uses `NullTTSRuntime` degraded behavior and does not claim real TTS playback/audio-output/device-state proof. No engine, session manager, artifacts, memory, runtime-family, playback, hardware/provisioning, routing, docs, inventory, desktop/API, tools, or agents changes were made.

- 2026-04-27 13:27
  - Summary: Slice C.3 Session Continuity + Canonical Turn Artifact was completed. Added canonical `TurnArtifact` and `SessionArtifact` schemas, deterministic artifact storage under `data/turns/` and `data/sessions/`, bounded in-session `WorkingMemory`, `WritePolicy` for working-memory writes, and `SessionManager` for session ID ownership, turn tracking, working-memory context injection, artifact recording, and session close. `TurnEngine` was extended with optional `session_manager` and `write_policy`, preserving default artifact-free C.1/C.2 behavior when no `SessionManager` is provided. Integration evidence proved two text turns in one session write deterministic artifacts and inject prior working memory into the second prompt.
  - Scope: `backend/app/artifacts/`, `backend/app/memory/`, `backend/app/conversation/`, `backend/tests/unit/artifacts/`, `backend/tests/unit/memory/`, `backend/tests/unit/conversation/`, `backend/tests/integration/services/test_two_turn_session.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64: compileall PASS; focused C.3 pytest PASS (`40 passed in 0.28s`); `scripts\validate_backend.py unit` PASS (`165 passed in 0.38s`); `scripts\validate_backend.py integration` PASS (`3 passed in 0.13s`); `scripts\validate_backend.py regression` PASS (`63 passed in 0.10s`). Windows ARM64: compileall PASS; focused C.3 pytest PASS (`40 passed in 0.22s`); `scripts\validate_backend.py unit` PASS (`165 passed in 0.40s`); `scripts\validate_backend.py integration` PASS (`3 passed in 0.10s`); `scripts\validate_backend.py regression` PASS (`63 passed in 0.09s`); fingerprint excerpt: `[fingerprint] arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready; tokens=15`.
  - Note: C.3 did not add episodic memory, retrieval, runtime-family changes, live runtime behavior, hardware/provisioning changes, API/desktop/tool/agent work, or inventory changes.

- 2026-04-27 10:34
  - Summary: Slice C.2 Spoken Response + SPEAKING State was completed and validated on Windows x64 and Windows ARM64. Voice turns now synthesize/play spoken output through the injected TTS runtime when available, sanitize response text before synthesis, enter `SPEAKING` only when playback is attempted, return to `IDLE` after playback, and degrade cleanly to text with additive `TurnResult` fields `tts_degraded` and `tts_degraded_reason` when TTS is unavailable.
  - Scope: `backend/app/conversation/engine.py`, `backend/app/cognition/responder.py`, `backend/tests/unit/conversation/test_engine.py`, `backend/tests/runtime/turn/test_voice_turn_live.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64: `backend\.venv\Scripts\python -m compileall backend/app/conversation backend/tests/unit/conversation backend/tests/runtime/turn` PASS; `backend\.venv\Scripts\python -m pytest backend/tests/unit/conversation/test_engine.py -q` PASS; `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families turn,tts` PASS with `3 passed, 4 deselected in 54.82s`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `63 passed in 0.10s`. Windows ARM64: fresh-clone bootstrap completed through profile/provision/ensure_models/preflight/validate_profile checkpoints; `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS; `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families turn,tts` PASS with `3 passed, 4 deselected in 14.97s`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `63 passed in 0.08s`.
    ```text
    x64: runtime --families turn,tts: 3 passed, 4 deselected in 54.82s; regression: 63 passed in 0.10s
    arm64: bootstrap checkpoints complete; verify-only PASS; runtime --families turn,tts: 3 passed, 4 deselected in 14.97s; regression: 63 passed in 0.08s
    arm64 note: initial runtime validation failed with Ollama not running; rerun PASS after starting Ollama (environment prerequisite, not C.2 code defect)
    ```
  - Note: Text-turn behavior was preserved. No changes were made to TTS runtime families, playback implementation, hardware/provisioning, routing, desktop/API, artifacts, memory, tools, agents, or `SYSTEM_INVENTORY.md`.

- 2026-04-27 07:30
  - Summary: Env/settings template cleanup reduced `.env.example` to a concise operator-facing template. `JARVISV7_OLLAMA_URL` was removed from the template while remaining code-supported as a compatibility alias; settings tests now split readable settings variables from public-template variables.
  - Scope: `.env.example`, `backend/tests/unit/core/test_settings.py`; `backend/app/core/settings.py` was not modified.
  - Host class(es): Windows x64
  - Evidence: `backend\.venv\Scripts\python -m compileall backend/app/core backend/tests/unit/core` PASS; `backend\.venv\Scripts\python -m pytest backend/tests/unit/core/test_settings.py -q` PASS; `backend\.venv\Scripts\python scripts/validate_backend.py unit` PASS.
    ```text
    6 passed in 0.06s
    135 passed in 0.40s
    [fingerprint] arch=amd64 python=3.12.10 extras=[hw-cpu-base,hw-x64-base,hw-gpu-nvidia-cuda,dev] readiness=ready; tokens=13
    ```
  - Note: Canonical `OLLAMA_BASE_URL`, active `OLLAMA_NUM_CTX` and `JARVISV7_LIVE_TESTS`, and shell env > `.env` > `.env.example` precedence behavior were preserved.

- 2026-04-27 05:36
  - Summary: The repo environment template coverage correction was recorded after the prior x64 env-standard entry. `.env.example` now includes `QAIRT_SDK_PATH=` so the committed fallback/template aligns with the settings coverage test, while `.env` remained local/gitignored and was not committed.
  - Scope: `.env.example`, ARM64 validation evidence for `backend/app/core/settings.py` / C.1 runtime path
  - Host class(es): Windows ARM64
  - Evidence: `.env.example` includes `QAIRT_SDK_PATH=`; `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families llm` PASS with `1 passed, 6 deselected`; `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families turn` PASS with `2 passed, 5 deselected`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `63 passed`; regression report `reports\validation\20260427023948-regression.txt`.
    ```text
    arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready; tokens=15
    llm runtime: 1 passed, 6 deselected
    turn runtime: 2 passed, 5 deselected
    regression: 63 passed
    ```
  - Note: No C.2, playback, artifacts, memory continuity, interruption, tools, agents, desktop, API routes, or Group D+ work was introduced.

- 2026-04-26 21:18
  - Summary: Repo-wide env/config loading was standardized through `backend/app/core/settings.py`. Shell environment variables now take precedence over `.env`, which takes precedence over `.env.example`; `.env` remains local/gitignored runtime config, and `.env.example` is the committed safe template/fallback.
  - Scope: `backend/app/core/settings.py`, `.env.example`, `backend/tests/unit/core/test_settings.py`, `backend/app/runtimes/llm/ollama_runtime.py`, `backend/tests/conftest.py`, `backend/tests/runtime/voice/test_llm_live.py`, `backend/tests/runtime/turn/test_text_turn_live.py`, `backend/tests/runtime/turn/test_voice_turn_live.py`, `backend/tests/runtime/acceleration_matrix/test_acceleration_matrix.py`
  - Host class(es): Windows x64
  - Evidence: `backend\.venv\Scripts\python -m compileall backend/app/core backend/app/runtimes/llm backend/tests` PASS; `backend\.venv\Scripts\python -m pytest backend/tests/unit/core/test_settings.py -q` PASS with `6 passed`; `backend\.venv\Scripts\python scripts/validate_backend.py unit` PASS with `135 passed`; `$env:JARVISV7_LIVE_TESTS="1"` then `backend\.venv\Scripts\python scripts/validate_backend.py runtime --families llm` PASS with `1 passed, 6 deselected`; `$env:JARVISV7_LIVE_TESTS="1"` then `backend\.venv\Scripts\python scripts/validate_backend.py runtime --families turn` PASS with `2 passed, 5 deselected`; `backend\.venv\Scripts\python scripts/validate_backend.py regression` PASS with `63 passed`.
    ```text
    canonical Ollama vars: OLLAMA_BASE_URL, OLLAMA_MODEL
    legacy alias only: JARVISV7_OLLAMA_URL
    settings fields added: OLLAMA_NUM_CTX, JARVISV7_LIVE_TESTS
    runtime/test Ollama gates consume settings where in scope; .env.example contains safe non-secret/default values
    ```

- 2026-04-26 21:17
  - Summary: Slice C.1 Minimal Voice/Text Turn was implemented and validated on Windows x64. A canonical conversation state guard, `TurnContext`, synchronous `TurnEngine` with shared text/voice reasoning path, explicit failure-to-`FAILED` behavior, minimal personality boundary, prompt/responder helpers, thin turn/task/voice services, default personality config, and focused unit/runtime turn tests were added.
  - Scope: `backend/app/conversation/`, `backend/app/cognition/`, `backend/app/personality/`, `backend/app/services/`, `config/personality/default.yaml`, `backend/tests/unit/conversation/`, `backend/tests/unit/cognition/`, `backend/tests/unit/personality/`, `backend/tests/unit/services/`, `backend/tests/runtime/turn/`
  - Host class(es): Windows x64
  - Evidence: `backend\.venv\Scripts\python -m compileall backend/app/conversation backend/app/cognition backend/app/personality backend/app/services` PASS; focused C.1 unit suite PASS with `27 passed`; after env standardization, `backend\.venv\Scripts\python scripts/validate_backend.py unit` PASS with `135 passed`; `backend\.venv\Scripts\python scripts/validate_backend.py runtime --families turn` PASS with `2 passed, 5 deselected`; `backend\.venv\Scripts\python scripts/validate_backend.py regression` PASS with `63 passed`.
    ```text
    C.1 scope only: no playback, artifacts, memory continuity, interruption, tools, agents, desktop, API routes, or Group D+ work introduced
    Windows x64 only; no ARM64 validation or full cross-host C.1 closeout claimed
    ```

- 2026-04-26 19:45
  - Summary: B.5 Acceleration Vetting Gate was implemented as a known-state matrix/reporting gate and validated on Windows x64 and Windows ARM64.
  - Scope: `backend/tests/runtime/acceleration_matrix/test_acceleration_matrix.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64: `git status --short` was clean before final validation; `backend\.venv\Scripts\python -m compileall backend\tests\runtime\acceleration_matrix` PASS; `backend\.venv\Scripts\python scripts\validate_backend.py matrix` PASS with `1 passed`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `63 passed`; matrix excerpt included `host,class,PASS,arch=amd64` and no `BLOCKED-*` cells. Windows ARM64: `backend\.venv\Scripts\python -m compileall backend\tests\runtime\acceleration_matrix` PASS; `backend\.venv\Scripts\python scripts\validate_backend.py matrix` PASS with `1 passed`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `63 passed`; matrix excerpt included `host,class,PASS,arch=arm64` and no `BLOCKED-*` cells.
    ```text
    x64: matrix 1 passed; regression 63 passed; host,class,PASS,arch=amd64; no BLOCKED-* cells
    arm64: matrix 1 passed; regression 63 passed; host,class,PASS,arch=arm64; no BLOCKED-* cells
    notable states: STT/TTS/Wake CPU PASS; STT QNN PENDING-H.2; TTS QNN and Wake acceleration N/A
    CUDA/DirectML: SKIP when execution provider not proven; LLM Ollama/local: SKIP-no-ollama when env gate unset
    ```
  - Note: Matrix cells are classified from profiler/preflight/runtime/env evidence. The gate does not duplicate B.1-B.4 live runtime probes, download models, play audio, or start/stop services; any `BLOCKED-*` cell fails the gate. No Slice B completion or `SYSTEM_INVENTORY.md` update is claimed.

- 2026-04-26 18:57
  - Summary: B.4 Wake Runtime Family was validated on Windows x64 and Windows ARM64. Existing openWakeWord CPU path validation passed on both hosts, and no implementation changes were required during the final validation pass.
  - Scope: `backend/app/runtimes/wake/`, `backend/tests/unit/runtimes/wake/test_wake_runtime.py`, `backend/tests/runtime/voice/test_wake_live.py`, `backend/tests/fixtures/hey_jarvis.wav`, `backend/tests/conftest.py`, `pyproject.toml`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64: `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS with wake `missing=[]`; `backend\.venv\Scripts\python -m compileall backend\app\runtimes\wake` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit\runtimes\wake -q` PASS with `8 passed`; `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families wake` PASS with `1 passed, 3 deselected`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `63 tests`. Windows ARM64: `git status --short` clean before validation; same command sequence PASS with wake `missing=[]` and `ready=true`, compileall PASS, wake unit `8 passed`, runtime `1 passed, 3 deselected`, and regression `63 passed`.
    ```text
    x64: wake missing=[]; 8 passed; runtime wake: 1 passed, 3 deselected; regression: 63 tests
    arm64: clean status; wake missing=[], ready=true; 8 passed; runtime wake: 1 passed, 3 deselected; regression: 63 passed
    ```
  - Note: Porcupine remained structural-only and was not live-validated. No Slice B completion or `SYSTEM_INVENTORY.md` update is claimed.

- 2026-04-26 10:17
  - Summary: Sub-Slice B.3 LLM runtime family was implemented and validated on Windows x64 and Windows ARM64.
  - Scope: `backend/app/runtimes/llm/`, `backend/app/routing/runtime_selector.py`, `config/app/policies.yaml`, `config/models/llm.yaml`, `.env.example`, `backend/tests/conftest.py`, `backend/tests/unit/runtimes/llm/test_llm_runtime.py`, `backend/tests/unit/routing/test_runtime_selector.py`, `backend/tests/runtime/voice/test_llm_live.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64: `backend\.venv\Scripts\python -m compileall backend\app\runtimes\llm backend\app\routing` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit\runtimes\llm backend\tests\unit\routing -q` PASS with `13 passed`; `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families llm` PASS with `1 passed, 2 deselected`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `63 tests`. Windows ARM64: same command sequence PASS with compileall PASS, LLM/routing unit `13 passed`, runtime `1 passed, 2 deselected`, and regression `63 passed`.
    ```text
    x64: compileall PASS; 13 passed; runtime llm: 1 passed, 2 deselected; regression: 63 tests
    arm64: compileall PASS; 13 passed; runtime llm: 1 passed, 2 deselected; regression: 63 passed
    ```
  - Note: Local Ollama live validation used `phi4-mini`. Cloud runtimes are policy-gated stubs only, llama.cpp remains deferred to ~~H.1~~ M.1, and no Slice B completion or `SYSTEM_INVENTORY.md` update is claimed.

- 2026-04-26 07:49
  - Summary: B.2 TTS runtime family was implemented and validated for CPU no-playback synthesis on Windows x64 and Windows ARM64.
  - Scope: `backend/app/runtimes/tts/`, `backend/tests/unit/runtimes/tts/test_tts_runtime.py`, `backend/tests/runtime/voice/test_tts_live.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64: `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS with TTS `ready=true` and `missing=[]`; `backend\.venv\Scripts\python -m compileall backend\app\runtimes\tts backend\app\models` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit\runtimes\tts -q` PASS with `8 passed`; `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families tts --devices cpu` PASS with `1 passed, 1 deselected`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `63 tests`. Windows ARM64: same command sequence PASS with TTS `ready=true` and `missing=[]`, compileall PASS, TTS unit `8 passed`, runtime `1 passed, 1 deselected`, and regression `63 passed`.
    ```text
    x64: TTS ready=true, missing=[]; 8 passed; runtime tts cpu: 1 passed, 1 deselected; regression: 63 tests
    arm64: TTS ready=true, missing=[]; 8 passed; runtime tts cpu: 1 passed, 1 deselected; regression: 63 passed
    ```
  - Note: No audio playback validation was performed. No Slice B completion or `SYSTEM_INVENTORY.md` update is claimed.

- 2026-04-26 07:12
  - Summary: B.1 STT live test fixture loading was corrected on Windows ARM64. `backend/tests/runtime/voice/test_stt_live.py` now loads `hello_world.wav` with stdlib `wave` plus `numpy` instead of `soundfile`.
  - Scope: `backend/tests/runtime/voice/test_stt_live.py`, ARM64 validation evidence
  - Host class(es): Windows ARM64
  - Evidence: `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS with STT `missing=[]` and `ready=true`; `backend\.venv\Scripts\python -m compileall backend\tests\runtime\voice\test_stt_live.py` PASS; `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt --devices cpu` PASS with `1 passed`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `63 passed`.
    ```text
    STT missing=[], ready=true
    Compiling 'backend\\tests\\runtime\\voice\\test_stt_live.py'...
    runtime --families stt --devices cpu: 1 passed
    regression: 63 passed
    ```
  - Note: The ARM64 `soundfile`/`libsndfile.dll` load failure was isolated to the test fixture loader. This does not claim Slice B completion.

- 2026-04-25 19:50
  - Summary: B.1 STT live CPU validation was tightened to use the supplied known-audio fixture. `backend/tests/runtime/voice/test_stt_live.py` now loads `backend/tests/fixtures/hello_world.wav` and validates a normalized `hello world` transcript through the repository validation authority.
  - Scope: `backend/tests/runtime/voice/test_stt_live.py`, `backend/tests/fixtures/hello_world.wav`
  - Host class(es): Windows x64
  - Evidence: `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS with STT `ready=true` and `missing=[]`; `backend\.venv\Scripts\python -m compileall backend\tests\runtime\voice\test_stt_live.py` PASS; `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt --devices cpu` PASS with `1 passed`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `63 tests`.
    ```text
    STT ready=true, missing=[]
    Compiling 'backend\\tests\\runtime\\voice\\test_stt_live.py'...
    runtime --families stt --devices cpu: 1 passed
    PASS: unit: 63 tests
    ```
  - Note: Validation was Windows x64 only. This does not claim ARM64 validation, full B.1 both-host closeout, `SYSTEM_INVENTORY.md` update, or Slice B completion.

- 2026-04-25 19:25
  - Summary: B.1 STT runtime boundary was validated on the current Windows x64 CPU path using the repository validation authority. The runtime package, unit boundary, and live STT smoke path were present and passed validation.
  - Scope: `backend/app/runtimes/stt/`, `backend/tests/unit/runtimes/stt/test_stt_runtime.py`, `backend/tests/runtime/voice/test_stt_live.py`
  - Host class(es): Windows x64
  - Evidence: `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS with STT `ready=true` and `missing=[]`; `backend\.venv\Scripts\python -m compileall backend\app\runtimes\stt backend\app\models scripts\validate_backend.py` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit\runtimes\stt -q` PASS with `10 passed`; `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt --devices cpu` PASS with `1 passed`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `63 tests`.
    ```text
    STT ready=true, missing=[]
    10 passed
    runtime --families stt --devices cpu: 1 passed
    PASS: unit: 63 tests
    ```
  - Note: This validates the current Windows x64 CPU STT smoke path only. It does not claim full B.1 closeout, ARM64 validation, Slice B completion, or the planned known-audio fixture transcript acceptance.

- 2026-04-25 19:20
  - Summary: The backend validator CPU device filter was corrected so `--devices cpu` is treated as the baseline runtime device and no nonexistent `cpu` pytest marker is required.
  - Scope: `scripts/validate_backend.py`, `backend/tests/unit/scripts/test_validate_backend_script.py`
  - Host class(es): Windows x64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\scripts\test_validate_backend_script.py -q` PASS with `9 passed`; `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt --devices cpu` no longer deselected due to a nonexistent `cpu` marker and PASSed with `1 passed`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `63 tests`.
    ```text
    9 passed
    runtime --families stt --devices cpu: 1 passed
    PASS: unit: 63 tests
    ```

- 2026-04-25 12:40
  - Summary: B.0 STT model acquisition completeness was corrected to include the ONNX support metadata required by the installed `onnx_asr` helper.
  - Scope: `scripts/ensure_models.py`, `config/models/stt.yaml`
  - Host class(es): Windows x64
  - Evidence: `backend\.venv\Scripts\python scripts\ensure_models.py --family stt` PASS; `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS with STT `ready=true` and `missing=[]`; `backend\.venv\Scripts\python -m compileall scripts\ensure_models.py` PASS; `backend\.venv\Scripts\python -c "from pathlib import Path; import onnx_asr; m=onnx_asr.load_model('onnx-community/whisper-small', path=Path('models/stt/whisper-small-onnx'), providers=['CPUExecutionProvider']); print(type(m).__name__)"` PASS with `TextResultsAsrAdapter`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `61 passed`.
    ```text
    STT ready=true, missing=[]
    TextResultsAsrAdapter
    61 passed
    ```

- 2026-04-25 12:40
  - Summary: B.0 STT model acquisition completeness was corrected on Windows x64. `models/stt/whisper-small-onnx` now includes the ONNX weights plus source-confirmed support files required by the installed `onnx_asr` helper, and `ensure_models.py --verify-only` requires those files before reporting STT ready.
  - Scope: `scripts/ensure_models.py`, `config/models/stt.yaml`
  - Host class(es): Windows x64
  - Evidence: `backend\.venv\Scripts\python scripts\ensure_models.py --family stt` PASS; `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS; `backend\.venv\Scripts\python -m compileall scripts\ensure_models.py` PASS; `backend\.venv\Scripts\python -c "from pathlib import Path; import onnx_asr; m=onnx_asr.load_model('onnx-community/whisper-small', path=Path('models/stt/whisper-small-onnx'), providers=['CPUExecutionProvider']); print(type(m).__name__)"` PASS with `TextResultsAsrAdapter`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `61 passed`.
    ```text
    arch=amd64
    acquired: encoder_model.onnx, decoder_model_merged.onnx, config/tokenizer support files
    TextResultsAsrAdapter
    61 passed
    ```
  - Note: Validation was Windows x64 only. No B.1 runtime implementation, `SYSTEM_INVENTORY.md` update, or Slice B closeout was introduced.

- 2026-04-25 10:03
  - Summary: B.0 model catalog and model acquisition activation was validated on Windows ARM64. No code edits were made; provisioning, model acquisition, final verification, and regression all passed.
  - Scope: Windows ARM64 B.0 validation evidence only; no repository files changed except this log entry
  - Host class(es): Windows ARM64
  - Evidence: `backend\.venv\Scripts\python scripts\provision.py install` PASS with `huggingface_hub-1.12.0` installed through provisioning; `backend\.venv\Scripts\python -m compileall scripts\ensure_models.py backend\app\models` PASS; `backend\.venv\Scripts\python scripts\ensure_models.py --family llm` PASS with `ollama_manages_models`; initial `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` reported missing STT/TTS/Wake files as expected; `backend\.venv\Scripts\python scripts\ensure_models.py --family wake` PASS; `backend\.venv\Scripts\python scripts\ensure_models.py --family tts` PASS; `backend\.venv\Scripts\python scripts\ensure_models.py --family stt` PASS; final `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS with `ready=true` and `missing=[]`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `61 passed`.
    ```text
    arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev]
    ollama_manages_models
    acquired: hey_jarvis_v0.1.onnx, melspectrogram.onnx, embedding_model.onnx
    acquired: kokoro-v1.0.onnx, voices-v1.0.bin
    acquired: encoder_model.onnx, decoder_model_merged.onnx
    final verify-only: ready=true, missing=[]
    61 passed
    ```
  - Note: This records B.0 Windows ARM64 validation only. It does not claim Slice B completion.

- 2026-04-25 09:50
  - Summary: B.0 model catalog and model acquisition activation was completed on Windows x64. `ensure_models.py` now verifies/acquires STT, TTS, and Wake model artifacts, LLM acquisition reports the Ollama-managed no-op, and Slice A regression remained green.
  - Scope: `scripts/ensure_models.py`, `backend/app/models/catalog.py`, `config/models/stt.yaml`, `config/models/tts.yaml`, `config/models/wake.yaml`, `pyproject.toml`
  - Host class(es): Windows x64
  - Evidence: `backend\.venv\Scripts\python scripts\provision.py install` PASS after using Windows path separators; `backend\.venv\Scripts\python -m compileall scripts\ensure_models.py backend\app\models` PASS; `backend\.venv\Scripts\python scripts\ensure_models.py --family llm` PASS with `ollama_manages_models`; initial `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` reported missing STT/TTS/Wake files as expected; `backend\.venv\Scripts\python scripts\ensure_models.py --family wake` PASS; `backend\.venv\Scripts\python scripts\ensure_models.py --family tts` PASS; `backend\.venv\Scripts\python scripts\ensure_models.py --family stt` PASS; final `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS with all B.0 files present; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `61 passed`.
    ```text
    arch=amd64
    ollama_manages_models
    present: STT/TTS/Wake model files
    61 passed
    ```
  - Note: Validation was Windows x64 only. No B.1-B.5 runtime implementation, tests, fixtures, markers, sentinel changes, `SYSTEM_INVENTORY.md` update, or Slice B closeout was introduced.

- 2026-04-24 17:16
  - Summary: A.6 QNN capability definition was completed on Windows ARM64 as structural metadata/readiness only. QNN definition now emits metadata-only structural tokens, while STT readiness remains CPU-selected with the H.2-named QNN inference pending reason.
  - Scope: `backend/app/hardware/preflight.py`, `backend/app/hardware/readiness.py`, `backend/tests/unit/hardware/test_qnn_slot.py`, ARM64 validation evidence
  - Host class(es): Windows ARM64
  - Evidence: `backend\.venv\Scripts\python -m compileall backend\app\hardware\preflight.py backend\app\hardware\readiness.py backend\tests\unit\hardware\test_qnn_slot.py` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit\hardware\test_qnn_slot.py -q` PASS with `8 passed`; `backend\.venv\Scripts\python scripts\validate_backend.py profile` PASS with ARM64 fingerprint `arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready; tokens=15`; QNN structural tokens are emitted as metadata only via `import:onnxruntime-qnn`, `ep:QNNExecutionProvider:MISSING`, and `dll:QnnHtp:MISSING`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS with `61 passed`, `UNIT=PASS`, `[PASS] JARVISv7 backend regression is validated!`; report file `reports\validation\20260424171638-regression.txt` records the ARM64 regression PASS artifact.
    ```text
    8 passed
    tokens=15
    61 passed
    reports\validation\20260424171638-regression.txt
    ```
  - Note: `ep:QNNExecutionProvider` and `dll:QnnHtp` remained missing/not proven, which was expected for definition-only A.6 and did not imply QNN runtime execution. No Group B runtime/model/voice work was introduced.

- 2026-04-24 15:43
  - Summary: A.5 ARM64 local validation proof was recorded from repo-local profile and regression artifacts. Windows ARM64 local profile and regression validation passed, and the ARM64 profile/regression artifacts now exist locally.
  - Scope: `CHANGE_LOG.md`, ARM64 local validation evidence for Slice A.5
  - Host class(es): Windows ARM64
  - Evidence: `reports/diagnostics/20260424154255-profile.txt` records the ARM64 local profile artifact; `reports/validation/20260424154318-regression.txt` records the ARM64 local regression PASS artifact; these artifacts supplement the earlier manual-host proof. Codex temp-directory/pytest cleanup failures remained classified as tooling-context only and did not invalidate manual host proof.
    ```text
    reports/diagnostics/20260424154255-profile.txt
    reports/validation/20260424154318-regression.txt
    ```
  - Note: No Group B runtime/model/voice work was introduced.

- 2026-04-24 10:30
  - Summary: A.5 provisioning gate was accepted from manual clean-venv validation on Windows x64 and Windows ARM64. Both host classes completed provisioning, profile, and regression checks, and the Codex temp-cleanup failures were classified as tooling-context only.
  - Scope: `scripts/provision.py`, `scripts/validate_backend.py`, manual Windows x64/ARM64 provisioning and regression validation evidence
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Manual Windows x64 clean-venv provisioning/profile/regression PASS; `reports/validation/20260424150028-regression.txt` records the x64 regression PASS artifact; manual Windows ARM64 clean-venv provisioning/profile/regression PASS; `reports/validation/20260424085330-validation-regression-arm64.txt` records the ARM64 regression artifact; latest user-side x64 regression console showed 53/53 PASS; Codex regression temp-directory failures remained isolated to the Agent/tooling context and did not invalidate host proof
    ```text
    summary: PASS
    52 passed in 0.07s
    ```
  - Note: No ARM64 profile report artifact was present in the repo-local `reports/diagnostics/` tree at the time of this entry. No Group B runtime/model/voice work was introduced.

- 2026-04-23 14:31
  - Summary: Sub-Slice A.4 added the arch-aware test harness scaffolding and the script-level validator/bootstrap/ensure-models entry points.
  - Scope: `backend/tests/conftest.py`, `backend/tests/integration/__init__.py`, `backend/tests/runtime/__init__.py`, `backend/tests/runtime/hardware/__init__.py`, `backend/tests/runtime/acceleration_matrix/__init__.py`, `backend/tests/fixtures/__init__.py`, `scripts/validate_backend.py`, `scripts/bootstrap.py`, `scripts/ensure_models.py`, `backend/tests/unit/scripts/test_validate_backend_script.py`, `backend/tests/unit/scripts/test_bootstrap_script.py`
  - Host class(es): Windows host (current workspace)
  - Evidence: `backend/.venv/Scripts/python -m compileall scripts backend/tests`; `backend/.venv/Scripts/python scripts/validate_backend.py --help`; `backend/.venv/Scripts/python scripts/bootstrap.py --help`; `backend/.venv/Scripts/python scripts/ensure_models.py`
    ```text
    [CHECKPOINT 1/5] profile -> PASS ...
    No module named pytest
    ```
  - Note: `pytest` was still missing in `backend/.venv` during validation.

- 2026-04-23 14:31
  - Summary: Sub-Slice A.3 added the hardware preflight rail and readiness derivation helpers.
  - Scope: `backend/app/hardware/preflight.py`, `backend/app/hardware/readiness.py`, `backend/tests/unit/hardware/test_preflight.py`, `backend/tests/unit/hardware/test_readiness.py`
  - Host class(es): Windows host (current workspace)
  - Evidence: `backend/.venv/Scripts/python -m compileall backend/app/hardware backend/tests/unit/hardware`; dependency-free smoke for preflight cache and readiness tuple output
    ```text
    ('cuda', True, 'ep:CUDAExecutionProvider proven; selecting cuda')
    ```
  - Note: `pytest` was still missing in `backend/.venv` during validation.

- 2026-04-23 14:31
  - Summary: Sub-Slice A.2 added the declarative provisioning resolver, provisioning script, and supporting core helpers.
  - Scope: `backend/app/core/paths.py`, `backend/app/core/logging.py`, `backend/app/core/settings.py`, `backend/app/hardware/provisioning.py`, `scripts/provision.py`, `backend/tests/unit/hardware/test_provisioning.py`, `backend/tests/unit/scripts/test_provision_script.py`
  - Host class(es): Windows host (current workspace)
  - Evidence: `backend/.venv/Scripts/python -m compileall backend/app/core backend/app/hardware scripts/provision.py backend/tests/unit`; dependency-free smoke for `dry-run`, `install --dry-run`, `verify`, and `lock`
    ```text
    dry_run_code= 0
    install_dry_code= 0
    verify_code= 1
    lock_code= 0
    ```
  - Note: `pytest` was still missing in `backend/.venv` during validation.

- 2026-04-23 14:31
  - Summary: Sub-Slice A.1 added the hardware capability profile and detector layer.
  - Scope: `backend/app/core/capabilities.py`, `backend/app/hardware/__init__.py`, `backend/app/hardware/detectors/__init__.py`, `backend/app/hardware/detectors/cpu_detector.py`, `backend/app/hardware/detectors/memory_detector.py`, `backend/app/hardware/detectors/os_detector.py`, `backend/app/hardware/detectors/gpu_detector.py`, `backend/app/hardware/detectors/cuda_detector.py`, `backend/app/hardware/detectors/npu_detector.py`, `backend/app/hardware/profiler.py`, `backend/tests/unit/hardware/test_profiler.py`
  - Host class(es): Windows host (current workspace)
  - Evidence: `backend/.venv/Scripts/python -m compileall backend/app/core backend/app/hardware backend/tests`; dependency-free smoke for `run_profiler()`
    ```text
    PASS A.1 smoke
    ```
  - Note: `pytest` was still missing in `backend/.venv` during validation.
- 2026-04-22 14:15
  - Summary: CHANGE_LOG.md established
  - Scope: CHANGE_LOG.md
  - Evidence: `cat .\CHANGE_LOG.md -head 1`
    ```text
    # CHANGE_LOG.md
    ```
