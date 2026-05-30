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

- Capability: Slice K+ desktop/operator cleanup and ARM64 QNN voice validation - 2026-05-30 06:58
  - State: Verified
  - Location: `desktop/src/index.html`, `desktop/src/main.js`, `desktop/src/style.css`, `desktop/src/components/readiness-panel.js`, `desktop/src/components/degraded-list.js`, `desktop/src/components/settings-panel.js`, `desktop/src-tauri/src/backend.rs`, `desktop/src-tauri/src/lib.rs`, `backend/app/api/service_status.py`, `backend/app/services/wake_monitor.py`, `backend/app/services/voice_service.py`, `backend/app/tools/search/search_tool.py`, `pyproject.toml`, `scripts/provision.py`, `backend/app/hardware/provisioning.py`, `backend/app/hardware/preflight.py`, `backend/app/hardware/qnn_provider.py`, `CHANGE_LOG.md`
  - Validation: Windows ARM64 / Qualcomm QNN evidence recorded in committed `CHANGE_LOG.md` entry at commit `cdf81476474fb9e3e4ec4cfb33b2848f072d0ea4`, plus Slice K+ entries in `CHANGE_LOG.md`: focused QNN provider tests PASS (`33 passed`), provision verify PASS, profile PASS (`ready; tokens=18`), regression PASS (`115 passed, 4 deselected`), QNN hardware live gate PASS (`2 passed`), QNN STT live fixture PASS (`1 passed`), and User desktop live proof PASS with wake monitoring active, wake detection incremented, resident voice turn completed from `source: wake`, transcript/response populated, and no visible failure reason.
  - Notes: Extends Slice K with three-pane layout/readability cleanup, readiness/sidebar refinements, settings access fix, SearXNG/service-status corrections, search provider escalation repair, and wake/operator panel surfacing. ARM64 voice path validated as STT `onnx-whisper / qnn`, TTS `kokoro-onnx / cpu`, Wake `openwakeword / cpu`; QNN provider surface uses `onnxruntime-qnn==1.24.3` as the sole ORT runtime distribution with readiness proven through built-in `onnxruntime`.

- Capability: Slice K operator controls/settings UX - 2026-05-26 21:45
  - State: Verified
  - Location: `desktop/src/components/settings-panel.js`, `desktop/src/components/service-status.js`, `desktop/src/components/appearance-controls.js`, `desktop/src/main.js`, `desktop/src/index.html`, `backend/app/api/routes/config.py`, `backend/app/api/schemas/config.py`, `backend/app/api/service_status.py`, `backend/app/api/routes/readiness.py`, `backend/app/api/schemas/readiness.py`, `backend/tests/unit/api/test_routes.py`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Validation: Windows ARM64 evidence recorded in `CHANGE_LOG.md` K.1-K.4 entries. Windows x64 regression evidence: `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`105 passed, 4 deselected`), report `reports\validation\20260527024302-regression.txt`.
  - Notes: Slice K added personality metadata display for Tone/Brevity/Formality without changing personality runtime behavior; allowlisted `/config/operator` read/write against existing `.env` with masked secrets and no `TAVILY_API_KEY` exposure; backend-field-driven settings panel with restart-required UX using existing backend lifecycle commands; additive Redis/SearXNG readiness service status rendered in the desktop sidebar; and localStorage-backed appearance controls for font size, density, and accent preferences. No cloud escalation, new Tauri commands, service start/stop controls, or semantic state-token overrides were added.

- Capability: Slice J runtime/readiness UX and desktop interaction surfacing - 2026-05-26 11:42
  - State: Verified
  - Location: `desktop/src/index.html`, `desktop/src/main.js`, `desktop/src/style.css`, `desktop/src/components/readiness-panel.js`, `desktop/src/components/degraded-list.js`, `desktop/src/components/state-label.js`, `desktop/src/components/wake-indicator.js`, `backend/tests/unit/desktop/test_desktop_static_contract.py`, `docs/windows-arm64-fresh-clone-setup.md`, `CHANGE_LOG.md`
  - Validation: Windows x64 evidence recorded in `CHANGE_LOG.md` (`2026-05-22 07:54`, `2026-05-22 08:20`, `2026-05-22 09:10`, `2026-05-22 10:01`, `2026-05-22 18:27`, `2026-05-22 18:45`): desktop static contract progressed through `15 passed`, `17 passed`, `19 passed`, `23 passed`, and `24 passed`; regression remained PASS at `104 passed, 4 deselected`; x64 manual desktop smoke passed after retry with click-start / click-stop PTT and STT→LLM→TTS. Windows ARM64 evidence recorded in `CHANGE_LOG.md` (`2026-05-26 11:31`, `2026-05-26 11:42`): desktop static contract PASS (`24 passed in 0.11s`); regression PASS (`105 passed, 4 deselected in 1.09s`); desktop app built/launched as `target\debug\jarvisv7-desktop.exe`; User initial ARM64 visual smoke OK.
  - Notes: Slice J surfaces existing backend data with no backend schema/routes or Tauri command additions; HTT proof behavior was replaced by click-start/click-stop PTT; active Ollama with local-runtime unavailable renders degraded, not hard-failed, while preserving backend reason/degraded listing; J.5 rendering was not executed because no safe local renderer/sanitizer approach was approved; ARM64 voice/transcription was not manually checked in final visual smoke, while x64 manual evidence proved STT→LLM→TTS for the new PTT path.

- Capability: Slice I hardware path normalization and live mic/audio interaction matrix - 2026-05-13 15:07
  - State: Verified
  - Location: `backend/app/hardware/readiness.py`, `config/hardware/notes.md`, `backend/app/api/schemas/voice.py`, `backend/app/api/routes/voice.py`, `backend/tests/unit/api/test_routes.py`, `backend/tests/runtime/turn/test_voice_acceleration_matrix_live.py`, `20260513_slice-i.md`, `20260513_slice-i3.md`, `CHANGE_LOG.md`
  - Validation: Windows x64 and Windows ARM64 evidence recorded in `CHANGE_LOG.md` (`2026-05-13 14:21`, `2026-05-13 14:31`, `2026-05-13 14:44`, `2026-05-13 14:57`): I.1 ARM64 normalization PASS with unit/regression/runtime evidence; I.2 x64 normalization PASS with unit/regression/runtime evidence; I.3 x64 live mic/audio matrix PASS (`runtime --families turn --devices cuda: 1 passed, 32 deselected`), and I.3 ARM64 follow-up PASS (`runtime --families turn --devices qnn: 1 passed, 34 deselected`; `runtime --families turn --devices cpu: 10 passed, 1 skipped, 24 deselected`) with regression remaining PASS (`104 passed, 4 deselected`) on both host classes.
  - Notes: Slice I closed with deterministic host-specific acceleration/readiness normalization plus `/task/voice` STT-device observability and host-gated live turn matrix coverage.

- Capability: Slice H voice acceleration matrix and live turn gates - 2026-05-13 09:10
  - State: Verified
  - Location: `backend/tests/runtime/turn/test_voice_acceleration_matrix_live.py`, `backend/tests/runtime/acceleration_matrix/test_acceleration_matrix.py`, `reports/validation/h8-voice-acceleration-matrix-current-host.txt`, `CHANGE_LOG.md`
  - Validation: Windows x64 and Windows ARM64 evidence recorded in `CHANGE_LOG.md` (`2026-05-13 09:01`): x64 H.8 live turn matrix PASS, x64 H.8 acceleration matrix PASS, and x64 regression PASS; ARM64 H.8 live turn matrix PASS (`1 passed in 17.45s`), ARM64 H.8 acceleration matrix PASS (`1 passed in 1.88s`), and ARM64 regression PASS (`104 passed, 4 deselected`).
  - Notes: H.8 superseded the prior B.5 voice-family matrix gate with a Slice H voice acceleration matrix plus live full-turn validation surface.

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
