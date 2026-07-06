# SYSTEM_INVENTORY.md
> Authoritative capability ledger. This is not a roadmap or config reference.  
> Inventory entries must reflect only observable artifacts in this repository:  
>   files, directories, executable code, configuration, scripts, and explicit UI text. 
> Do not include intent, design plans, or inferred behavior.

## Rules
- Write component entry for capability or feature group observed in the repository.
- Ordering: Entries are maintained in descending chronological order (newest first, oldest last).
- Append location: New entries must be added at the top directly under `## Inventory Entries`.
- Corrections or clarifications go only below the `##  Inventory Appendix` section.
- Each entry must include:

- Timestamp: `YYYY-MM-DD HH:MM`
  - State: Verified, Implemented, or Scaffold
  - Host class(es): validated on (e.g., `Windows x64`, `Windows ARM64`, etc. as appropriate)
  - Summary: description of codebase changed, 1–2 lines, past tense
  - Location: (list location where capability can be found, 1-5 lines)
    - List folders, files, areas
  - Evidence: (list referenceable reproducable evidence as validation)
    - Timestamp: List supporting `CHANGE_LOG.md` entries (by `Timestamp:` with brief descriptive `Summary:` excerpt)
  - Notes: (list notes as appropriate - optional)
    - List of notes

## States
- Verified: validated with evidence working
- Implemented: code exists, not yet validated end-to-end
- Scaffold: put into place to mark a boundary of future capability; no implementation is claimed

---

## Inventory Entries

- Timestamp: 2026-07-05 10:37
  - State: Implemented
  - Host class(es): Windows x64 / amd64 validated
  - Summary: Updated `CHANGE_LOG.md`, `SYSTEM_INVENTORY.md` to organize repo governance
  - Location: 
    - `CHANGE_LOG.md`
    - `SYSTEM_INVENTORY.md`
  - Evidence: 
    - Timestamp: 2026-07-05 10:30 - Established `CHANGE_LOG.md`, `SYSTEM_INVENTORY.md` ...
  - Notes: 

---

## Inventory Appendix

---

## Consolidated Inventory History

- Timestamp: 2026-05-03 18:03
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established the Slice F deterministic tool execution and result presentation foundation: explicit `tool_name`-driven ACTING lifecycle wiring, a cognition executor surface, bounded tool registry, first tool set, read-only sandboxed filesystem access, internet-search tool adaptation, API metadata propagation, and text/desktop presentation of tool-call metadata.
  - Scope:
    - `backend/app/cognition/executor.py`
    - `backend/app/tools/`
    - `backend/app/api/schemas/tools.py`
    - `backend/app/api/schemas/task.py`
    - `backend/app/api/schemas/voice.py`
    - `backend/app/api/routes/task.py`
    - `backend/app/api/routes/voice.py`
    - `scripts/run_jarvis.py`
    - `desktop/src/main.js`
    - `backend/tests/runtime/turn/test_acting_live.py`
  - Validation: F.1 was validated on Windows x64 and Windows ARM64 with executor unit `4 passed`, conversation engine unit `29 passed`, unit validator `277 passed`, and regression `95 passed`; F.2 was validated on both host classes with tools/full unit `289 passed` and regression `95 passed`; F.3 was validated on both host classes with unit `292 passed` and regression `96 passed`; live ACTING/tool evidence on Windows x64 proved a turn reached ACTING, invoked the registered `time` tool through explicit deterministic dispatch, and recorded tool invocation metadata in both result and persisted artifact evidence.
  - Notes:
    - Tool invocation is deterministic and explicit; no LLM-driven tool selection or model-side function calling is claimed.
    - `filesystem.read` is read-only and sandboxed under `data/tool_sandbox/`.
    - Internet search is an adapter over the existing Slice E runtime/provider boundary. Slice F did not introduce new search providers, packages, runtimes, or services.
    - Shell/API changes are presentation-only and do not themselves invoke tools. No Group G memory retrieval, Group I agent behavior, autonomous agents, write tools, or filesystem search/indexing is claimed.

- Timestamp: 2026-05-01 01:19
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established the Slice E local service substrate: repo-owned `.env`-driven Redis and SearXNG configuration, injectable Redis-backed cache management, and a fail-closed internet-search runtime interface with SearXNG primary, DDGS fallback, Tavily policy-gated tertiary, and null/empty-results behavior for unavailable or failing providers.
  - Scope:
    - `docker-compose.yml`
    - `.env.example`
    - `config/search/searxng/`
    - `config/search/ddgs/`
    - `config/search/tavily/`
    - `config/models/search.yaml`
    - `backend/app/cache/`
    - `backend/app/runtimes/internetsearch/`
    - `backend/app/routing/runtime_selector.py`
    - `backend/app/core/settings.py`
    - `backend/tests/runtime/services/`
  - Validation: Slice E evidence in `CHANGE_LOG.md` E.1 through E.5 validated regression `95 passed` on both Windows x64 and Windows ARM64; Redis and SearXNG Docker substrate health was proven on both host classes; live Redis cache roundtrip was proven; live SearXNG, DDGS, and Tavily search evidence was proven as recorded.
  - Notes:
    - Redis is substrate/cache acceleration, not durable authority.
    - This entry claims substrate/runtime capability for retrieval, tool, memory, and acceleration consumers. It does not claim user-facing tool behavior, retrieval, tool orchestration, hardware acceleration, or agent runtime behavior.

- Timestamp: 2026-04-30 11:13
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established the Slice D durable application surface: backend FastAPI shell contract, durable npm/Tauri desktop host, backend child lifecycle through `scripts/run_backend.py`, resident session continuity, wake status and deterministic wake detection, selectable personality profiles, presence UI, and desktop runtime live evidence for the relevant D.3/D.4 paths.
  - Scope:
    - `desktop/`
    - `backend/app/api/`
    - `backend/app/services/`
    - `backend/app/personality/`
    - `backend/tests/unit/desktop/`
    - `backend/tests/runtime/desktop/`
  - Validation: Windows x64 and Windows ARM64 evidence was recorded in `CHANGE_LOG.md` D.1 through D.5 entries, including D.2 desktop evidence and the `2026-04-30 11:12` live-evidence closeout delta. D.2 validated the npm/Tauri desktop host on both host classes, backend startup through `scripts/run_backend.py`, readiness/runtime display, text turn, tray lifecycle menu, HTT voice path through `/task/voice`, and green regression on both host classes.
  - Notes:
    - HTT was a proof path, not the durable PTT interaction. The desktop shell boundary owns click-start/click-stop PTT semantics.
    - Browser capture/WAV path worked, but idealized 16 kHz PCM/downsample quality was not claimed.
    - Slice D established durable desktop/API surface capability. The D.2 entry did not claim resident loop, wake integration, tools/agents, routing policy, WebSockets, audio streaming, or shell-side playback beyond the later Slice D closeout scope described above.

- Timestamp: 2026-04-28 06:04
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established the Slice C canonical turn/session engine and proving host: one shared engine for voice and text turns, session continuity, canonical artifacts, bounded working memory, deterministic interruption behavior, personality/cognition integration points, and a diagnostic proving host.
  - Scope:
    - `backend/app/conversation/`
    - `backend/app/cognition/`
    - `backend/app/personality/`
    - `backend/app/services/`
    - `backend/app/artifacts/`
    - `backend/app/memory/`
    - `backend/app/runtimes/stt/barge_in.py`
    - `backend/app/runtimes/tts/playback.py`
    - `config/personality/default.yaml`
    - `scripts/run_jarvis.py`
    - `backend/tests/unit/conversation/`
    - `backend/tests/unit/cognition/`
    - `backend/tests/unit/personality/`
    - `backend/tests/unit/services/`
    - `backend/tests/unit/artifacts/`
    - `backend/tests/unit/memory/`
    - `backend/tests/unit/scripts/test_run_jarvis_script.py`
    - `backend/tests/integration/services/test_two_turn_session.py`
    - `backend/tests/runtime/turn/`
  - Validation: Windows x64 and Windows ARM64 Slice C evidence was recorded in `CHANGE_LOG.md`: C.1 x64 at `2026-04-26 21:17`, C.1 ARM64 turn evidence at `2026-04-27 05:36`, and C.2 through C.6 validated on both host classes. Latest C.6 closeout evidence included focused script unit `11 passed`, unit validator `182 passed`, and regression `74 passed` on both host classes; C.3 integration validator `3 passed`, C.4 runtime validator `5 passed, 3 deselected`, and C.5 runtime validator `5 passed, 4 deselected` on both host classes.
  - Notes:
    - Voice and text turns share one engine with explicit session continuity and turn artifacts.
    - Slice C did not claim physical audio-output validation, full acoustic microphone barge-in, durable desktop/API/resident shell, episodic memory, tools, agents, routing/policy implementation, QNN STT inference, or verified llama.cpp runtime wiring.

- Timestamp: 2026-04-26 19:45
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established the Slice B cross-platform voice runtime foundation: STT, TTS, LLM, and Wake runtime families with device-parameterized runtime surfaces, model catalog/config wiring, runtime selector policy boundary, model acquisition support, and arch-aware unit/runtime validation surfaces.
  - Scope:
    - `backend/app/runtimes/stt/`
    - `backend/app/runtimes/tts/`
    - `backend/app/runtimes/llm/`
    - `backend/app/runtimes/wake/`
    - `backend/app/routing/runtime_selector.py`
    - `backend/app/models/catalog.py`
    - `config/models/`
    - `config/app/policies.yaml`
    - `backend/tests/runtime/voice/`
    - `backend/tests/unit/runtimes/`
    - `backend/tests/runtime/acceleration_matrix/test_acceleration_matrix.py`
    - `scripts/ensure_models.py`
    - `scripts/validate_backend.py`
  - Validation: Windows x64 and Windows ARM64 B.0-B.5 validation was recorded in `CHANGE_LOG.md`; B.5 matrix validation was recorded in the `2026-04-26 19:45` entry. Evidence included x64 matrix artifact `reports/validation/b5-acceleration-matrix-current-host.txt`, x64 regression artifact `reports/validation/20260427004353-regression.txt`, and ARM64 B.5 matrix state recorded in `CHANGE_LOG.md`.
  - Notes:
    - CPU voice paths and the voice-family matrix were validated on Windows x64 and Windows ARM64.
    - QNN remained definition-only for this entry; hardware acceleration owns STT inference validation.
    - llama.cpp was not wired as a verified runtime in Slice B; local LLM runtime wiring and validation belong to the later local LLM boundary.
    - Slice B did not claim conversation/session, desktop shell, service substrate, tool orchestration, semantic memory, hardware acceleration, or agent runtime implementation.

- Timestamp: 2026-04-24 17:16
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established the Slice A hardware intelligence foundation: normalized hardware profiling and capability flags, profiler-driven provisioning, preflight/readiness evidence, validation/reporting harness support, x64/ARM64 clean-host proof, and structural QNN metadata/readiness definition.
  - Scope:
    - `backend/app/hardware/`
    - `backend/app/core/capabilities.py`
    - `scripts/provision.py`
    - `scripts/validate_backend.py`
    - `backend/tests/unit/hardware/`
    - `backend/tests/unit/scripts/`
    - `reports/diagnostics/`
    - `reports/validation/`
  - Validation: Windows x64 manual provisioning, profile, and regression validation passed; Windows ARM64 manual provisioning, profile, and regression validation passed; ARM64 A.6 regression passed with `61 passed`.
  - Notes:
    - Slice A covers A.1 profiler/capability flags, A.2 provisioning resolver/install path, A.3 preflight/readiness evidence, A.4 validation/report harness, A.5 x64/ARM64 clean-host validation proof, and A.6 QNN structural metadata/readiness definition.
    - QNN was structural metadata/readiness only at Slice A. `import:onnxruntime-qnn` was present on ARM64, while `ep:QNNExecutionProvider:MISSING` and `dll:QnnHtp:MISSING` were expected not-proven states.
    - STT readiness remained CPU-selected with QNN inference pending. Slice A did not introduce Group B runtime/model/voice-loop work, STT/TTS/LLM/wake runtime execution, or a durable desktop/product surface.

- Timestamp: 2026-04-22 14:25
  - State: Implemented
  - Host class(es): Windows x64 / amd64 validated
  - Summary: Established `CHANGE_LOG.md`, `SYSTEM_INVENTORY.md` as part of repo governance
  - Location: 
    - `CHANGE_LOG.md`
    - `SYSTEM_INVENTORY.md`
  - Evidence: 
    - Timestamp: 2026-04-22 14:20 - Established `CHANGE_LOG.md`, `SYSTEM_INVENTORY.md` ...
  - Notes: 

