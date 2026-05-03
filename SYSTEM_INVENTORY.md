# SYSTEM_INVENTORY.md
> Authoritative capability ledger. This is not a roadmap or config reference. 
> Inventory entries must reflect only observable artifacts in this repository: files, directories, executable code, configuration, scripts, and explicit UI text. 
> Do not include intent, design plans, or inferred behavior.

## Rules
- One component entry = one capability or feature observed in the repository.
- New capabilities go at the top under `## Inventory` and above `## Observed Initial Inventory`.
- Corrections or clarifications go only below the `## Appendix` section.
- Entries must include:

- Capability: **Brief Descriptive Component Name** 
  - Date/Time
  - State: Planned, Implemented, Verified, Deferred
  - Location: `Relative File Path(s)`
  - Validation: Method &/or `Relative Script Path(s)`; include host class(es) (e.g., `Windows x64`, `Windows ARM64`)
  - Notes: 
    - Optional (3 lines max).

## States
- Planned: intent only, not implemented
- Implemented: code exists, not yet validated end-to-end
- Verified: validated with evidence (command)
- Deferred: intentionally postponed (reason noted)

---

## Inventory

- Capability: Slice G cross-session episodic retrieval and cached recall foundation - 2026-05-02 22:10
  - State: Verified
  - Location: `backend/app/memory/episodic.py`, `backend/app/memory/retrieval.py`, `backend/app/memory/write_policy.py`, `backend/app/conversation/engine.py`, `backend/app/cognition/prompt_assembler.py`, `backend/tests/unit/memory/`, `backend/tests/runtime/turn/test_retrieval_live.py`, `backend/tests/runtime/services/test_retrieval_cached_live.py`
  - Validation: G.1 validated on Windows x64 and Windows ARM64 with memory unit `17 passed`, engine unit `31 passed`, unit validator `306 passed`, regression `96 passed`, and live G.1 retrieval subset `2 passed, 1 deselected`; G.2 validated on Windows x64 and Windows ARM64 with prompt assembler unit `6 passed`, engine unit `35 passed`, unit validator `313 passed`, regression `96 passed`, and live retrieval suite `3 passed`; G.3 validated on Windows x64 and Windows ARM64 with retrieval unit `13 passed`, unit validator `322 passed`, regression `96 passed`, and live Redis cached retrieval `2 passed`; Redis cache miss/hit behavior and Redis-stopped disk-fallback behavior were proven, and Redis was restored healthy after stopped-fallback tests.
  - Slice G added a disk-backed episodic memory write/read substrate, explicit episodic write-policy controls, post-turn episodic writes from the turn lifecycle, recency/keyword retrieval, additive retrieved-context injection into prompt assembly, retrieval provenance recording in `TurnArtifact.retrieved_memory_refs`, and Redis-backed retrieval-cache acceleration with fail-closed fallback to direct episodic disk retrieval.
  - Notes: Durable memory authority remains disk-backed episodic entries under `data/memory/episodic/`, not Redis; Redis is retrieval acceleration only and fails closed to disk-backed retrieval; retrieval is recency+keyword only with semantic/vector memory deferred; retrieval is not a Slice F tool; no API/schema/route changes, desktop/text-shell rendering changes, Slice F tool/executor behavior changes, Group H acceleration behavior, Group I agent behavior, autonomous memory decisions, new packages, new providers, new runtimes, or new services were introduced.

- Capability: Slice F deterministic tool execution and result presentation foundation - 2026-05-03 18:03
  - State: Verified
  - Location: `backend/app/cognition/executor.py`, `backend/app/tools/`, `backend/app/api/schemas/tools.py`, `backend/app/api/schemas/task.py`, `backend/app/api/schemas/voice.py`, `backend/app/api/routes/task.py`, `backend/app/api/routes/voice.py`, `scripts/run_jarvis.py`, `desktop/src/main.js`, `backend/tests/runtime/turn/test_acting_live.py`
  - Validation: F.1 validated on Windows x64 and Windows ARM64 with executor unit `4 passed`, conversation engine unit `29 passed`, unit validator `277 passed`, and regression `95 passed`; F.2 validated on Windows x64 and Windows ARM64 with tools/full unit `289 passed` and regression `95 passed`; F.3 validated on Windows x64 and Windows ARM64 with unit `292 passed` and regression `96 passed`; missed live ACTING/tool gate recovered on Windows x64 in `backend/tests/runtime/turn/test_acting_live.py` using explicit deterministic `tool_name="time"` dispatch, where the live turn reached ACTING and invoked the registered `time` tool, and both result evidence plus persisted artifact evidence captured tool invocation metadata.
  - Slice F added deterministic ACTING lifecycle wiring through explicit `tool_name` dispatch, the cognition executor surface, a bounded tool registry and first tool set, read-only sandboxed filesystem access, an internet-search tool adapter over the existing Slice E internet-search runtime, additive tool-call metadata propagation through task/voice API responses, and text/desktop shell presentation of tool-call metadata.
  - Notes: Tool invocation is deterministic and explicit with no LLM-driven tool selection or model-side function calling; `filesystem.read` is read-only and sandboxed under `data/tool_sandbox/`; internet search remains an adapter over existing Slice E runtime/provider boundaries with no Slice E boundary changes; shell/API changes are presentation-only and do not invoke tools; no Group G memory retrieval, Group I agent behavior, autonomous agents, write tools, filesystem search/indexing, new providers, new packages, new runtimes, or new services were introduced.

- Capability: Slice E local service substrate foundation - 2026-05-01 01:19
  - State: Verified
  - Location: `docker-compose.yml`, `.env.example`, `config/search/searxng/`, `config/search/ddgs/`, `config/search/tavily/`, `config/models/search.yaml`, `backend/app/cache/`, `backend/app/runtimes/internetsearch/`, `backend/app/routing/runtime_selector.py`, `backend/app/core/settings.py`, `backend/tests/runtime/services/`
  - Validation: Existing Slice E evidence recorded in `CHANGE_LOG.md` E.1 through E.5 entries (Windows x64 and Windows ARM64): regression `95 passed` on both host classes; Redis and SearXNG Docker substrate healthy on both host classes; live Redis cache roundtrip proven; live SearXNG, DDGS, and Tavily search evidence proven as recorded; Docker SKIP-no-docker is not the active state because both host classes have Docker-backed validation evidence.
  - Slice E established a repo-owned, `.env`-driven Redis/SearXNG local service substrate, one injectable Redis-backed `CacheManager`, and one fail-closed internet-search runtime interface with SearXNG primary, DDGS fallback, Tavily policy-gated tertiary, and a null/empty-results path when providers are unavailable or error.
  - Notes: This is substrate/runtime capability for later consumers; no user-facing tool behavior is claimed. No F/G/H/I behavior is included in this capability entry.

- Capability: Slice D durable application surface - 2026-04-30 11:13
  - State: Verified
  - Location: `desktop/`, `backend/app/api/`, `backend/app/services/`, `backend/app/personality/`, `backend/tests/runtime/desktop/`
  - Validation: Windows x64 and Windows ARM64 evidence recorded in `CHANGE_LOG.md` D.1 through D.5 entries, including D.2 desktop inventory-linked evidence and the `2026-04-30 11:12` live-evidence closeout delta. Verified capability includes backend FastAPI shell contract, durable npm/Tauri desktop host, backend child lifecycle through `scripts/run_backend.py`, resident session continuity, wake status and deterministic wake detection, selectable personality profiles and presence UI, and runtime desktop live evidence for D.3/D.4.
  - Notes:

- Capability: Slice D.2 durable desktop host - 2026-04-29 10:30
  - State: Verified
  - Location: `desktop/`, `backend/tests/unit/desktop/`
  - Validation: Windows x64 and Windows ARM64 D.2 evidence recorded in `CHANGE_LOG.md`: `2026-04-29 05:32` Windows x64 desktop progress validation, `2026-04-29 06:00` Windows ARM64 desktop progress validation, and `2026-04-29 10:15` D.2 closeout delta. npm/Tauri desktop host validated on both host classes; backend starts through `scripts/run_backend.py`; readiness/runtime display, text turn, tray lifecycle menu, and HTT voice path through `/task/voice` validated; regression remained green on both host classes.
  - Notes: HTT is not the final intended PTT UX; final PTT interaction semantics continue in later D work. Browser capture/WAV path worked, but idealized 16 kHz PCM/downsample quality is not claimed. No resident loop, wake integration, tools/agents, routing policy, WebSockets, audio streaming, or shell-side playback is claimed.

- Capability: Slice C canonical turn/session engine and proving host - 2026-04-28 06:04
  - State: Verified
  - Location: `backend/app/conversation/`, `backend/app/cognition/`, `backend/app/personality/`, `backend/app/services/`, `backend/app/artifacts/`, `backend/app/memory/`, `backend/app/runtimes/stt/barge_in.py`, `backend/app/runtimes/tts/playback.py`, `config/personality/default.yaml`, `scripts/run_jarvis.py`, `backend/tests/unit/conversation/`, `backend/tests/unit/cognition/`, `backend/tests/unit/personality/`, `backend/tests/unit/services/`, `backend/tests/unit/artifacts/`, `backend/tests/unit/memory/`, `backend/tests/unit/scripts/test_run_jarvis_script.py`, `backend/tests/integration/services/test_two_turn_session.py`, `backend/tests/runtime/turn/`
  - Validation: Windows x64 and Windows ARM64 Slice C evidence recorded in `CHANGE_LOG.md`: C.1 x64 at `2026-04-26 21:17`, C.1 ARM64 turn evidence at `2026-04-27 05:36`, and C.2 through C.6 validated on both host classes. Latest C.6 closeout evidence includes focused script unit `11 passed`, unit validator `182 passed`, and regression `74 passed` on both host classes; C.3 integration validator `3 passed`, C.4 runtime validator `5 passed, 3 deselected`, and C.5 runtime validator `5 passed, 4 deselected` on both host classes.
  - Notes: Voice/text turns share one engine with session continuity, canonical artifacts, bounded working memory, deterministic interruption, and a diagnostic proving host. No physical audio-output validation, full acoustic microphone barge-in, durable desktop/API/resident shell, episodic memory, tools, agents, or routing/policy implementation is claimed. QNN STT inference remains deferred to H.2; llama.cpp remains deferred to ~~H.1~~ M.1; no Group D+ implementation is claimed.

- Capability: Slice B cross-platform voice runtime foundation - 2026-04-26 19:45
  - State: Verified
  - Location: `backend/app/runtimes/stt/`, `backend/app/runtimes/tts/`, `backend/app/runtimes/llm/`, `backend/app/runtimes/wake/`, `backend/app/routing/runtime_selector.py`, `backend/app/models/catalog.py`, `config/models/`, `config/app/policies.yaml`, `backend/tests/runtime/voice/`, `backend/tests/unit/runtimes/`, `backend/tests/runtime/acceleration_matrix/test_acceleration_matrix.py`, `scripts/ensure_models.py`, `scripts/validate_backend.py`
  - Validation: Windows x64 and Windows ARM64 B.0-B.5 validation recorded in `CHANGE_LOG.md`; B.5 matrix validation recorded in `CHANGE_LOG.md` entry `2026-04-26 19:45`; x64 matrix artifact `reports/validation/b5-acceleration-matrix-current-host.txt`; x64 regression artifact `reports/validation/20260427004353-regression.txt`; ARM64 B.5 matrix state recorded in `CHANGE_LOG.md` entry `2026-04-26 19:45`.
  - Notes: STT, TTS, LLM, and Wake runtime families exist with device-parameterized runtime surfaces. CPU voice paths and B.5 matrix are validated on Windows x64 and Windows ARM64. QNN remains definition-only with STT inference deferred to H.2; llama.cpp remains deferred to ~~H.1~~ M.1; no Group C/D/E/F/G/H/I implementation is claimed.

- Capability: Slice A hardware/provisioning/readiness foundation - 2026-04-24 17:16
  - State: Verified
  - Location: `backend/app/hardware/`, `backend/app/core/capabilities.py`, `scripts/provision.py`, `scripts/validate_backend.py`, `backend/tests/unit/hardware/`, `backend/tests/unit/scripts/`, `reports/diagnostics/`, `reports/validation/`
  - Validation: Windows x64 manual provisioning/profile/regression PASS; Windows ARM64 manual provisioning/profile/regression PASS; ARM64 A.6 regression PASS with `61 passed`
  - Notes: Covers A.1 profiler/capability flags, A.2 provisioning resolver/install path, A.3 preflight/readiness evidence, A.4 validation/report harness, A.5 x64/ARM64 clean-host validation proof, and A.6 QNN structural metadata/readiness definition only. QNN is not executable at Slice A; `import:onnxruntime-qnn` is present on ARM64; `ep:QNNExecutionProvider:MISSING` and `dll:QnnHtp:MISSING` are expected/not-proven states; STT readiness remains CPU-selected with the H.2-named QNN inference pending reason. No Group B runtime/model/voice-loop work, no STT/TTS/LLM/wake runtime execution, and no durable desktop/product surface were introduced. Codex temp/pytest cleanup failures remain tooling-context only, not repo acceptance evidence.

- Capability: SYSTEM_INVENTORY extablished - 2026-04-22 14:20
  - State: Implemented
  - Location: `SYSTEM_INVENTORY.md`
  - Validation: `cat .\SYSTEM_INVENTORY.md -head 1` = `# SYSTEM_INVENTORY.md`
  - Notes: 

---

## Appendix
