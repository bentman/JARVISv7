# Memory subsystem census — 2026-07-25

Scope: fresh read-only inspection of current source, callers, focused tests, and the requested operational directories. Historical reports and patch residue are listed only as residue; they were not used as authority. Structural presence, deterministic test evidence, runtime evidence, and observed on-disk state are kept separate.

## 1. Implemented and directly evidenced

### Capture, artifacts, and runtime wiring

- `backend/app/artifacts/turn_artifact.py` — `TurnArtifact` serializes canonical fields: identifiers, modality, transcript, final prompt, response, tools, runtime/phase/failure/TTS data, and both `retrieved_memory_refs` and structured `retrieved_memory_evidence`. `backend/app/artifacts/storage.py` writes it atomically to `data/turns/<session>/<turn>.json`; `backend/tests/unit/artifacts/test_turn_artifact.py` covers canonical fields, atomic replacement, structured provenance round-trip, and loading an older artifact without structured provenance.
- `backend/app/artifacts/session_artifact.py`, `session_timeline.py`, and `storage.py` define/write `data/sessions/<session>/session.json` and `timeline.json`. Session fields include close time, turn IDs, continuity summary, and curation candidate/authorization/policy-revision fields. `SessionManager.close_session` in `backend/app/conversation/session_manager.py` records a close event, writes timeline then session artifact, and sets candidate true only when in-memory turn artifacts exist.
- `WorkingMemory` in `backend/app/memory/working.py` is an in-memory, trim-and-append FIFO (default 10). `SessionManager.update_working_memory` applies `WritePolicy` capacity and stores successful response text; `TurnEngine._record_artifact` calls it only when no turn failure. Consumer: `assemble_prompt_envelope` inserts it as untrusted context. Tests: `backend/tests/unit/memory/test_working_memory.py`, `backend/tests/unit/conversation/test_session_manager.py`, and `backend/tests/unit/conversation/test_engine.py`.
- `EpisodicMemory` in `backend/app/memory/episodic.py` writes per-turn JSON under `data/memory/episodic/<session>/<turn>.json`, subject to policy enabled, no failure, minimum response length, and retention pruning. It reads recent entries by descending `written_at` and keyword matches transcript/response. `TurnEngine._record_artifact` calls it only when an instance was injected. Tests: `backend/tests/unit/memory/test_episodic.py`; injection/order/failure isolation: `backend/tests/unit/conversation/test_engine.py`.
- Exact default API composition: `build_startup_state` in `backend/app/api/app.py` constructs `SemanticMemory`, `CacheManager`, `LLMExecutionCoordinator`, `TurnEngine(... semantic=semantic_memory ...)`, `MemoryCurationService`, `MemoryService`, then starts curation after `recover_and_reconcile()`. It does **not** construct or pass `EpisodicMemory` to that engine. Thus semantic retrieval is wired in this constructor; episodic write/retrieval is structurally available through injected `TurnEngine.episodic` but not through this observed default startup call.
- `backend/app/conversation/engine.py` retrieves up to three facts before prompt assembly if either memory backend is non-null; records prompt/provenance; atomically persists the turn via the session manager; then writes episodic memory (if injected) and working memory as above. Retrieval failure is caught and leaves an empty retrieval list. Focused engine tests cover injected episodic/retrieval/provenance paths; they do not independently prove default API startup uses episodic memory.

### Extraction and governed curation

- `backend/app/cognition/memory_extraction.py`: `MemoryCandidateExtractor.extract` selects last 12 persisted turn artifacts, truncates transcript/response fields to 500 characters, builds a `PromptEnvelope` with trusted application/output contract and untrusted session JSON, calls `LLMBase.generate_envelope`, and strictly parses output. Generation is bounded to 256 tokens. `backend/tests/unit/cognition/test_memory_extraction.py` deterministically checks envelope authority/bounds; no live generation was run here.
- `backend/app/memory/curation_contract.py`: parser accepts one strict JSON object with 0..3 candidates, exact fields, bounded text/value/key/excerpts, finite 0..1 scores, no duplicates/nonstandard JSON/trailing content. Evidence must name allowlisted persisted turn and `transcript|response_text`, and the excerpt must be exact. Transcript maps to direct-user-statement; response maps to assistant-inference. Only transcript-backed candidates become provisional review candidates. Model kind, claim key, value, relation, confidence and importance are advisory; provisional key derives from verified evidence; application identity decision supplies governed kind/key. Tests: `backend/tests/unit/memory/test_curation_contract.py`.
- `backend/app/memory/curation_reconciliation.py`: `ReviewOnlyCurationPolicy` rejects secret-pattern, quoted/external, and application-owned values; otherwise persists an `unclassified`, `pending_review`, direct-user-statement fact with hashed-excerpt metadata. It never auto-confirms or assigns the model's advisory identity. Tests: `backend/tests/unit/memory/test_curation_reconciliation.py`.
- `backend/app/services/memory_curation_processor.py`: runs extraction, provisional construction, then review-only reconciliation and returns bounded typed result counts. `backend/tests/unit/services/test_memory_curation_processor.py` covers retry after partial persistence. `backend/tests/integration/test_memory_curation_review_pipeline.py` uses a deterministic fake LLM and proves one authorized persisted job becomes one pending-review unclassified fact with evidence/event.

### Governance, persistence, and durable execution

- `backend/app/memory/curation.py` defines lifecycle states `pending_review, active, disputed, superseded, expired, forgotten`; direct edges are pending→active/disputed/forgotten, active→disputed/superseded/expired/forgotten, disputed→active/superseded/forgotten; terminal states have no exits. Evidence authorities include direct user statement/action, assistant inference, synthesized summary, imported record, legacy unknown. Inputs enforce bounded IDs/text/metadata/scores/timestamps and application-owned lifecycle/kind/authority.
- `backend/app/memory/semantic.py` is the persistence owner at `data/memory/semantic/memory.sqlite`; source constant is `SEMANTIC_SCHEMA_VERSION = 3`. It uses a connection-local foreign-key check, 250ms busy timeout, `BEGIN IMMEDIATE`, three bounded busy retries/backoff, commit/rollback, and fail-closed `StoreResult` statuses. It supports recognized legacy v0 schema migration, v1→v2 and v2→v3 curation-job migrations; future/partial schemas set `schema_error` and do not mutate.
- Latest source schema includes `semantic_fact`, immutable `semantic_evidence` and `semantic_event`, `semantic_curation_job`, `semantic_policy`, and `semantic_meta`; unique text-hash and evidence-origin indexes, FTS5 when available (otherwise LIKE), policy/meta monotonic triggers, and evidence/event immutable update/delete triggers. Semantic content revision increments for content-changing fact operations and contributes to retrieval cache identity; evidence append does not increment it. Tests: `backend/tests/unit/memory/test_semantic.py` and `test_semantic_lifecycle.py` cover migrations, constraints, FTS fallback, eligibility, transactions, optimistic revisions, transitions, correction/supersession, concurrent mutation, job claims/recovery, and policy default/stale conflicts.
- Fact operations `create_governed_fact, append_evidence, confirm_fact, dispute_fact, expire_fact, forget_fact, reinforce_fact, supersede_fact, correct_fact` require expected revisions where mutation applies. API-originated confirm/dispute/forget/correct uses direct-user-action evidence with a generated action ID. Forget marks only the semantic record; source session/turn artifacts remain separate. The policy singleton defaults automatic curation disabled; updating it cancels queued jobs and requests cancellation for processing jobs when disabled/source policy revision differs.
- `MemoryCurationService` has one daemon worker, but it does work only after explicit `drain()` sets coordinator shutdown-drain state. It enqueues closed authorized sessions; job states are pending, processing, retry_wait, succeeded, failed, cancelled. Claims are atomic, lease-fenced by boot ID/token with 120-second lease and max 3 attempts; failure waits 60 then 300 seconds, stale processing recovers based on boot/lease/policy, and results/runtime identity/timing/error/status fields persist. Admission requires shutdown drain, no active session/interactive waiter, enabled policy, ready LLM, and free coordinator background slot. Startup recovers/reconciles then starts worker; API lifespan stops curation before resident audio/local LLM. Tests: `backend/tests/unit/services/test_memory_curation_service.py`, `test_memory_curation_processor.py`, `test_llm_execution_coordinator.py`, and the integration file above.

### Retrieval and prompt insertion

- `backend/app/memory/retrieval.py`: query `None` is episodic recency only. Query retrieval uses episodic case-insensitive keyword scan plus semantic lexical and hashed-128-dimension vector cosine search. Semantic eligibility is active, permitted kind, unexpired, and unsuperseded. Semantic lexical uses FTS5 BM25 then LIKE fallback; vector scores all eligible vectors. Hybrid fusion is reciprocal-rank fusion (`RRF_K=60`), deduped by source identity and ordered by RRF, authority, confidence, importance, reinforcement, timestamp, then identity. Provenance carries source kind, semantic ID/governance/lifecycle/evidence refs and scores.
- Redis key namespace is `retrieval`; identity includes backend availability, query mode/hash, n, and semantic content revision for semantic queries. TTL is 300 seconds. Revision change invalidates by new key; cache is disabled if semantic revision cannot be read. Cache/Redis failure falls back to direct retrieval; invalid cache payload is ignored. `backend/app/cache/{keys,manager,redis_client}.py` has 30-second Redis reconnection cooldown. Tests: `backend/tests/unit/memory/test_retrieval.py`; live Redis-marked coverage exists in `backend/tests/runtime/services/test_redis_retrieval_cache_live.py`, but was not run.
- `backend/app/cognition/prompt_assembler.py` puts retrieval after continuity/working memory and before current user input, explicitly as untrusted context. It emits episodic short IDs or semantic fact/evidence references. `TurnArtifact.retrieved_memory_evidence` records retrieval provenance. Tests: `backend/tests/unit/cognition/test_prompt_assembler.py`, artifact test, and engine test.

### API and desktop surface

- Backend routes: `backend/app/api/routes/memory.py` exposes GET/PUT `/memory/policy`, GET `/memory/curation/status`, list/detail, confirm/correct/dispute/DELETE forget. `memory_curation.py` exposes POST `/memory/curation/drain`; `session.py` closes sessions and returns curation enqueue outcome. `schemas/memory.py` uses strict models and bounds; `MemoryService` enforces list offset ≤250, limit ≤50, detail ≤50, hides internal metadata/raw evidence excerpts, maps invalid→422, absent→404, revision conflict→409 including current revision/state, unavailable→503, and unexpected→500. Focused API tests: `backend/tests/unit/api/test_memory_routes.py`, `test_memory_curation_routes.py`.
- Desktop renderer: `desktop/src/components/memory-panel.js` owns panel state, bounded filters, curation display, mutation lock, list/detail sequence tokens for stale responses, conflict reload, correction reload, explicit forgetting confirmation, and DOM `textContent` rendering. `createOperatorPanelCoordinator` deterministically closes settings before memory and vice versa. `desktop/src/main.js` wires it to `api-client.js`.
- `desktop/src/api-client.js` invokes Tauri commands and parses structured backend errors. `desktop/src-tauri/src/lib.rs` validates nonblank IDs/text and positive revisions and proxies commands. `desktop/src-tauri/src/backend.rs` maps them to backend HTTP routes and preserves status/body JSON error information. Desktop shutdown closes session, POSTs drain, then kills backend. Static evidence: `desktop/tests/static.test.mjs` tests stale response suppression, mutation/conflict/forget flows, curation rendering, panel coordination, command/route bridges, no direct fetch/localStorage/innerHTML/lifecycle duplication; `backend/tests/unit/desktop/test_desktop_static_contract.py` checks static bridge/panel contracts. No live desktop memory interaction was run.

## 2. Present but not independently validated

- Deterministic unit coverage exists for all major source modules named above, but this investigation did not run tests, broad validation, model generations, or benchmarks.
- Integration coverage is one deterministic fake-LLM curation pipeline (`backend/tests/integration/test_memory_curation_review_pipeline.py`) and two-turn session semantic retrieval (`backend/tests/integration/services/test_two_turn_session.py`).
- Runtime/live test definitions exist for Redis retrieval and continuity/episodic paths (`backend/tests/runtime/services/test_redis_retrieval_cache_live.py`, `backend/tests/runtime/turn/test_continuity_retrieval_live.py`). Their current live behavior was not reproduced.
- No direct test evidence was found for production default startup completing an end-to-end session-close → drain → real LLM → review candidate sequence, nor for desktop-Tauri-live memory mutation. Static desktop tests are not live UI evidence.

## 3. Known incomplete, blocked, contradictory, or unused

- `WritePolicy.write_to_semantic_memory`, `semantic_min_text_length`, `semantic_max_entries_per_session`, `semantic_similarity_dedupe_threshold`, and `semantic_consolidate_on_close` are defined in `backend/app/memory/write_policy.py`; no caller was found in the inspected memory flow. They are not used as the curation-service policy gate, which is `semantic_policy.automatic_curation_enabled`.
- Default startup omits `EpisodicMemory` injection despite the implementation, tests, and retrieval path accepting it.
- On-disk `data/memory/semantic/memory.sqlite` reports SQLite user version **2**; source declares current version **3**. Its readable schema strings show governed tables/triggers and an FTS table, but this inspection did not instantiate `SemanticMemory` or run migration.
- Current `data/sessions` contains 14 session artifacts, each `IDLE`, `memory_curation_candidate=false`, no authorization, and zero turn IDs. Current `data/turns` contains 27 text artifacts, all `FAILED` in LLM phase with the persisted failure `'_FakeRuntime' object has no attribute 'generate_envelope'`; all have zero retrieval references, 21 include structured retrieval-evidence field and six are backward-compatible artifacts without it. This is operational residue, not a conclusion about current code behavior.

## 4. Operational residue and unreadable paths

- `reports/`: backend startup/stderr logs; profile diagnostics; JSON curation/model probe records; and JUnit/regression XML/text records. Content includes historical pass/fail/skip evidence and failure traces. These files were inspected as residue only, not used to establish implementation correctness.
- `cache/temp/`: 758 relevant files: a paused patch plus generated SQLite/session/turn/episodic artifacts grouped under `issue41-*`, `issue50-pytest`, `issue52-*`, and `pytest-of-bentl`. The inspected patch is a historical diff; generated contents are test/probe residue, not product state.
- `data/memory/`: placeholder files plus the SQLite database described above. `data/memory/episodic/` and `working/` contain only `.gitkeep`.
- `data/sessions/`: 14 `session.json` and 14 `timeline.json` files; a sampled timeline contains `session_started`, personality selection, and `session_closed` events.
- `data/turns/`: 27 JSON turn artifacts as summarized above.
- Unreadable paths: none. No permission/ACL access failure occurred; the failed attempt to use the repository-prescribed `backend/.venv/Scripts/python` was a missing-path/tool availability condition, not an artifact read ACL failure.

## 5. Questions requiring a future decision

1. Should default API composition inject and retain `EpisodicMemory`, or is injection-only use intentional?
2. Should the existing on-disk v2 semantic database be migrated to v3 by normal application startup before current product use?
3. Is explicit shutdown-only curation drain the intended operational trigger, given the worker otherwise waits for `drain()`?
4. Are the currently persisted failed-turn/session artifacts retained intentionally, and should they remain separate from semantic forgetting?

## Inspection ledger

Exact files inspected (171):
`AGENTS.md`, `.agentignore`, `backend/AGENTS.md`, `desktop/AGENTS.md`;
`backend/app/artifacts/{session_artifact.py,session_timeline.py,storage.py,trace_writer.py,turn_artifact.py}`;
`backend/app/memory/{working.py,episodic.py,semantic.py,retrieval.py,write_policy.py,curation.py,curation_contract.py,curation_reconciliation.py}`;
`backend/app/cognition/{memory_extraction.py,prompt_assembler.py,prompt_chat_renderer.py,prompt_envelope.py,prompt_renderer.py,responder.py}`;
`backend/app/conversation/{engine.py,session_manager.py,continuity.py,continuity_policy.py}`;
`backend/app/services/{session_service.py,memory_service.py,memory_curation_service.py,memory_curation_processor.py,llm_execution_coordinator.py,startup_context.py}`;
`backend/app/api/{app.py,dependencies.py,routes/memory.py,routes/memory_curation.py,routes/session.py,schemas/memory.py,schemas/session.py}`;
`backend/app/cache/{keys.py,manager.py,redis_client.py}`;
`backend/app/core/{paths.py,settings.py}`;
`desktop/src/{api-client.js,main.js,components/memory-panel.js,components/desktop-state.js,components/settings-panel.js}`;
`desktop/src-tauri/src/{backend.rs,lib.rs,main.rs}`;
`backend/tests/unit/{memory/test_working_memory.py,memory/test_episodic.py,memory/test_retrieval.py,memory/test_semantic.py,memory/test_semantic_lifecycle.py,memory/test_curation_contract.py,memory/test_curation_reconciliation.py,services/test_memory_service.py,services/test_memory_curation_service.py,services/test_memory_curation_processor.py,api/test_memory_routes.py,api/test_memory_curation_routes.py,cognition/test_memory_extraction.py,cognition/test_prompt_assembler.py,artifacts/test_turn_artifact.py,conversation/test_session_manager.py,conversation/test_engine.py,desktop/test_desktop_static_contract.py}`;
`backend/tests/integration/{test_memory_curation_review_pipeline.py,services/test_two_turn_session.py}`;
`backend/tests/runtime/{services/test_redis_retrieval_cache_live.py,turn/test_continuity_retrieval_live.py}`;
`desktop/tests/static.test.mjs`;
all readable files in the requested `reports/`, `data/memory/`, `data/sessions/`, and `data/turns/` directory scopes, plus `cache/temp/issue41-paused-20260725.patch` and enumerated relevant cache-temp residue.

Exact directories inspected:
`reports/`, `reports/diagnostics/`, `reports/validation/`, `reports/benchmarks/`, `cache/temp/`, `data/memory/`, `data/memory/episodic/`, `data/memory/semantic/`, `data/memory/working/`, `data/sessions/`, `data/turns/`, `backend/app/{artifacts,memory,cognition,conversation,services,api,cache,core}/`, `backend/tests/{unit,integration,runtime}/`, `desktop/src/`, `desktop/src-tauri/src/`, `desktop/tests/`.

Exact unreadable paths and error text: none.

Exact `git status --short` output at report creation:

```text
 M .agentignore
 M .codex/config.toml
 M .env.example
 M .flake8
 M .github/AGENTS.md
 M .gitignore
 M .python-version
 M AGENTS.md
 M CHANGE_LOG.md
 M LICENSE
 M ProjectVision.md
 M README.md
 M SYSTEM_INVENTORY.md
 M backend/AGENTS.md
 M backend/app/api/__init__.py
 M backend/app/api/app.py
 M backend/app/api/dependencies.py
 M backend/app/api/routes/config.py
 M backend/app/api/routes/diagnostics.py
 M backend/app/api/routes/health.py
 M backend/app/api/routes/memory.py
 M backend/app/api/routes/memory_curation.py
 M backend/app/api/routes/personality.py
 M backend/app/api/routes/readiness.py
 M backend/app/api/routes/session.py
 M backend/app/api/routes/status.py
 M backend/app/api/routes/task.py
 M backend/app/api/schemas/common.py
 M backend/app/api/schemas/config.py
 M backend/app/api/schemas/diagnostics.py
 M backend/app/api/schemas/memory.py
 M backend/app/api/schemas/personality.py
 M backend/app/api/schemas/readiness.py
 M backend/app/api/schemas/session.py
 M backend/app/api/schemas/status.py
 M backend/app/api/schemas/task.py
 M backend/app/api/service_status.py
 M backend/app/artifacts/session_artifact.py
 M backend/app/artifacts/session_timeline.py
 M backend/app/artifacts/storage.py
 M backend/app/artifacts/trace_writer.py
 M backend/app/artifacts/turn_artifact.py
 M backend/app/cache/__init__.py
 M backend/app/cache/keys.py
 M backend/app/cache/manager.py
 M backend/app/cache/redis_client.py
 M backend/app/cognition/memory_extraction.py
 M backend/app/cognition/prompt_assembler.py
 M backend/app/cognition/prompt_chat_renderer.py
 M backend/app/cognition/prompt_envelope.py
 M backend/app/cognition/prompt_renderer.py
 M backend/app/cognition/responder.py
 M backend/app/cognition/style_guard.py
 M backend/app/conversation/continuity.py
 M backend/app/conversation/continuity_policy.py
 M backend/app/conversation/engine.py
 M backend/app/conversation/realtime/__init__.py
 M backend/app/conversation/realtime/events.py
 M backend/app/conversation/realtime/interruption.py
 M backend/app/conversation/realtime/ledger.py
 M backend/app/conversation/realtime/response_queue.py
 M backend/app/conversation/realtime/session.py
 M backend/app/conversation/realtime/turn_taking.py
 M backend/app/conversation/session_manager.py
 M backend/app/conversation/states.py
 M backend/app/conversation/turn_manager.py
 M backend/app/core/capabilities.py
 M backend/app/core/logging.py
 M backend/app/core/paths.py
 M backend/app/core/settings.py
 M backend/app/hardware/__init__.py
 M backend/app/hardware/detectors/__init__.py
 M backend/app/hardware/detectors/cpu_detector.py
 M backend/app/hardware/detectors/cuda_detector.py
 M backend/app/hardware/detectors/gpu_detector.py
 M backend/app/hardware/detectors/memory_detector.py
 M backend/app/hardware/detectors/npu_detector.py
 M backend/app/hardware/detectors/os_detector.py
 M backend/app/hardware/preflight.py
 M backend/app/hardware/profiler.py
 M backend/app/hardware/provisioning.py
 M backend/app/hardware/qnn_provider.py
 M backend/app/hardware/readiness.py
 M backend/app/memory/curation.py
 M backend/app/memory/curation_contract.py
 M backend/app/memory/curation_reconciliation.py
 M backend/app/memory/episodic.py
 M backend/app/memory/retrieval.py
 M backend/app/memory/semantic.py
 M backend/app/memory/working.py
 M backend/app/memory/write_policy.py
 M backend/app/models/catalog.py
 M backend/app/models/llm_profiles.py
 M backend/app/models/llm_selection.py
 M backend/app/personality/loader.py
 M backend/app/personality/policy.py
 M backend/app/personality/schema.py
 M backend/app/routing/runtime_selector.py
 M backend/app/runtimes/internetsearch/__init__.py
 M backend/app/runtimes/internetsearch/base.py
 M backend/app/runtimes/internetsearch/ddgs_runtime.py
 M backend/app/runtimes/internetsearch/searxng_runtime.py
 M backend/app/runtimes/internetsearch/tavily_runtime.py
 M backend/app/runtimes/llm/__init__.py
 M backend/app/runtimes/llm/base.py
 M backend/app/runtimes/llm/local_runtime.py
 M backend/app/runtimes/llm/ollama_runtime.py
 M backend/app/runtimes/stt/__init__.py
 M backend/app/runtimes/stt/barge_in.py
 M backend/app/runtimes/stt/base.py
 M backend/app/runtimes/stt/onnx_whisper_runtime.py
 M backend/app/runtimes/stt/stt_runtime.py
 M backend/app/runtimes/tts/__init__.py
 M backend/app/runtimes/tts/base.py
 M backend/app/runtimes/tts/kokoro_onnx_runtime.py
 M backend/app/runtimes/tts/playback.py
 M backend/app/runtimes/tts/tts_runtime.py
 M backend/app/runtimes/vad/__init__.py
 M backend/app/runtimes/vad/base.py
 M backend/app/runtimes/vad/energy_runtime.py
 M backend/app/runtimes/wake/__init__.py
 M backend/app/runtimes/wake/base.py
 M backend/app/runtimes/wake/openwakeword_runtime.py
 M backend/app/runtimes/wake/wake_runtime.py
 M backend/app/services/audio_stream.py
 M backend/app/services/llm_execution_coordinator.py
 M backend/app/services/local_llm_sidecar.py
 M backend/app/services/local_llm_startup.py
 M backend/app/services/memory_curation_processor.py
 M backend/app/services/memory_curation_service.py
 M backend/app/services/memory_service.py
 M backend/app/services/resident_voice_invocation.py
 M backend/app/services/session_service.py
 M backend/app/services/startup_context.py
 M backend/app/services/turn_service.py
 M backend/app/services/utterance_segmenter.py
 M backend/app/services/voice_service.py
 M backend/app/services/wake_monitor.py
 M backend/app/services/wake_status.py
 M backend/tests/__init__.py
 M backend/tests/conftest.py
 M backend/tests/fixtures/__init__.py
 M backend/tests/integration/__init__.py
 M backend/tests/integration/api/test_headless_client.py
 M backend/tests/integration/services/test_two_turn_session.py
 M backend/tests/integration/test_memory_curation_review_pipeline.py
 M backend/tests/runtime/__init__.py
 M backend/tests/runtime/acceleration_matrix/__init__.py
 M backend/tests/runtime/acceleration_matrix/test_acceleration_matrix.py
 M backend/tests/runtime/desktop/test_resident_loop_live.py
 M backend/tests/runtime/desktop/test_resident_voice_desktop_live.py
 M backend/tests/runtime/desktop/test_wake_integration_live.py
 M backend/tests/runtime/hardware/__init__.py
 M backend/tests/runtime/hardware/test_directml_gate_live.py
 M backend/tests/runtime/hardware/test_llm_serve_profile_resolution.py
 M backend/tests/runtime/hardware/test_qnn_gate_live.py
 M backend/tests/runtime/services/__init__.py
 M backend/tests/runtime/services/test_redis_cache_live.py
 M backend/tests/runtime/services/test_redis_retrieval_cache_live.py
 M backend/tests/runtime/services/test_search_public_providers_live.py
 M backend/tests/runtime/services/test_searxng_live.py
 M backend/tests/runtime/turn/test_barge_in_live.py
 M backend/tests/runtime/turn/test_continuity_retrieval_live.py
 M backend/tests/runtime/turn/test_turn_control_live.py
 M backend/tests/runtime/voice/test_llm_llama_cpp_live.py
 M backend/tests/runtime/voice/test_llm_ollama_live.py
 M backend/tests/runtime/voice/test_resident_audio_activation_live.py
 M backend/tests/runtime/voice/test_resident_audio_live.py
 M backend/tests/runtime/voice/test_wake_live.py
 M backend/tests/unit/__init__.py
 M backend/tests/unit/api/test_app_lifecycle.py
 M backend/tests/unit/api/test_memory_curation_routes.py
 M backend/tests/unit/api/test_memory_routes.py
 M backend/tests/unit/api/test_routes.py
 M backend/tests/unit/api/test_service_status.py
 M backend/tests/unit/artifacts/test_turn_artifact.py
 M backend/tests/unit/cache/test_cache_manager.py
 M backend/tests/unit/cognition/test_memory_extraction.py
 M backend/tests/unit/cognition/test_prompt_assembler.py
 M backend/tests/unit/cognition/test_responder.py
 M backend/tests/unit/cognition/test_style_guard.py
 M backend/tests/unit/conversation/realtime/test_events.py
 M backend/tests/unit/conversation/realtime/test_response_and_interruption.py
 M backend/tests/unit/conversation/realtime/test_session.py
 M backend/tests/unit/conversation/test_continuity_policy.py
 M backend/tests/unit/conversation/test_engine.py
 M backend/tests/unit/conversation/test_session_manager.py
 M backend/tests/unit/conversation/test_states.py
 M backend/tests/unit/core/test_settings.py
 M backend/tests/unit/desktop/test_desktop_static_contract.py
 M backend/tests/unit/hardware/__init__.py
 M backend/tests/unit/hardware/test_preflight.py
 M backend/tests/unit/hardware/test_profiler.py
 M backend/tests/unit/hardware/test_provisioning.py
 M backend/tests/unit/hardware/test_qnn_prerequisite.py
 M backend/tests/unit/hardware/test_qnn_provider.py
 M backend/tests/unit/hardware/test_qnn_slot.py
 M backend/tests/unit/hardware/test_readiness.py
 M backend/tests/unit/memory/test_curation_contract.py
 M backend/tests/unit/memory/test_curation_reconciliation.py
 M backend/tests/unit/memory/test_episodic.py
 M backend/tests/unit/memory/test_retrieval.py
 M backend/tests/unit/memory/test_semantic.py
 M backend/tests/unit/memory/test_semantic_lifecycle.py
 M backend/tests/unit/memory/test_working_memory.py
 M backend/tests/unit/models/test_llm_selection.py
 M backend/tests/unit/personality/test_personality.py
 M backend/tests/unit/personality/test_personality_authority_guards.py
 M backend/tests/unit/routing/test_runtime_selector.py
 M backend/tests/unit/runtimes/internetsearch/test_search_runtime.py
 M backend/tests/unit/runtimes/llm/test_llm_runtime.py
 M backend/tests/unit/runtimes/llm/test_llm_serve_profiles.py
 M backend/tests/unit/runtimes/stt/test_stt_runtime.py
 M backend/tests/unit/runtimes/tts/test_tts_runtime.py
 M backend/tests/unit/runtimes/vad/test_vad_runtime.py
 M backend/tests/unit/runtimes/wake/test_wake_runtime.py
 M backend/tests/unit/scripts/__init__.py
 M backend/tests/unit/scripts/test_bootstrap_script.py
 M backend/tests/unit/scripts/test_ensure_models_llm_runtime_artifacts.py
 M backend/tests/unit/scripts/test_ensure_models_script.py
 M backend/tests/unit/scripts/test_provision_script.py
 M backend/tests/unit/scripts/test_run_backend_script.py
 M backend/tests/unit/scripts/test_run_jarvis_script.py
 M backend/tests/unit/scripts/test_validate_backend_script.py
 M backend/tests/unit/services/test_audio_stream.py
 M backend/tests/unit/services/test_llm_execution_coordinator.py
 M backend/tests/unit/services/test_local_llm_sidecar.py
 M backend/tests/unit/services/test_local_llm_startup.py
 M backend/tests/unit/services/test_memory_curation_processor.py
 M backend/tests/unit/services/test_memory_curation_service.py
 M backend/tests/unit/services/test_memory_service.py
 M backend/tests/unit/services/test_resident_voice_invocation.py
 M backend/tests/unit/services/test_resident_voice_modes.py
 M backend/tests/unit/services/test_session_service.py
 M backend/tests/unit/services/test_startup_context.py
 M backend/tests/unit/services/test_turn_service.py
 M backend/tests/unit/services/test_utterance_segmenter.py
 M backend/tests/unit/services/test_voice_service.py
 M backend/tests/unit/services/test_wake_monitor.py
 M backend/tests/unit/services/test_wake_status.py
 M config/hardware/notes.md
 M config/models/llm.yaml
 M config/models/stt.yaml
 M config/models/tts.yaml
 M config/models/wake.yaml
 M config/personality/README.md
 M config/personality/concise.yaml
 M config/personality/default.yaml
 M config/personality/jarvis.yaml
 M config/personality/sage.yaml
 M config/personality/warm.yaml
 M config/search/searxng/settings.yml
 M config/search/searxng/settings.yml.new
 M desktop/AGENTS.md
 M desktop/README.md
 M desktop/package-lock.json
 M desktop/package.json
 M desktop/src-tauri/Cargo.lock
 M desktop/src-tauri/build.rs
 M desktop/src-tauri/src/backend.rs
 M desktop/src-tauri/src/lib.rs
 M desktop/src-tauri/src/main.rs
 M desktop/src-tauri/tauri.conf.json
 M desktop/src/api-client.js
 M desktop/src/components/appearance-controls.js
 M desktop/src/components/backend-diagnostics.js
 M desktop/src/components/conversation-debug.js
 M desktop/src/components/degraded-list.js
 M desktop/src/components/desktop-polling.js
 M desktop/src/components/desktop-state.js
 M desktop/src/components/memory-panel.js
 M desktop/src/components/readiness-panel.js
 M desktop/src/components/resident-voice.js
 M desktop/src/components/service-status.js
 M desktop/src/components/settings-panel.js
 M desktop/src/components/state-label.js
 M desktop/src/components/wake-indicator.js
 M desktop/src/index.html
 M desktop/src/main.js
 M desktop/src/style.css
 M desktop/tests/static.test.mjs
 M docker-compose.yml
 M docs/QuickStart-linux.md
 M docs/QuickStart-windows.md
 M docs/YYYYMMDD_slice-template.md
 M docs/archives/AGENTS.md.bak
 M docs/archives/README_ORG.md
 M docs/archives/READMEv1.md
 M docs/archives/READMEv2.md
 M docs/archives/READMEv3.md
 M docs/archives/slices-done/2026-q2/20260423-slice_a.md
 M docs/archives/slices-done/2026-q2/20260425-slice_b.md
 M docs/archives/slices-done/2026-q2/20260426-slice_c.md
 M docs/archives/slices-done/2026-q2/20260428-slice_d.md
 M docs/archives/slices-done/2026-q2/20260430-slice_e.md
 M docs/archives/slices-done/2026-q2/20260503-slice_f.md
 M docs/archives/slices-done/2026-q2/20260504-slice_g.md
 M docs/archives/slices-done/2026-q2/20260505-slice_h.md
 M docs/archives/slices-done/2026-q2/20260513_slice-i.md
 M docs/archives/slices-done/2026-q2/20260515_slice-j.md
 M docs/archives/slices-done/2026-q2/20260526_slice-k.md
 M docs/archives/slices-done/2026-q2/20260612_slice-l.md
 M docs/archives/slices-done/2026-q2/20260613_slice-m.md
 M docs/archives/slices-done/2026-q2/20260614_slice-n.md
 M docs/archives/slices-done/2026-q2/20260615_slice-o.md
 M docs/archives/slices-done/2026-q2/20260615_slice-p.md
 M docs/archives/slices-done/2026-q2/20260615_slice-q.md
 M docs/archives/slices-done/2026-q2/20260616_census-r.md
 M docs/archives/slices-done/2026-q2/20260616_slice-r.md
 M docs/archives/slices-done/2026-q2/20260618_slice-s.md
 M docs/archives/slices-done/2026-q2/20260625_slice-t.md
 M docs/archives/slices-done/2026-q2/20260625_slice-t2.md
 M docs/archives/slices-done/2026-q2/20260626_slice-u.md
 M docs/archives/slices-done/2026-q2/20260627_slice-u2.md
 M docs/archives/slices-done/2026-q2/20260627_slice-u3.md
 M docs/archives/slices-done/2026-q2/20260627_slice-u4_.md
 M docs/archives/slices-done/2026-q2/20260630_slice-v.md
 M docs/archives/slices-done/2026-q2/20260630_slice-w.md
 M docs/archives/slices-done/2026-q2/20260630_slice-w2.md
 M docs/archives/slices-done/2026-q2/20260630_slice-x.md
 M docs/archives/slices-done/2026-q2/20260701_slice-y.md
 M docs/archives/slices-done/2026-q2/20260702_slice-z.md
 M docs/archives/slices-done/2026-q2/20260702_slice-z1.md
 M docs/archives/slices-done/2026-q2/20260702_slice-z2.md
 M docs/archives/slices-done/2026-q2/20260703_slice-z3.md
 M docs/archives/slices-done/2026-q2/20260703_slice-z4.md
 M docs/archives/slices-done/2026-q2/20260703_slice-z5.md
 M docs/archives/slices-done/2026-q2/20260704_slice-z5b.md
 M docs/archives/slices-done/2026-q2/20260704_slice-z6.md
 M docs/archives/slices-done/2026-q2/20260705_CHANGE_LOG.md
 M docs/archives/slices-done/2026-q2/20260705_SYSTEM_INVENTORY.md
 M docs/archives/slices-done/20260706_slice-aa.md
 M docs/archives/slices-done/20260708_kokoro-tts-qnn.md
 M docs/archives/slices-done/20260708_slice-bb.md
 M docs/archives/slices-done/20260710_slice-cc.md
 M docs/archives/slices-done/20260720-CHANGE_LOG.md
 M docs/archives/slices-done/20260720-SYSTEM_INVENTORY.md
 M docs/archives/slices.md
 M docs/helpers/jarvis-arm-llamacpp-qnn.md
 M docs/helpers/jarvis-arm-llamacpp-qnn.ps1
 M docs/helpers/jarvis-arm-llamacpp.md
 M docs/helpers/jarvis-arm-llamacpp.ps1
 M docs/helpers/jarvis-arm-whisper.md
 M docs/helpers/jarvis-arm-whisper.ps1
 M docs/helpers/jarvis-arm.vsconfig
 M docs/helpers/jarvis-wsl-llamacpp.md
 M docs/helpers/jarvis-wsl-llamacpp.sh
 M docs/ideas/new-internetsearch.md
 M docs/ideas/new-tavilyopen.md
 M models/AGENTS.md
 M pyproject.toml
 M repo_tree.md
 M runtimes/AGENTS.md
 M scripts/AGENTS.md
 M scripts/bootstrap.py
 M scripts/ensure_models.py
 M scripts/provision.py
 M scripts/run_backend.py
 M scripts/run_jarvis.py
 M scripts/validate_backend.py
?? reports/20260725_census-memory.md
```


