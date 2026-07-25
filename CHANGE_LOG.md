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

- Timestamp: 2026-07-25 15:05
  - Host class(es): Windows AMD64
  - Summary: Upgraded the active semantic-memory database from schema version 2 to version 3 through the production initializer and expanded v2 migration coverage for stored governed data.
  - Scope: Active semantic-memory schema initialization and focused semantic-memory migration test coverage; no extraction, retrieval, desktop, or cleanup behavior changed.
  - Validation: Focused pytest PASS (`4 passed, 27 deselected`): `backend/.venv/Scripts/python.exe -m pytest -q backend/tests/unit/memory/test_semantic.py -k 'version_two or repeat_initialization_after_migration or unknown_future_user_version or partial_version_zero or rollback'`. Production initializer reported `schema_ready=True`, `schema_error=None`, and the active database reported `user_version=3` with all eight version-3 curation result columns.
  - Notes: The transactional v2-to-v3 migration was already present in production code; this work exercised it against the active database and added preservation assertions for facts, evidence/events, policy, content revision, and curation jobs.

---

- Timestamp: 2026-07-25 14:49
  - Host class(es): Windows AMD64
  - Summary: Removed inactive semantic-memory controls from the turn write policy so persisted curation policy remains the sole authority for post-session semantic curation.
  - Scope: Write-policy contract and focused memory/session-service tests; working-memory and episodic-memory policy controls were unchanged.
  - Validation: Focused pytest PASS (`40 passed`): `backend/.venv/Scripts/python.exe -m pytest -q backend/tests/unit/memory/test_working_memory.py backend/tests/unit/memory/test_episodic.py backend/tests/unit/services/test_session_service.py`.
  - Notes: No extraction, lifecycle, retrieval, desktop, schema, migration, or runtime-policy behavior changed.

---

- Timestamp: 2026-07-25 14:42
  - Host class(es): Windows AMD64
  - Summary: Wired the default backend startup path to construct and retain episodic memory, making it available to initial and replacement session turn engines.
  - Scope: Backend API startup composition and focused application-lifecycle coverage; existing episodic write, retrieval, retention, and failure-isolation behavior was reused unchanged.
  - Validation: Focused pytest PASS (`63 passed, 1 warning`): `backend/.venv/Scripts/python.exe -m pytest -q backend/tests/unit/api/test_app_lifecycle.py backend/tests/unit/conversation/test_engine.py backend/tests/unit/memory/test_episodic.py`.
  - Notes: No model generation, live runtime validation, policy change, schema change, or configuration change was performed.

---

- Timestamp: 2026-07-25 09:21
  - Host class(es): Windows AMD64
  - Summary: Added the governed semantic-memory desktop surface for opt-in retention, bounded inspection, evidence/lifecycle review, backend-owned actions, forgetting, and truthful curation status.
  - Scope: Desktop renderer/Tauri memory bridge, hidden operator memory panel and settings focus coordination, scoped presentation, focused Node behavior tests, and desktop static-contract coverage.
  - Validation: Desktop Node tests PASS; Cargo check PASS with one Windows incremental-cache finalization warning; desktop static contract PASS (`33 passed`); unit validator PASS (`852 passed, 4 skipped, 1 warning`).
  - Notes: PR #49 closed issue #40; no production build/package or Agent-claimed manual UI validation was performed.

---

- Timestamp: 2026-07-25 07:15
  - Host class(es): Windows AMD64
  - Summary: Exposed typed, bounded governed-memory policy, inspection, lifecycle, forgetting, and curation-status contracts through the backend API with optimistic-concurrency conflict reporting and sanitized responses.
  - Scope: Memory application service, API schemas/routes/dependency injection, startup composition, focused service/API coverage, and the approved resident-voice hook test synchronization.
  - Validation: Focused memory tests PASS (`13 passed`); services tests PASS (`174 passed`); API tests PASS (`77 passed`); unit validator PASS (`851 passed, 4 skipped`); integration validator PASS (`10 passed`); focused Ruff checks PASS.
  - Notes: PR #48 preserved the existing curation drain route and added no retry endpoint; desktop, retrieval, curation, lifecycle, and model behavior were unchanged, and forgetting does not erase separate source turn/session artifacts.

---

- Timestamp: 2026-07-25 06:13
  - Host class(es): Windows AMD64
  - Summary: Added lifecycle-aware governed semantic retrieval with source-stable RRF fusion, semantic revision cache identity, untrusted prompt references, and structured turn-artifact provenance.
  - Scope: Semantic-memory SQL eligibility, hybrid retrieval ranking/cache contracts, prompt assembly, turn artifact/engine persistence, and focused memory/cognition/conversation/artifact tests.
  - Validation: Retrieval tests PASS (`27 passed`); semantic tests PASS (`30 passed`); cognition tests PASS (`22 passed`); conversation tests PASS (`80 passed`); focused two-turn integration PASS (`4 passed`); unit validator PASS (`838 passed, 4 skipped`); integration validator PASS (`10 passed`).
  - Notes: Preserved three-list RRF with `k=60`, optional fail-open caching, existing `retrieved_memory_refs`, and read-only lifecycle behavior; curation, lifecycle transitions, APIs, desktop UI, embeddings, and model/runtime policy were unchanged.

---

- Timestamp: 2026-07-24 18:48
  - Host class(es): Windows AMD64
  - Summary: Added bounded typed memory extraction and durable review-only reconciliation through the deferred curation processor, with strict persisted evidence verification, deterministic exclusions, and resumable per-candidate idempotency.
  - Scope: Cognition extraction envelope, unclassified pending-review policy, production curation processor composition, bounded processor results, API startup injection, and focused unit/integration coverage.
  - Validation: Cognition tests PASS (`21 passed`); memory tests PASS (`104 passed`); services tests PASS (`168 passed`); unit validator PASS (`813 passed, 4 skipped`); integration validator PASS (`10 passed`); focused Ruff checks PASS.
  - Notes: Model-proposed identity and lifecycle actions remain advisory. No automatic activation, reinforcement, dispute, correction, or supersession; retrieval, APIs, desktop UI, and model/runtime policy were unchanged.

---

- Timestamp: 2026-07-24 14:56
  - Host class(es): Windows AMD64
  - Summary: Prevented FastAPI shutdown from stopping the managed LLM sidecar while an in-flight non-preemptible curation processor still owns the shared coordinator, and narrowed the curation API to the required POST drain bridge.
  - Scope: `backend/app/api/app.py`, `backend/app/api/routes/memory_curation.py`, and focused API lifecycle/route tests; the #34 governed lifecycle and #36 curation-job schema were otherwise unchanged.
  - Validation: Affected lifecycle, route, service, and #34 lifecycle tests PASS (`40 passed`); session tests PASS (`25 passed`); service tests PASS (`167 passed`); unit validator PASS (`807 passed, 5 skipped`); integration validator PASS (`9 passed`); profile and desktop static tests PASS.
  - Notes: A Cargo check rerun was environment-blocked twice by transient Windows object-file locks (`os error 32`); the unchanged desktop diff had already passed Cargo check before this backend-only correction. No application packaging build was run.

---

- Timestamp: 2026-07-24 14:30
  - Host class(es): Windows AMD64
  - Summary: Added resumable deferred memory-curation execution with durable artifact-first enqueue, bounded shutdown drain, stale-claim recovery, and one shared interactive-priority LLM coordinator.
  - Scope: Backend curation persistence/service/composition, session and turn coordination, curation status/drain routes, Tauri shutdown ordering/timeouts, and focused deterministic tests.
  - Validation: Focused session tests PASS (`25 passed`); service tests PASS (`167 passed`); focused curation/coordinator/lifecycle tests PASS (`14 passed`); unit validator PASS (`807 passed, 5 skipped`); integration validator PASS (`9 passed`); live CUDA LLM/desktop runtime validator PASS (`3 passed, 46 deselected`); desktop static tests PASS; Cargo test PASS (`4 passed`) and Cargo check PASS.
  - Notes: Production extraction, candidate parsing, reconciliation policy, automatic semantic writes, and memory management UI remain out of scope. Application packaging/build was not run per explicit operator direction.

---

- Timestamp: 2026-07-24 13:27
  - Host class(es): Windows AMD64
  - Summary: Added deterministic transactional semantic-memory lifecycle, evidence, policy, curation-job, and content-revision operations with optimistic concurrency and bounded SQLite writer-conflict handling.
  - Scope: `backend/app/memory/curation.py`, `backend/app/memory/semantic.py`, `backend/tests/unit/memory/test_semantic_lifecycle.py`
  - Validation: Focused lifecycle tests PASS (`30 passed`); complete memory tests PASS (`101 passed`); unit validator PASS (`788 passed, 5 skipped`); focused Ruff and Python 3.12 mypy checks PASS.
  - Notes: Governed creation requires the application-owned kind/identity contract from #32; model extraction, workers, retrieval changes, APIs, desktop code, and physical source-artifact deletion remain out of scope.

---

- Timestamp: 2026-07-24 12:26
  - Host class(es): Windows AMD64
  - Summary: Replaced model-owned semantic-memory identity with a strict application boundary that verifies persisted evidence, derives provisional claim keys, and requires trusted application decisions for governed kinds and related claims.
  - Scope: `backend/app/memory/curation_contract.py`, `backend/tests/unit/memory/test_curation_contract.py`
  - Validation: Focused contract tests PASS (`20 passed`); retained 96-output diagnostic compatibility probe PASS (`93 accepted, 3 rejected, 0 mismatches`); memory tests PASS (`71 passed`); unit validator PASS (`758 passed, 5 skipped`); profile and focused Ruff checks PASS.
  - Notes: Model-proposed kind, claim key, and correction relation remain advisory; candidates are unclassified, review-only, direct-transcript-grounded, and cannot automatically activate, reinforce, or supersede. Lifecycle persistence from issue #34 and later children remains out of scope.

---

- Timestamp: 2026-07-24 12:01
  - Host class(es): Windows AMD64
  - Summary: Added the versioned, transactional SQLite semantic-memory governance schema and an idempotent compatibility migration for recognized legacy databases.
  - Scope: `backend/app/memory/semantic.py`, `backend/tests/unit/memory/test_semantic.py`
  - Validation: Focused semantic-memory tests PASS (`27 passed`); unit validator PASS (`739 passed, 4 skipped`); focused Ruff checks PASS.
  - Notes: PR #42 preserved existing facts, vectors, hashes, content-storing FTS5 rowids, deduplication, and retrieval behavior; model extraction, governed claim identity, lifecycle operations, scheduling, and automatic writes remained out of scope.

---

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
