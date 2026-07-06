# CHANGE_LOG.md
> No edits/reorders/deletes of past entries.
> If an entry is wrong, append a corrective entry in `## Appendix`.

## Rules
- Write an entry for codebase change only after objective is complete and supported by evidence.
- Ordering: Entries are maintained in descending chronological order (newest first, oldest last).
- Append location: New entries must be added at the top directly under `## Change Entries`.
- Corrections or clarifications go only below the `## Change Appendix` section.
- Each entry must include:

- Timestamp: `YYYY-MM-DD HH:MM`
  - Host class(es): validated on (e.g., `Windows x64`, `Windows ARM64`, etc. as appropriate)
  - Summary: description of capability added, 1–2 lines, past tense
  - Scope: (list codebase added/changed/removed, 1-5 lines )
    - List exact folders, files, tests, areas
  - Validation: (list reproducable evidence as validation)
    - List of exact command(s) run + a minimal excerpt pointer (or embedded excerpt ≤10 lines)
  - Notes: (list notes as appropriate - optional)
    - List of notes

---

## Change Entries

- Timestamp: 2026-07-05 10:30
  - Host class(es): Windows x64 / amd64 validated
  - Summary: Updated `CHANGE_LOG.md`, `SYSTEM_INVENTORY.md` to organize repo governance
  - Scope: 
    - `CHANGE_LOG.md`
    - `SYSTEM_INVENTORY.md`
  - Validation: 
    - `cat .\CHANGE_LOG.md -head 1` = `# CHANGE_LOG.md`
    - `cat .\SYSTEM_INVENTORY.md -head 1` = `# SYSTEM_INVENTORY.md`
  - Notes: 

---

## Change Appendix

---

### Consolidated Change History

- Timestamp: 2026-05-02 18:03
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated, with missed live ACTING/tool runtime gate recovered on Windows x64
  - Summary: Completed Slice F deterministic tool execution and rendering surface. The codebase gained deterministic ACTING-state executor wiring, additive turn/artifact tool metadata, a tool registry and first deterministic tool set, fail-closed tool invocation behavior, task/voice API tool-call summaries, text-shell and desktop tool-result rendering, and live ACTING/tool-path evidence for the registered `time` tool.
  - Scope:
    - ACTING executor and turn/artifact metadata: `backend/app/cognition/executor.py`, `backend/app/conversation/engine.py`, `backend/tests/unit/cognition/test_tool_executor.py`, `backend/tests/unit/conversation/test_engine.py`.
    - Tool registry and first tool set: `backend/app/tools/`, `backend/app/core/settings.py`, `.env.example`, `backend/tests/unit/tools/`, `backend/tests/unit/conversation/test_engine.py`.
    - Tool result API/shell rendering: `backend/app/api/schemas/`, `backend/app/api/routes/task.py`, `backend/app/api/routes/voice.py`, `scripts/run_jarvis.py`, `desktop/src/main.js`, `backend/tests/unit/api/test_routes.py`, `backend/tests/unit/desktop/test_desktop_static_contract.py`, `backend/tests/unit/scripts/test_run_jarvis_script.py`.
    - Runtime ACTING proof: `backend/tests/runtime/turn/test_acting_live.py`.
  - Validation:
    - F.1 executor and ACTING state on Windows x64 and Windows ARM64: compileall PASS for executor/engine; focused tool-executor unit PASS (`4 passed`) on both hosts; focused conversation engine unit PASS (`29 passed`) on both hosts; validator unit PASS (`277 passed`) on both hosts; regression PASS (`95 passed`) on both hosts.
    - F.2 tool registry and first tool set on Windows x64 and Windows ARM64: compileall PASS for `backend/app/tools` and settings; unit suite PASS (`289 passed`) on both hosts; ARM64 focused tool unit PASS (`12 passed`); validator unit PASS (`289 passed`) on both hosts; regression PASS (`95 passed`) on both hosts.
    - F.3 tool result rendering on Windows x64 and Windows ARM64: compileall PASS for backend app/tests; unit suite PASS (`292 passed`) on both hosts; validator unit PASS (`292 passed`) on both hosts; regression PASS (`96 passed`) on both hosts.
    - Missed Slice F live gate recovery on Windows x64: compileall PASS for `backend/tests/runtime/turn/test_acting_live.py`; live runtime test PASS (`1 passed in 24.52s`); `scripts\validate_backend.py runtime --families turn` PASS (`5 passed, 14 deselected in 42.00s`); regression PASS (`96 passed`). Live assertions proved `result.tool_calls[0]["tool_name"] == "time"`, `result.tool_results[0]["tool_name"] == "time"`, successful tool result, `"time"` in persisted `artifact.tools_invoked`, and `artifact.agent_trace` containing `tool_calls` and `tool_results`.
  - Notes:
    - Slice F uses explicit deterministic `tool_name` dispatch and does not add LLM-driven tool selection, model-side function calling, autonomous agents, or Group I agent behavior.
    - First tool set includes time/date, hardware-info, read-only sandboxed `filesystem.read`, and an internet-search adapter over the existing Slice E search runtime selection contract.
    - `filesystem.read` is confined by `TOOL_FILESYSTEM_SANDBOX_PATH` with default `data/tool_sandbox/`; it rejects traversal/out-of-sandbox access, sibling internal data directories, missing files, binary/invalid UTF-8 reads, and write behavior.
    - API and shell rendering is presentation-only: task/voice routes map existing `TurnResult.tool_calls` into optional response summaries, and shells render concise optional tool metadata without invoking tools directly.
    - Search tool output remains provider-agnostic and fail-closed through the Slice E selector tuple contract. Slice F did not add new Slice E providers/runtimes, memory retrieval behavior, new packages, new services, filesystem indexing/search, or inventory behavior.
    - The recovered live ACTING/tool-path gate was validated on Windows x64 only and is not a full additional ARM64 live-runtime closeout.

- Timestamp: 2026-05-01 01:05
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Completed Slice E infrastructure and internet-search substrate. The codebase gained Docker-backed Redis and SearXNG service substrate, Redis/search settings, a fail-closed Redis cache layer wired into FastAPI application state, a fail-closed internet search runtime family, provider selection for SearXNG, DDGS, Tavily, and Null search, and live service/provider validation evidence across Windows x64 and Windows ARM64.
  - Scope:
    - Service substrate and configuration: `docker-compose.yml`, `.env.example`, `config/search/searxng/settings.yml`, `config/search/searxng/cache/.gitkeep`, `config/search/ddgs/.gitkeep`, `config/search/tavily/.gitkeep`.
    - Settings and dependencies: `backend/app/core/settings.py`, `pyproject.toml`, `backend/tests/unit/core/test_settings.py`; Redis settings cover `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_MAX_CONNECTIONS`, and `REDIS_SOCKET_TIMEOUT`; search settings cover `USE_SEARXNG`, `SEARXNG_BASE_URL`, `USE_DDGS`, `USE_TAVILY`, and `TAVILY_API_KEY`; dependency state uses `redis>=5.0` and `ddgs>=9.10`.
    - Cache wiring: `backend/app/cache/`, `backend/app/api/app.py`, `backend/app/api/dependencies.py`, `backend/tests/unit/cache/test_cache_manager.py`, `backend/tests/runtime/services/test_redis_cache_live.py`.
    - Internet search runtime and routing: `backend/app/runtimes/internetsearch/`, `backend/app/routing/runtime_selector.py`, `backend/tests/unit/runtimes/internetsearch/test_search_runtime.py`, `backend/tests/runtime/services/test_searxng_live.py`, `backend/tests/runtime/services/test_search_public_providers_live.py`.
  - Validation:
    - E.1 Docker service substrate on Windows x64 and Windows ARM64: `docker compose config` PASS; `docker compose up -d` PASS; `docker compose ps` healthy; Redis `redis-cli ping` returned `PONG`; SearXNG JSON search endpoint returned valid JSON; backend regression PASS (`95 passed`) on both hosts.
    - E.2 Redis configuration on Windows x64 and Windows ARM64: focused core settings tests PASS (`8 passed` on both hosts); Redis import/version PASS (`7.4.0`); backend regression PASS (`95 passed`) on both hosts.
    - E.3 cache wiring on Windows x64 and Windows ARM64: cache unit PASS (`7 passed` on both hosts); API unit PASS (`21 passed` on both hosts); validator unit PASS (`260 passed` on both hosts); regression PASS (`95 passed`) on both hosts; Redis `PONG`; runtime cache live PASS (`3 passed`) on both hosts.
    - E.4 search configuration on Windows x64 and Windows ARM64: core settings tests PASS (`11 passed` on both hosts); dependency provisioning PASS; search dependency import/version PASS; regression PASS (`95 passed`) on both hosts. Final dependency alignment uses `ddgs>=9.10` with `from ddgs import DDGS`.
    - E.5 search wiring on Windows x64 and Windows ARM64: scoped URL grep checks had no hardcoded SearXNG localhost hits; internetsearch unit PASS (`6 passed`) on both hosts; validator unit PASS (`269 passed`) on both hosts; regression PASS (`95 passed`) on both hosts; live search tests PASS (`3 passed`, including x64 `3 passed in 2.70s`) with SearXNG, DDGS, and Tavily provider proof.
    - Slice E grouped closeout recorded E.1-E.5 as verified across Windows x64 and Windows ARM64 with 95 passing regression on both hosts, live Redis roundtrip, live SearXNG search, and live DDGS/Tavily provider proof.
  - Notes:
    - Slice E established infrastructure/cache/search substrate only. It did not introduce prompt, turn, conversation, tool-call, agent, autonomous-agent, or memory-retrieval behavior.
    - Cache and search behavior is fail-closed: Redis unavailability does not make default unit/regression validation require Redis or Docker, and search provider unavailable/error paths return empty results through the Null/fallback path.
    - Search provider priority is SearXNG, then DDGS, then Tavily, then Null; SearXNG URL ownership flows through settings instead of scoped test hardcoding.
    - Tavily key material was not printed or logged in validation evidence.

- Timestamp: 2026-04-30 11:12
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated, with D.3/D.4 user-run runtime desktop closeout evidence on Windows x64
  - Summary: Completed Slice D durable application surface. The codebase gained a backend FastAPI shell contract, backend-only launcher, desktop/Tauri host, desktop prerequisite checker, resident session continuity surface, wake status integration, selectable personality/presence controls, and runtime desktop evidence for resident session continuity and deterministic wake integration.
  - Scope:
    - Backend shell/API contract: `backend/app/api/`, `scripts/run_backend.py`, `backend/tests/unit/api/`, `backend/tests/integration/api/`, `backend/tests/unit/scripts/test_run_backend_script.py`.
    - Desktop prerequisite/method viability: `scripts/dev_runner.py`, `backend/tests/unit/scripts/test_dev_runner.py`.
    - Durable desktop host: `desktop/`, `desktop/src-tauri/src/`, `desktop/src/`, `desktop/package-lock.json`, `backend/tests/unit/desktop/`.
    - Resident session continuity: `backend/app/services/session_service.py`, `backend/app/api/routes/session.py`, `backend/app/api/schemas/session.py`, `backend/app/api/dependencies.py`, `backend/app/api/routes/task.py`, `desktop/src-tauri/src/{backend.rs,lib.rs}`, `desktop/src/main.js`, `desktop/src/index.html`, `backend/tests/unit/services/test_session_service.py`, `backend/tests/unit/api/test_routes.py`, `backend/tests/integration/api/test_headless_client.py`, `backend/tests/unit/desktop/test_desktop_static_contract.py`, `backend/tests/runtime/desktop/test_resident_loop_live.py`.
    - Wake integration/status surfacing: `desktop/src-tauri/src/{backend.rs,lib.rs}`, `desktop/src/main.js`, `backend/app/services/session_service.py`, `backend/app/api/routes/status.py`, `backend/app/api/schemas/status.py`, `backend/tests/unit/services/test_session_service.py`, `backend/tests/unit/api/test_routes.py`, `backend/tests/runtime/desktop/test_wake_integration_live.py`.
    - Personality/presence polish: `backend/app/personality/{loader.py,adapter.py,schema.py}`, `backend/app/conversation/engine.py`, `backend/app/api/routes/personality.py`, `backend/app/api/schemas/personality.py`, `backend/app/services/session_service.py`, `desktop/src-tauri/src/{backend.rs,lib.rs}`, `desktop/src/{main.js,index.html}`, and related personality, conversation, session-service, API, and desktop static tests.
  - Validation:
    - D.1 backend shell/API contract on Windows x64 and Windows ARM64: compileall PASS; API unit PASS (`12 passed`); run-backend script unit PASS (`3 passed`); API integration PASS (`4 passed`); run-backend dry-run PASS with fingerprint first; unit validator PASS (`197 passed`); integration validator PASS (`7 passed`); regression PASS (`77 passed`) on both hosts.
    - D.2 prerequisite checker on Windows x64 and Windows ARM64: compileall PASS; focused dev-runner unit PASS (`18 passed`) on both hosts; `scripts/dev_runner.py check --arch x64` PASS with `SUMMARY arch=x64 failures=0 warnings=1`; `scripts/dev_runner.py check --arch arm64` PASS with `SUMMARY arch=arm64 failures=0 warnings=1`; regression PASS (`95 passed`) on both hosts.
    - D.2 desktop host on Windows x64: dev runner PASS; desktop static tests PASS (`8 passed`); npm static voice checks PASS; `cargo check --manifest-path desktop\src-tauri\Cargo.toml` PASS; `backend\.venv\Scripts\python scripts\run_backend.py --dry-run` PASS; backend regression PASS (`95 passed`); user Tauri smoke confirmed app launch, backend health/session/readiness load, visible text turn, tray menu operation, and `/task/voice` visible result.
    - D.2 desktop host on Windows ARM64: `backend\.venv\Scripts\python scripts\dev_runner.py check --arch arm64` PASS; desktop unit/static checks PASS; `npm --prefix desktop install` PASS using committed lockfile; `npm --prefix desktop test` PASS; `cargo check --manifest-path desktop\src-tauri\Cargo.toml` PASS; backend dry-run/regression PASS; `npm --prefix desktop run dev` launch PASS; user smoke confirmed window, backend health/session/readiness, visible text turn, tray menu, and HTT voice path result.
    - D.3 resident session continuity on Windows x64 and Windows ARM64: service unit PASS (`6 passed`) on both hosts; API unit PASS (`15 passed`) on both hosts; API integration PASS (`5 passed`) on both hosts; desktop static PASS (`9 passed`) on both hosts; validator unit PASS (`233 passed`) on both hosts; validator integration PASS (`8 passed`) on both hosts; regression PASS (`95 passed`/`95 tests`) on both hosts. Integration proof drove three text turns with one `session_id`; `/session/status` returned `active=true` with `turn_count=3`.
    - D.4 wake integration/status on Windows x64 and Windows ARM64: service unit PASS (`11 passed`) on both hosts; API unit PASS (`17 passed`) on both hosts; validator unit PASS (`241 passed`) on both hosts; regression PASS (`95 passed`/`95 tests`) on both hosts. `/status/wake` preserves `provider`, `available`, and `reason`, and includes `monitoring`, `last_detected`, `detection_count`, and `last_error`; deterministic injected-chunk detection updates `last_detected=true` and increments `detection_count`; unavailable/error states return explicit PTT-only fallback status.
    - D.5 personality/presence on Windows x64 and Windows ARM64: personality unit PASS (`7 passed`) on both hosts; conversation unit PASS (`25 passed`) on both hosts; session-service unit PASS (`12 passed`) on both hosts; API unit PASS (`20 passed`) on both hosts; desktop static PASS (`11 passed`) on both hosts; validator unit PASS (`250 passed`) on both hosts; validator integration PASS (`8 passed`) on both hosts; regression PASS (`95 passed`) on both hosts.
    - Slice D runtime desktop closeout on Windows x64: user-run `backend\.venv\Scripts\python -m pytest backend\tests\runtime\desktop\test_resident_loop_live.py -q -s` PASS; three `/task/text` turns completed in one active session with the same `session_id`; `/session/status` returned `active=True`, `state='IDLE'`, `turn_count=3`; `/session/close` returned `closed=True` and wrote the session artifact. User-run `backend\.venv\Scripts\python -m pytest backend\tests\runtime\desktop\test_wake_integration_live.py -q -s` PASS; wake provider configured `openwakeword available=true`; nondetect path reported cleanly; unavailable runtime reported explicit `PTT-only fallback`; deterministic detection set `last_detected=True` and `detection_count=1`; deterministic error reported fallback with `last_error`.
  - Notes:
    - Slice D established the durable application surface over the Slice C turn engine. Route handlers remain thin service/engine/app-state adapters, and `/session/tick` remains excluded.
    - The desktop shell is a durable npm/Tauri host with backend lifecycle through `scripts/run_backend.py`, readiness/runtime display, visible text turns, tray lifecycle menu, robot `.ico`, and a development-cycle Hold-to-Talk voice proof path.
    - HTT validated the D.2 voice path but is not the final intended PTT UX; idealized 16 kHz PCM/downsample quality is not claimed.
    - D.3/D.4 live closeout evidence was user-run runtime desktop evidence on Windows x64. No open-microphone live wake phrase test is claimed.
    - D.5 added selectable personality/profile presence behavior and UI-only presence acknowledgments without changing model/runtime selection, STT/TTS/LLM runtime behavior, wake runtime behavior, provisioning behavior, or changelog/inventory behavior.

- Timestamp: 2026-04-28 06:04
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Completed Slice C canonical turn/session engine and proving-host foundation. The codebase gained a shared text/voice `TurnEngine`, canonical conversation states and failure handling, personality/prompt/responder boundaries, spoken response and `SPEAKING` state behavior, deterministic session continuity with canonical turn/session artifacts, bounded working memory, live multi-turn spoken continuity coverage, deterministic interruption/barge-in behavior, and `scripts/run_jarvis.py` as the developer/proving-host diagnostic surface.
  - Scope:
    - Turn engine and shared text/voice cognition path: `backend/app/conversation/`, `backend/app/cognition/`, `backend/app/personality/`, `backend/app/services/`, `config/personality/default.yaml`, `backend/tests/unit/conversation/`, `backend/tests/unit/cognition/`, `backend/tests/unit/personality/`, `backend/tests/unit/services/`, `backend/tests/runtime/turn/`.
    - Spoken response and response sanitation: `backend/app/conversation/engine.py`, `backend/app/cognition/responder.py`, `backend/tests/unit/conversation/test_engine.py`, `backend/tests/runtime/turn/test_turn_control_live.py`.
    - Session continuity, artifacts, and working memory: `backend/app/artifacts/`, `backend/app/memory/`, `backend/app/conversation/`, `backend/tests/unit/artifacts/`, `backend/tests/unit/memory/`, `backend/tests/unit/conversation/`, `backend/tests/integration/services/test_two_turn_session.py`.
    - Live continuity and interruption coverage: `backend/tests/runtime/turn/test_continuity_retrieval_live.py`, `backend/app/runtimes/stt/barge_in.py`, `backend/app/runtimes/tts/playback.py`, `backend/app/artifacts/turn_artifact.py`, `backend/tests/unit/runtimes/stt/test_stt_runtime.py`, `backend/tests/runtime/turn/test_barge_in_live.py`.
    - Developer/proving host: `scripts/run_jarvis.py`, `backend/tests/unit/scripts/test_run_jarvis_script.py`.
    - Environment/settings support used by the C.1 runtime path: `backend/app/core/settings.py`, `.env.example`, `backend/tests/unit/core/test_settings.py`, `backend/app/runtimes/llm/ollama_runtime.py`, relevant runtime test gates in `backend/tests/conftest.py`, `backend/tests/runtime/voice/`, `backend/tests/runtime/turn/`, and `backend/tests/runtime/acceleration_matrix/`.
  - Validation:
    - C.1 minimal voice/text turn on Windows x64: `backend\.venv\Scripts\python -m compileall backend/app/conversation backend/app/cognition backend/app/personality backend/app/services` PASS; focused C.1 unit suite PASS (`27 passed`); after env standardization, `backend\.venv\Scripts\python scripts/validate_backend.py unit` PASS (`135 passed`), `backend\.venv\Scripts\python scripts/validate_backend.py runtime --families turn` PASS (`2 passed, 5 deselected`), and `backend\.venv\Scripts\python scripts/validate_backend.py regression` PASS (`63 passed`).
    - Env/settings support for the C.1 runtime path: `backend/app/core/settings.py` standardized shell env > `.env` > `.env.example` precedence; `.env.example` remained the committed safe fallback and included `QAIRT_SDK_PATH=`; related unit/runtime/regression validation PASS, including ARM64 `llm` runtime (`1 passed, 6 deselected`), ARM64 `turn` runtime (`2 passed, 5 deselected`), and ARM64 regression (`63 passed`, report `reports\validation\20260427023948-regression.txt`).
    - C.2 spoken response on Windows x64 and Windows ARM64: compileall PASS; `backend\.venv\Scripts\python -m pytest backend/tests/unit/conversation/test_engine.py -q` PASS; `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families turn,tts` PASS (`3 passed, 4 deselected`) on both hosts; regression PASS (`63 passed`) on both hosts. ARM64 bootstrap completed profile/provision/ensure_models/preflight/validate_profile checkpoints and verify-only PASS before runtime validation.
    - C.3 session/artifact/working-memory foundation on Windows x64 and Windows ARM64: compileall PASS; focused C.3 pytest PASS (`40 passed`) on both hosts; `scripts\validate_backend.py unit` PASS (`165 passed`) on both hosts; `scripts\validate_backend.py integration` PASS (`3 passed`) on both hosts; `scripts\validate_backend.py regression` PASS (`63 passed`) on both hosts.
    - C.4 live multi-turn spoken continuity on Windows x64 and Windows ARM64: compileall PASS; runtime validator PASS (`5 passed, 3 deselected`) on both hosts; regression PASS (`63 passed`) on both hosts. Coverage proved two spoken turns in one `SessionManager`, successful completion, tmp-path-scoped artifact writes, and second-turn working-memory injection through persisted `final_prompt_text`.
    - C.5 interruption/barge-in on Windows x64 and Windows ARM64: focused STT detector unit PASS (`10 passed`), focused engine unit PASS (`24 passed`), unit validator PASS (`171 passed`), runtime validator PASS (`5 passed, 4 deselected`), and regression PASS (`63 passed`) on both hosts.
    - C.6 proving host on Windows x64 and Windows ARM64: compileall PASS; focused run-jarvis script unit PASS (`11 passed`); dry-run PASS with fingerprint first; profile PASS with fingerprint first; unit validator PASS (`182 passed`); regression PASS (`74 passed`) on both hosts.
  - Notes:
    - Slice C established the backend turn/session/proving-host foundation, not the durable API/desktop application surface, resident loop, tool system, agents, or Group D+ product shell.
    - Voice and text turns share the same engine path. Text-turn behavior was preserved while voice turns gained TTS-attempted `SPEAKING` transitions and clean text degradation when TTS is unavailable.
    - Canonical artifacts are deterministic and optional at the engine boundary: default C.1/C.2 behavior remains artifact-free when no `SessionManager` is provided; session-managed turns write under `data/turns/` and `data/sessions/`.
    - C.4 continuity proof used `NullTTSRuntime` degraded behavior and did not claim real TTS playback/audio-output/device-state proof.
    - C.5 interruption proof was deterministic/runtime-gated but did not claim full acoustic microphone barge-in validation or physical audio-output validation.
    - `scripts/run_jarvis.py` is a developer/proving host only. It does not create a durable application surface, API, desktop shell, resident loop, new runtime family, routing-policy implementation, tool behavior, agent behavior, or inventory promotion.

- Timestamp: 2026-04-26 19:45
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Completed Slice B cross-platform voice runtime foundation. The codebase gained model catalog/acquisition support for STT, TTS, and Wake artifacts; CPU-validated STT, TTS, LLM, and Wake runtime families; a policy-gated LLM routing surface; runtime validation gates; known-audio STT fixture coverage; and an acceleration matrix gate that reports known PASS/SKIP/PENDING/N/A states from profiler, preflight, runtime, and environment evidence.
  - Scope:
    - Model catalog and acquisition: `scripts/ensure_models.py`, `backend/app/models/catalog.py`, `config/models/stt.yaml`, `config/models/tts.yaml`, `config/models/wake.yaml`, `config/models/llm.yaml`, `pyproject.toml`, and model artifact locations under `models/stt/`, `models/tts/`, and `models/wake/`.
    - STT runtime foundation and live fixture path: `backend/app/runtimes/stt/`, `backend/tests/unit/runtimes/stt/test_stt_runtime.py`, `backend/tests/runtime/acceleration_matrix/test_acceleration_matrix.py`, `backend/tests/fixtures/hello_world.wav`, and `scripts/validate_backend.py`.
    - TTS runtime foundation: `backend/app/runtimes/tts/`, `backend/tests/unit/runtimes/tts/test_tts_runtime.py`, `backend/tests/runtime/voice/test_tts_device_matrix_live.py`.
    - LLM runtime and routing foundation: `backend/app/runtimes/llm/`, `backend/app/routing/runtime_selector.py`, `config/app/policies.yaml`, `.env.example`, `backend/tests/unit/runtimes/llm/test_llm_runtime.py`, `backend/tests/unit/routing/test_runtime_selector.py`, `backend/tests/runtime/voice/test_llm_llama_cpp_live.py`, `backend/tests/runtime/voice/test_llm_ollama_live.py`.
    - Wake runtime foundation: `backend/app/runtimes/wake/`, `backend/tests/unit/runtimes/wake/test_wake_runtime.py`, `backend/tests/runtime/voice/test_wake_live.py`, `backend/tests/fixtures/hey_jarvis.wav`, `backend/tests/conftest.py`.
    - Acceleration/known-state gate: `backend/tests/runtime/acceleration_matrix/test_acceleration_matrix.py`.
  - Validation:
    - B.0 model acquisition on Windows x64: `backend\.venv\Scripts\python scripts\provision.py install` PASS; `backend\.venv\Scripts\python -m compileall scripts\ensure_models.py backend\app\models` PASS; `backend\.venv\Scripts\python scripts\ensure_models.py --family llm` PASS with `ollama_manages_models`; `scripts\ensure_models.py --family wake`, `--family tts`, and `--family stt` PASS; final `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS with B.0 files present; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`61 passed`).
    - B.0 model acquisition on Windows ARM64: provisioning, compileall, LLM no-op acquisition, Wake/TTS/STT acquisition, final verify-only, and regression all PASS; excerpt included `arch=arm64`, `ollama_manages_models`, acquired Wake/TTS/STT files, `ready=true`, `missing=[]`, and `61 passed`.
    - STT model completeness on Windows x64: `backend\.venv\Scripts\python scripts\ensure_models.py --family stt` PASS; `scripts\ensure_models.py --verify-only` PASS with STT `ready=true` and `missing=[]`; `backend\.venv\Scripts\python -c "from pathlib import Path; import onnx_asr; m=onnx_asr.load_model('onnx-community/whisper-small', path=Path('models/stt/whisper-small-onnx'), providers=['CPUExecutionProvider']); print(type(m).__name__)"` PASS with `TextResultsAsrAdapter`; regression PASS (`61 passed`).
    - STT runtime CPU validation on Windows x64 and Windows ARM64: `backend\.venv\Scripts\python -m compileall backend\app\runtimes\stt backend\app\models scripts\validate_backend.py` PASS where applicable; STT unit PASS (`10 passed` on x64); `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt --devices cpu` PASS (`1 passed`); regression PASS (`63 tests`/`63 passed`). Known-audio fixture validation accepted normalized `hello world`; ARM64 fixture loading used stdlib `wave` plus `numpy`.
    - Validator CPU device gate: `backend\.venv\Scripts\python -m pytest backend\tests\unit\scripts\test_validate_backend_script.py -q` PASS (`9 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt --devices cpu` PASS without requiring a nonexistent `cpu` marker.
    - TTS runtime CPU no-playback validation on Windows x64 and Windows ARM64: `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS with TTS `ready=true` and `missing=[]`; compileall PASS; TTS unit PASS (`8 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families tts --devices cpu` PASS (`1 passed, 1 deselected`); regression PASS (`63 tests`/`63 passed`).
    - LLM runtime/routing validation on Windows x64 and Windows ARM64: `backend\.venv\Scripts\python -m compileall backend\app\runtimes\llm backend\app\routing` PASS; LLM/routing unit PASS (`13 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families llm` PASS (`1 passed, 2 deselected`); regression PASS (`63 tests`/`63 passed`).
    - Wake runtime validation on Windows x64 and Windows ARM64: `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS with wake `missing=[]` and ARM64 `ready=true`; compileall PASS; wake unit PASS (`8 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families wake` PASS (`1 passed, 3 deselected`); regression PASS (`63 tests`/`63 passed`).
    - B.5 acceleration matrix on Windows x64 and Windows ARM64: `backend\.venv\Scripts\python -m compileall backend\tests\runtime\acceleration_matrix` PASS; `backend\.venv\Scripts\python scripts\validate_backend.py matrix` PASS (`1 passed`) on both hosts; regression PASS (`63 passed`) on both hosts; matrix excerpts included `host,class,PASS,arch=amd64`, `host,class,PASS,arch=arm64`, no `BLOCKED-*` cells, STT/TTS/Wake CPU PASS, STT QNN `PENDING-H.2`, TTS QNN and Wake acceleration N/A, CUDA/DirectML SKIP when provider evidence was not proven, and LLM Ollama/local SKIP when the environment gate was unset.
  - Notes:
    - Slice B established runtime-family surfaces and validation gates, not the full conversation/session loop or durable product shell.
    - STT, TTS, and Wake CPU paths were validated on both Windows x64 and Windows ARM64; TTS validation was no-playback synthesis only and did not prove physical audio playback.
    - LLM validation used local Ollama (`phi4-mini`) as the live local path; cloud runtimes remained policy-gated stubs, and llama.cpp was not wired as a verified runtime in Slice B.
    - QNN STT remained pending at Slice B (`PENDING-H.2`); Porcupine wake remained structural-only and was not live-validated.
    - The B.5 matrix classified known states from evidence and failed on `BLOCKED-*` cells, but did not duplicate live runtime probes, download models, play audio, or start/stop services.

- Timestamp: 2026-04-24 17:16
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Completed Slice A hardware, provisioning, readiness, validation, and QNN structural foundation. The codebase gained a callable hardware profiler, declarative provisioning resolver, preflight/readiness evidence rail, arch-aware validation/bootstrap/model script entry points, cross-host provisioning proof, and metadata-only QNN capability definition.
  - Scope:
    - Hardware profiling and capability schema: `backend/app/core/capabilities.py`, `backend/app/hardware/profiler.py`, `backend/app/hardware/detectors/`, `backend/tests/unit/hardware/test_profiler.py`.
    - Core/provisioning foundation: `backend/app/core/paths.py`, `backend/app/core/logging.py`, `backend/app/core/settings.py`, `backend/app/hardware/provisioning.py`, `scripts/provision.py`, `backend/tests/unit/hardware/test_provisioning.py`, `backend/tests/unit/scripts/test_provision_script.py`.
    - Preflight/readiness foundation: `backend/app/hardware/preflight.py`, `backend/app/hardware/readiness.py`, `backend/tests/unit/hardware/test_preflight.py`, `backend/tests/unit/hardware/test_readiness.py`, `backend/tests/unit/hardware/test_qnn_slot.py`.
    - Validation/bootstrap/model entry points and arch-aware harness: `scripts/validate_backend.py`, `scripts/bootstrap.py`, `scripts/ensure_models.py`, `backend/tests/conftest.py`, `backend/tests/integration/__init__.py`, `backend/tests/runtime/__init__.py`, `backend/tests/runtime/hardware/__init__.py`, `backend/tests/runtime/acceleration_matrix/__init__.py`, `backend/tests/fixtures/__init__.py`, `backend/tests/unit/scripts/test_validate_backend_script.py`, `backend/tests/unit/scripts/test_bootstrap_script.py`.
    - Validation evidence artifacts: `reports/diagnostics/20260424154255-profile.txt`, `reports/validation/20260424150028-regression.txt`, `reports/validation/20260424085330-validation-regression-arm64.txt`, `reports/validation/20260424154318-regression.txt`, `reports/validation/20260424171638-regression.txt`.
  - Validation:
    - `backend/.venv/Scripts/python -m compileall backend/app/core backend/app/hardware backend/tests` PASS; dependency-free `run_profiler()` smoke PASS (`PASS A.1 smoke`).
    - `backend/.venv/Scripts/python -m compileall backend/app/core backend/app/hardware scripts/provision.py backend/tests/unit` PASS; provisioning resolver/script smoke PASS for `dry-run`, `install --dry-run`, and `lock`.
    - `backend/.venv/Scripts/python -m compileall backend/app/hardware backend/tests/unit/hardware` PASS; preflight/readiness smoke emitted a CUDA readiness tuple when CUDA evidence was present.
    - `backend/.venv/Scripts/python -m compileall scripts backend/tests` PASS; `scripts/validate_backend.py --help` PASS; `scripts/bootstrap.py --help` PASS; `scripts/ensure_models.py` reached checkpoint output.
    - Manual clean-venv provisioning/profile/regression PASS on Windows x64 and Windows ARM64; x64 regression artifact `reports/validation/20260424150028-regression.txt`; ARM64 regression artifact `reports/validation/20260424085330-validation-regression-arm64.txt`; user-side x64 regression showed `53/53 PASS`.
    - ARM64 repo-local profile/regression evidence recorded in `reports/diagnostics/20260424154255-profile.txt` and `reports/validation/20260424154318-regression.txt`.
    - QNN structural definition validation on ARM64: `backend\.venv\Scripts\python -m compileall backend\app\hardware\preflight.py backend\app\hardware\readiness.py backend\tests\unit\hardware\test_qnn_slot.py` PASS; `backend\.venv\Scripts\python -m pytest backend\tests\unit\hardware\test_qnn_slot.py -q` PASS (`8 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py profile` PASS with `arch=arm64`, QNN extra selected, readiness `ready`, and `tokens=15`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`61 passed`) with report `reports\validation\20260424171638-regression.txt`.
  - Notes:
    - Slice A established the hardware/provisioning/readiness authority only. It did not introduce Group B runtime/model/voice execution.
    - QNN support at Slice A was structural metadata/readiness definition only: `import:onnxruntime-qnn` was observed, while `ep:QNNExecutionProvider:MISSING` and `dll:QnnHtp:MISSING` remained expected/not-proven states.
    - Early A.1-A.4 validation occurred before `pytest` was installed in `backend/.venv`; later A.5/A.6 validation supplied clean-host and ARM64 repo-local evidence.

- Timestamp: 2026-04-22 14:20
  - Host class(es): Windows x64 / amd64 validated
  - Summary: Established `CHANGE_LOG.md`, `SYSTEM_INVENTORY.md` as part of repo governance
  - Scope: 
    - `CHANGE_LOG.md`
    - `SYSTEM_INVENTORY.md`
  - Validation: 
    - `cat .\CHANGE_LOG.md -head 1` = `# CHANGE_LOG.md`
    - `cat .\SYSTEM_INVENTORY.md -head 1` = `# SYSTEM_INVENTORY.md`
  - Notes: 

