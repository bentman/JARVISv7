# CHANGE_LOG.md
> No edits/reorders/deletes of past entries.
> If an entry is wrong, append a corrective entry in `## Change Appendix`.

## Rules
- Write an entry for codebase change only after objective is complete and supported by evidence.
- Ordering: Entries are maintained in descending chronological order (newest first, oldest last).
- Append location: New entries must be added at the top directly under `## Change Entries`.
- Corrections or clarifications go only below the `## Change Appendix` section.
- Each entry must include:

- Timestamp: `YYYY-MM-DD HH:MM`
  - Host class(es): validated on
  - Summary: description of capability added, 1–2 lines, past tense
  - Scope: exact folders, files, tests, or areas
  - Validation: reproducible evidence
  - Notes: optional constraints or exclusions

---

## Change Entries

- Timestamp: 2026-07-23 15:57
  - Host class(es): Windows AMD64; existing Windows ARM64 and Linux AMD64 catalog evidence preserved
  - Summary: Aligned Qwen-family sampling, made Qwen3 4B the development behavioral default, retained Qwen2.5 0.5B only for explicit diagnostics, and locked model quants and host contexts to the catalog policy.
  - Scope: `config/models/llm.yaml`, Windows quick-start guidance, LLM selection/runtime/profile tests, and managed llama.cpp live conversation coverage.
  - Validation: Focused LLM policy/runtime tests PASS (`57 passed`); dependent provisioning/startup/API tests PASS (`101 passed, 3 skipped`); unit validator PASS (`726 passed, 4 skipped`); regression validator PASS (`149 passed, 3 skipped, 5 deselected`; `reports/validation/20260723205705-regression.txt`); managed Qwen3 8B CUDA live tests PASS (`3 passed`).
  - Notes: Active Qwen3 non-thinking roles use `temperature=0.7`, `top_p=0.8`, `top_k=20`, and `repeat_penalty=1.0`; the legacy Qwen2.5 diagnostic uses its family `repeat_penalty=1.1`.

---

- Timestamp: 2026-07-23 09:17
  - Host class(es): Windows AMD64
  - Summary: Added configurable Ollama model residency and made the structured chat endpoint explicit as the normal conversation path.
  - Scope: Ollama settings, operator config, runtime payloads, model catalog, quick-start docs, and focused settings/API/LLM tests.
  - Validation: Focused tests PASS (`110 passed`); unit validator PASS (`725 passed, 4 skipped`); live Ollama chat PASS (`1 passed`); controlled cold/warm probe PASS.
  - Notes: Default residency is `5m`; the proving host's `30m` override reduced observed load time from `3083 ms` cold to `279 ms` warm.

---

- Timestamp: 2026-07-22 19:48
  - Host class(es): Windows AMD64
  - Summary: Normalized non-thinking Ollama requests, final-content extraction, and token-limit mapping while preserving llama.cpp non-thinking generation policy.
  - Scope: `backend/app/runtimes/llm/ollama_runtime.py`, `backend/tests/unit/runtimes/llm/test_llm_runtime.py`
  - Validation: Focused LLM tests PASS (`43 passed`); unit validator PASS (`725 passed, 4 skipped`); live Qwen3 Ollama final-answer check PASS; managed llama.cpp live checks PASS (`2 passed`).
  - Notes: Qwen3 receives a model-gated `/no_think` compatibility suffix because the installed Ollama renderer still emits thinking metadata despite native `think: false`; application output remains final content only.

---

- Timestamp: 2026-07-22 15:30
  - Host class(es): Windows AMD64
  - Summary: Isolated sidecar lifecycle tests from host processes and tightened managed-process cleanup to exact executable paths.
  - Scope: `backend/app/services/local_llm_sidecar.py`, `backend/tests/unit/services/test_local_llm_sidecar.py`
  - Validation: Focused sidecar tests PASS (`35 passed`); unit validator PASS (`721 passed, 4 skipped`); regression validator PASS (`149 passed, 3 skipped, 5 deselected`); proving-host text path PASS.

---

- Timestamp: 2026-07-21 19:37
  - Host class(es): Windows AMD64
  - Summary: Aligned the wake integration test with current personality and detection-status contracts.
  - Scope: `backend/tests/runtime/desktop/test_wake_integration_live.py`
  - Validation: Unit validator PASS (`719 passed, 4 skipped`); regression validator PASS (`149 passed, 3 skipped, 5 deselected`); focused live wake test PASS (`2 passed`).

---

## Change Appendix

---

## Consolidated Change History

- Timestamp: 2026-07-18 08:06
  - Host class(es): Linux AMD64 validated on WSL2 with NVIDIA CUDA
  - Summary: Hardened managed Linux CUDA llama.cpp source-build, sidecar verification, and genuine portable-model CPU fallback when CUDA serving is unavailable.
  - Scope:
    - `scripts/ensure_models.py`, `backend/app/services/local_llm_startup.py`, `config/models/llm.yaml`
    - focused model, runtime, script, and startup tests
  - Validation:
    - Focused unit suite PASS (`65 passed`).
    - Managed CUDA runtime verification and portable fallback checks PASS.
  - Notes:
    - CUDA toolchain selection remains subprocess-scoped.

- Timestamp: 2026-07-17 06:10
  - Host class(es): Windows AMD64 and Linux ARM64 validated as applicable
  - Summary: Hardened Redis reconnection, retrieval-cache identity, semantic-memory consistency, artifact atomicity, corrupt-artifact tolerance, operator configuration writes, and degraded local-LLM startup behavior.
  - Scope:
    - `backend/app/cache/`
    - `backend/app/memory/`
    - `backend/app/artifacts/`
    - `backend/app/api/routes/config.py`
    - `backend/app/services/local_llm_startup.py`
    - related unit tests
  - Validation:
    - Focused cache, memory, artifact, API, and local-LLM tests PASS.
    - Backend unit validator PASS after platform-specific filesystem tests were gated appropriately.

- Timestamp: 2026-07-08 13:52
  - Host class(es): Windows AMD64 validated; Windows ARM64 validated where noted
  - Summary: Completed resident voice persistence, runtime warmup, TTS voice selection, startup/status stabilization, and accelerated Kokoro TTS support for CUDA, DirectML, and Qualcomm QNN.
  - Scope:
    - `backend/app/runtimes/tts/`
    - `backend/app/runtimes/stt/`
    - `backend/app/runtimes/wake/`
    - `backend/app/services/`
    - `backend/app/api/`
    - `desktop/src/`
    - `config/models/tts.yaml`
  - Validation:
    - Focused backend voice/API/desktop suites PASS.
    - Desktop static tests PASS.
    - Windows AMD64 CUDA/DirectML and Windows ARM64 QNN TTS paths were validated on their recorded hosts.

- Timestamp: 2026-07-04 22:11
  - Host class(es): Windows AMD64 and Windows ARM64 validated as applicable
  - Summary: Completed startup-truth, readiness, diagnostics, conversation-debug, desktop-state, and personality request-path behavior for the local runtime stack.
  - Scope:
    - `backend/app/services/startup_context.py`
    - `backend/app/api/`
    - `backend/app/personality/`
    - `backend/app/cognition/`
    - `backend/app/conversation/`
    - `backend/app/runtimes/llm/`
    - `desktop/src/`, `desktop/src-tauri/`
    - startup and validation scripts
  - Validation:
    - Focused startup, personality, conversation, API, desktop, and sidecar suites PASS on recorded AMD64/ARM64 hosts.
    - Backend unit validator, desktop static tests, and Tauri `cargo check` PASS.

- Timestamp: 2026-07-03 13:19
  - Host class(es): Windows AMD64 and Windows ARM64 validated
  - Summary: Activated local LLM model tiers, operator model policy, Qwen3 production catalog selection, and managed llama.cpp/Ollama runtime selection.
  - Scope:
    - `config/models/llm.yaml`
    - `backend/app/models/`
    - `backend/app/services/local_llm_startup.py`
    - `backend/app/services/local_llm_sidecar.py`
    - `backend/app/runtimes/llm/`
    - `backend/app/routing/`
    - operator configuration and desktop settings surfaces
  - Validation:
    - Focused catalog, selection, startup, sidecar, API, script, and desktop tests PASS.
  - Notes:
    - Current LLM execution is local-first; removed cloud-provider placeholders are not part of this history.

- Timestamp: 2026-06-30 05:44
  - Host class(es): Windows ARM64 Qualcomm QNN validated; Windows AMD64 non-selection validated
  - Summary: Added and validated the side-by-side Qualcomm QNN Whisper STT path while preserving portable fallback behavior.
  - Scope:
    - `backend/app/hardware/qnn_provider.py`
    - `backend/app/runtimes/stt/`
    - `config/models/stt.yaml`
    - hardware, STT, and acceleration-matrix tests
  - Validation:
    - QNN STT unit and live host-gated validation PASS.

- Timestamp: 2026-06-26 10:51
  - Host class(es): Windows AMD64 and Windows ARM64 validated
  - Summary: Established the resident shared-stream voice layer with wake/PTT modes, endpointing, VAD behavior, interruption handling, session status, and desktop controls.
  - Scope:
    - `backend/app/services/`
    - `backend/app/conversation/`
    - `backend/app/runtimes/stt/`, `tts/`, and `wake/`
    - `backend/app/api/`
    - `desktop/src/`
  - Validation:
    - Focused service, conversation, runtime, API, desktop, and live voice suites PASS.

- Timestamp: 2026-06-24 07:48
  - Host class(es): Windows AMD64 and Windows ARM64 validated
  - Summary: Established repo-managed llama.cpp runtime artifacts, serve profiles, acquisition, readiness reporting, and sidecar lifecycle for supported local host classes.
  - Scope:
    - `scripts/ensure_models.py`
    - `config/models/llm.yaml`
    - `backend/app/models/llm_profiles.py`
    - `backend/app/services/local_llm_sidecar.py`
    - `backend/app/hardware/`
    - `runtimes/llama.cpp/`
  - Validation:
    - Artifact acquisition, verification, sidecar, profile, and readiness tests PASS.

- Timestamp: 2026-06-14 10:32
  - Host class(es): Windows AMD64 validated
  - Summary: Added bounded conversation continuity, session timelines, working-memory context, and conservative session closeout behavior.
  - Scope:
    - `backend/app/artifacts/`
    - `backend/app/conversation/`
    - `backend/app/cognition/`
    - related tests
  - Validation:
    - Focused artifact, continuity, conversation, and cognition tests PASS.

- Timestamp: 2026-06-13 18:21
  - Host class(es): Windows AMD64 and Windows ARM64 validated
  - Summary: Added realtime resident-session event coordination while retaining committed turn execution in `TurnEngine`.
  - Scope:
    - `backend/app/conversation/realtime/`
    - `backend/app/services/resident_voice_invocation.py`
    - related service and realtime tests
  - Validation:
    - Focused realtime and resident invocation suites PASS.

- Timestamp: 2026-06-12 11:46
  - Host class(es): Windows AMD64 and Windows ARM64 validated
  - Summary: Added structured personality policy, prompt envelopes, provenance-aware rendering, profile selection, and response-style enforcement.
  - Scope:
    - `config/personality/`
    - `backend/app/personality/`
    - `backend/app/cognition/`
    - `backend/app/conversation/`
    - personality API and tests
  - Validation:
    - Focused personality, cognition, conversation, LLM, API, and desktop tests PASS.

- Timestamp: 2026-05-30 06:58
  - Host class(es): Windows AMD64 and Windows ARM64 validated
  - Summary: Added operator desktop/settings UX, service readiness, wake controls, degraded-state presentation, and host-specific voice readiness.
  - Scope:
    - `desktop/src/`, `desktop/src-tauri/`
    - `backend/app/api/`
    - `backend/app/services/`
    - `backend/app/hardware/`
    - provisioning and desktop tests
  - Validation:
    - Desktop static tests, backend API/readiness tests, and host-specific validation PASS.

- Timestamp: 2026-05-13 14:57
  - Host class(es): Windows AMD64 and Windows ARM64 validated
  - Summary: Added normalized hardware readiness and host-gated live acceleration-matrix validation for voice runtimes.
  - Scope:
    - `backend/app/hardware/`
    - `backend/tests/runtime/acceleration_matrix/`
    - `reports/validation/`
  - Validation:
    - CPU, CUDA, DirectML, and QNN paths were exercised where supported by the recorded host evidence.

- Timestamp: 2026-05-02 22:10
  - Host class(es): Windows AMD64 and Windows ARM64 validated
  - Summary: Added disk-backed episodic and semantic memory, retrieval, prompt-context injection, and Redis-backed retrieval-cache acceleration.
  - Scope:
    - `backend/app/memory/`
    - `backend/app/cache/`
    - `backend/app/conversation/`
    - `backend/app/cognition/`
    - memory and cache tests
  - Validation:
    - Focused memory, retrieval, cache, semantic-index, and integration tests PASS.

- Timestamp: 2026-05-01 01:05
  - Host class(es): Windows AMD64 and Windows ARM64 validated
  - Summary: Added local Redis/SearXNG service composition and fail-closed internet-search runtime providers for future explicit consumers.
  - Scope:
    - `docker-compose.yml`
    - `config/search/`
    - `backend/app/cache/`
    - `backend/app/runtimes/internetsearch/`
    - search runtime and service tests
  - Validation:
    - Service configuration, probes, provider fallback, and failure-boundary tests PASS.
  - Notes:
    - No normal conversation or autonomous search invocation capability is claimed.

- Timestamp: 2026-04-30 11:12
  - Host class(es): Windows AMD64 and Windows ARM64 validated
  - Summary: Established the durable FastAPI backend, session/task/status APIs, desktop shell, personality profiles, and application service boundaries.
  - Scope:
    - `backend/app/api/`
    - `backend/app/services/`
    - `backend/app/conversation/`
    - `backend/app/personality/`
    - `desktop/`
    - backend and desktop tests
  - Validation:
    - Backend API/service tests and desktop static/Tauri validation PASS.
