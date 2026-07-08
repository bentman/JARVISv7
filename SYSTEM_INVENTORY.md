# SYSTEM_INVENTORY.md
> Authoritative capability ledger. This is not a roadmap or config reference.  
> Inventory entries must reflect only observable artifacts in this repository:  
>   files, directories, executable code, configuration, scripts, and explicit UI text. 
> Do not include intent, design plans, or inferred behavior.

## Rules
- Write component entry for capability or feature group observed in the repository.
- Ordering: Entries are maintained in descending chronological order (newest first, oldest last).
- Append location: New entries must be added at the top directly under `## Inventory Entries`.
- Corrections or clarifications go only below the `## Inventory Appendix` section.
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

- Timestamp: 2026-07-08 07:15
  - State: Verified
  - Host class(es): Windows AMD64 / amd64 validated
  - Summary: Eager model warmup for STT, TTS, and Wake runtimes, robust llama-server and Python port reclamation, Rust sidecar launcher cleanup, adaptive session polling, and synchronized resident voice unit testing.
  - Location:
    - `backend/app/runtimes/stt/`, `backend/app/runtimes/tts/`, `backend/app/runtimes/wake/`
    - `backend/app/services/`, `backend/app/api/`
    - `desktop/src-tauri/src/`, `desktop/src/components/`
  - Evidence:
    - Timestamp: 2026-07-08 07:15 - Resolved eager model warmup for STT, TTS, and Wake monitor, implemented robust port reclamation and zombie process reap logic, optimized dynamic/adaptive session polling, and synchronized resident voice unit tests.
  - Notes:
    - Warmups eagerly load model weights during system initialization to eliminate first-use inference spikes.
    - Port reclamation force-kills any matching process occupying required ports (8765 and llama-server ports) before launch.
    - Desktop session polling dynamically increases to 100ms when active/transient phases are detected and drops back to 1000ms.

- Timestamp: 2026-07-07 20:35
  - State: Verified
  - Host class(es): Windows AMD64 / amd64 validated
  - Summary: Established Slice AA resident voice stabilization and conversation-flow improvements: PTT-only startup posture, explicit Wake/operator controls, voice-turn diagnostics, live phase/status reporting, hardened PTT no-speech recovery, stabilized endpointing, and config-backed TTS voice selection.
  - Location:
    - `backend/app/services/`, `backend/app/conversation/`, `backend/app/runtimes/stt/`, `backend/app/runtimes/tts/`
    - `backend/app/api/`, `backend/app/artifacts/`, `config/models/tts.yaml`
    - `desktop/src/`, `desktop/src/components/`, `desktop/tests/`
  - Evidence:
    - Timestamp: 2026-07-07 07:30 - Completed Slice AA resident voice stabilization and operator-surface work through AA.7.
    - Timestamp: 2026-07-07 20:24 - Corrected AA.7 Resident Voice TTS selector behavior and layout.
    - Timestamp: 2026-07-07 20:35 - Added `capture_ms` timing to streamed Resident Voice PTT capture diagnostics.
  - Notes:
    - No new model VAD dependency, accelerator capability, hidden always-listening default, or autonomous agent behavior is claimed.

- Timestamp: 2026-07-05 10:37
  - State: Implemented
  - Host class(es): Windows x64 / amd64 validated
  - Summary: Updated repo governance ledgers for consolidation organization.
  - Location:
    - `CHANGE_LOG.md`
    - `SYSTEM_INVENTORY.md`
  - Evidence:
    - Timestamp: 2026-07-05 10:30 - Updated `CHANGE_LOG.md`, `SYSTEM_INVENTORY.md` to organize repo governance.
  - Notes:
    - Governance documentation organization only; no runtime capability changed.

---

## Inventory Appendix

---

## Consolidated Inventory History

- Timestamp: 2026-07-04 10:35
  - State: Verified
  - Host class(es): Windows AMD64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice Z startup truth, desktop readiness/status polish, diagnostics, and personality request-path/profile behavior.
  - Location:
    - `backend/app/services/startup_context.py`, `backend/app/api/`, `scripts/`
    - `config/personality/`, `backend/app/personality/`, `backend/app/cognition/`
    - `backend/app/conversation/`, `backend/app/runtimes/llm/`
    - `desktop/src/`, `backend/tests/`, `desktop/tests/`
  - Evidence:
    - Timestamp: 2026-07-04 22:11 - Completed Slice Z desktop/startup/personality/debug polish through Z.6.
  - Notes:
    - Slice Z is presentation, startup-truth, diagnostics, and personality polish; new model artifacts, accelerator capability, agent execution, memory behavior, and provisioning workflows were not included.

- Timestamp: 2026-07-01 10:25 UTC
  - State: Verified
  - Host class(es): Windows AMD64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice X local LLM tier activation with dev/prod model mode and Qwen3 production catalog selection.
  - Location:
    - `.env.example`, `config/models/llm.yaml`
    - `backend/app/models/`, `backend/app/services/local_llm_startup.py`
    - `backend/app/runtimes/llm/`, `backend/app/routing/`
    - `backend/app/api/`, `scripts/`, `desktop/src/components/settings-panel.js`
  - Evidence:
    - Timestamp: 2026-07-03 13:19 - Completed Slice X local LLM tier activation and desktop readiness/status validation.
  - Notes:
    - Reused existing catalog/settings/selection/readiness paths; NPU/QNN LLM acceleration was not claimed.

- Timestamp: 2026-07-01 00:46 UTC
  - State: Verified
  - Host class(es): Windows AMD64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice W safe environment defaults and Operator settings posture.
  - Location:
    - `.env.example`, `docker-compose.yml`
    - `backend/app/core/settings.py`, `backend/app/api/routes/config.py`
    - `scripts/ensure_models.py`, `backend/app/services/local_llm_startup.py`
    - `desktop/src/components/settings-panel.js`, `docs/QuickStart.md`, `backend/tests/`
  - Evidence:
    - Timestamp: 2026-06-30 15:51 - Completed Slice W settings posture cleanup and corrective W2 cleanup.
  - Notes:
    - Settings posture cleanup only; new model artifacts, accelerator claims, runtime architecture, and setup workflows were not included.

- Timestamp: 2026-06-30 09:25
  - State: Verified
  - Host class(es): Windows AMD64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice V model-selection policy, selected-LLM setup, and Operator model policy control.
  - Location:
    - `config/models/llm.yaml`, `backend/app/models/`
    - `backend/app/services/local_llm_startup.py`, `backend/app/runtimes/llm/`
    - `backend/app/routing/`, `backend/app/api/`, `scripts/`
    - `desktop/src/components/settings-panel.js`, `backend/tests/`
  - Evidence:
    - Timestamp: 2026-06-30 08:52 - Completed Slice V model selection policy and setup simplification.
  - Notes:
    - Selection resolves through existing `assistant-small-q4` roles; no Qwen/Gemma/vision model capability or new runtime architecture was claimed.

- Timestamp: 2026-06-28 23:19
  - State: Verified
  - Host class(es): Windows ARM64 / arm64 validated, with Windows AMD64 / amd64 non-selection validation
  - Summary: Established Slice U side-by-side Qualcomm QNN Whisper STT runtime path.
  - Location:
    - `backend/app/hardware/qnn_provider.py`
    - `backend/app/runtimes/stt/`, `config/models/stt.yaml`
    - `backend/tests/unit/hardware/`, `backend/tests/unit/runtimes/stt/`
    - `backend/tests/runtime/hardware/`, `backend/tests/runtime/acceleration_matrix/`
  - Evidence:
    - Timestamp: 2026-06-30 05:44 - Completed Slice U Qualcomm QNN Whisper integration and staged resident voice stabilization.
  - Notes:
    - ARM64 QNN STT uses side-by-side `whisper-qualcomm-qnn` and ONNX Runtime EP-device initialization; AMD64 QNN execution was not claimed.

- Timestamp: 2026-06-26 10:51
  - State: Verified
  - Host class(es): Windows AMD64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice T resident shared-stream voice layer with wake/PTT, VAD, barge-in follow-up, and desktop controls.
  - Location:
    - `backend/app/services/`
    - `backend/app/conversation/`, `backend/app/runtimes/stt/`, `backend/app/runtimes/tts/`
    - `backend/app/api/`, `desktop/src/`
    - `backend/tests/unit/`, `backend/tests/runtime/`, `desktop/tests/`
  - Evidence:
    - Timestamp: 2026-06-26 10:51 - Completed Slice T resident full-duplex voice foundation and corrective closeout.
  - Notes:
    - Verified shared microphone stream behavior; echo cancellation, overlapped-speech robustness, browser microphone transport, Silero VAD, and hidden always-listening default were not claimed.

- Timestamp: 2026-06-24 07:48
  - State: Verified
  - Host class(es): Windows AMD64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice S repo-owned local llama.cpp runtime artifact and acceleration-profile acquisition framework.
  - Location:
    - `config/models/llm.yaml`, `scripts/ensure_models.py`
    - `backend/app/models/llm_profiles.py`
    - `backend/app/hardware/`, `backend/app/api/routes/readiness.py`
    - `backend/tests/`, `docs/jarvis-arm-llamacpp.md`
  - Evidence:
    - Timestamp: 2026-06-24 07:48 - Completed Slice S local llama.cpp runtime artifact and acceleration-profile acquisition framework ...
  - Notes:
    - Supersedes older Group R artifact state with repo-owned CPU and AMD64 CUDA acquisition truth; ARM64 Adreno OpenCL remains staged/end-user-buildable, and QNN/Hexagon local LLM acceleration remains unimplemented.

- Timestamp: 2026-06-18 04:36
  - State: Verified
  - Host class(es): Windows AMD64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Group R managed local llama.cpp LLM runtime, sidecar lifecycle, and local-first runtime selection path.
  - Location:
    - `config/models/llm.yaml`, `.env.example`
    - `backend/app/services/local_llm_sidecar.py`, `backend/app/services/local_llm_startup.py`
    - `backend/app/runtimes/llm/`, `backend/app/routing/`
    - `backend/app/api/`, `scripts/ensure_models.py`, `backend/tests/`
  - Evidence:
    - Timestamp: 2026-06-18 04:59 - Completed Slice R managed local LLM sidecar/runtime path through the current repo state ...
  - Notes:
    - CPU-only local llama.cpp was live-proven on AMD64 and ARM64; Ollama remains fallback. CUDA and QNN local llama.cpp live completion were not claimed by this entry.

- Timestamp: 2026-06-15 10:14
  - State: Verified
  - Host class(es): Windows x64 / amd64 validated
  - Summary: Established Group P spec-first agent catalog and deterministic Agent Creator boundary.
  - Location:
    - `backend/app/agents/`
    - `backend/app/api/routes/agents.py`, `backend/app/api/schemas/agents.py`
    - `config/agents/specs/`, `config/prompts/agents/`
    - `backend/tests/unit/agents/`, `backend/tests/unit/api/`
  - Evidence:
    - Timestamp: 2026-06-15 10:14 - Completed Slice P spec-first agent correction ...
  - Notes:
    - Agent Creator writes validated disabled specs only; autonomous/background execution, turn-engine integration, model/tool calls, training/deployment, and desktop UI behavior were not included.

- Timestamp: 2026-06-15 08:14
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / Qualcomm QNN validated
  - Summary: Established Group O truthful default-disabled dry-run agent boundary and read-only trace diagnostics.
  - Location:
    - `backend/app/agents/`
    - `backend/app/api/routes/agents.py`, `backend/app/api/schemas/agents.py`
    - `config/app/policies.yaml`, `config/agents/`, `config/prompts/agents/`
    - `backend/tests/unit/agents/`, `backend/tests/unit/api/`
  - Evidence:
    - Timestamp: 2026-06-15 08:14 - Completed Slice O truthful dry-run agent boundary ...
  - Notes:
    - Agent surfaces are explicit, read-only or dry-run, and default-disabled; hidden/background execution, model routing, training/deployment, desktop UI, and normal conversation behavior changes were not included.

- Timestamp: 2026-06-14 10:32
  - State: Verified
  - Host class(es): Windows x64 / amd64 validated
  - Summary: Established Group N conversation continuity and session memory boundary.
  - Location:
    - `backend/app/artifacts/`
    - `backend/app/conversation/`
    - `backend/app/cognition/`
    - `backend/tests/unit/artifacts/`, `backend/tests/unit/conversation/`, `backend/tests/unit/cognition/`
  - Evidence:
    - Timestamp: 2026-06-15 05:08 - Completed Slice N conversation continuity and session memory boundary ...
  - Notes:
    - Adds deterministic session timelines, bounded continuity packets, prompt ordering, and conservative closeout metadata; semantic/vector memory and agents remained outside this boundary.

- Timestamp: 2026-06-13 18:21
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Group M realtime conversation session boundary for resident wake/PTT invocation events.
  - Location:
    - `backend/app/conversation/realtime/`
    - `backend/app/services/resident_voice_invocation.py`
    - `backend/tests/unit/conversation/realtime/`, `backend/tests/unit/services/`
  - Evidence:
    - Timestamp: 2026-06-15 05:08 - Completed Slice M realtime conversation session boundary ...
  - Notes:
    - Realtime coordination records ordered events and delegates committed turns to `TurnEngine`; committed turn execution authority was not moved.

- Timestamp: 2026-06-12 11:46
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice L structured personality policy envelope and provenance-aware prompt rendering.
  - Location:
    - `backend/app/personality/`, `config/personality/`
    - `backend/app/cognition/`
    - `backend/app/conversation/`, `backend/app/runtimes/llm/`
    - `backend/app/api/`, `backend/tests/`
  - Evidence:
    - Timestamp: 2026-06-15 05:08 - Completed Slice L personality policy envelope ...
  - Notes:
    - Personality compiles to style policy and prompt envelopes; tool authority, runtime selection, safety policy, and orchestration state were not changed.

- Timestamp: 2026-05-30 06:58
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / Qualcomm QNN validated
  - Summary: Established Slice K operator desktop/settings UX, service readiness surfacing, wake controls, and ARM64 QNN voice validation.
  - Location:
    - `desktop/src/`, `desktop/src-tauri/src/`
    - `backend/app/api/`, `backend/app/services/`
    - `backend/app/hardware/`, `backend/app/tools/search/`
    - `scripts/provision.py`, `pyproject.toml`, `backend/tests/`
  - Evidence:
    - Timestamp: 2026-05-29 07:40 - Completed Slice K operator desktop/readiness/wake surface work ...
    - Timestamp: 2026-06-12 14:41 - Completed Slice H voice acceleration normalization and live evidence ...
  - Notes:
    - Consolidates K and K+ inventory state; ARM64 voice path was validated as STT QNN, TTS CPU, and Wake CPU. New agent behavior and service start/stop controls were not included.

- Timestamp: 2026-05-26 11:42
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice J desktop readiness, degraded-state, wake/PTT, and interaction-state surfacing.
  - Location:
    - `desktop/src/`
    - `desktop/src/components/`
    - `backend/tests/unit/desktop/`
    - `docs/windows-arm64-fresh-clone-setup.md`
  - Evidence:
    - Timestamp: 2026-05-22 18:45 - Completed Slice J desktop readiness and interaction polish ...
  - Notes:
    - Slice J surfaced existing backend data in the desktop shell; backend schemas/routes, Tauri commands, dependency/provisioning, and runtime selection were not changed.

- Timestamp: 2026-05-13 15:07
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice I host-specific acceleration/readiness normalization and live voice interaction matrix coverage.
  - Location:
    - `backend/app/hardware/readiness.py`
    - `backend/app/api/routes/voice.py`, `backend/app/api/schemas/voice.py`
    - `backend/tests/runtime/acceleration_matrix/`
    - `config/hardware/notes.md`
  - Evidence:
    - Timestamp: 2026-05-13 14:57 - Completed Slice I acceleration sequence normalization and live user-interaction matrix extension ...
  - Notes:
    - Slice I added STT-device observability and host-gated live turn matrix proof; runtime-family dispatch changes were not included.

- Timestamp: 2026-05-13 09:10
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice H voice acceleration matrix and live full-turn validation gates.
  - Location:
    - `backend/tests/runtime/acceleration_matrix/`
    - `reports/validation/`
  - Evidence:
    - Timestamp: 2026-06-12 14:41 - Completed Slice H voice acceleration normalization and live evidence ...
  - Notes:
    - CPU STT remained fallback; accelerated STT proof covered x64 CUDA and ARM64 QNN, while DirectML and accelerated TTS remained not wired.

- Timestamp: 2026-05-03 18:03
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice F deterministic tool execution, tool metadata, and result presentation foundation.
  - Location:
    - `backend/app/cognition/`
    - `backend/app/tools/`
    - `backend/app/api/`, `scripts/run_jarvis.py`, `desktop/src/`
    - `backend/tests/`
  - Evidence:
    - Timestamp: 2026-05-02 18:03 - Completed Slice F deterministic tool execution and rendering surface ...
  - Notes:
    - Tool invocation is explicit through `tool_name`; LLM-driven tool selection, autonomous agents, write tools, and new runtime/provider surfaces were not included.

- Timestamp: 2026-05-02 22:10
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice G disk-backed episodic memory, retrieval, prompt context injection, and Redis retrieval-cache acceleration.
  - Location:
    - `backend/app/memory/`
    - `backend/app/conversation/`, `backend/app/cognition/`
    - `backend/tests/unit/memory/`, `backend/tests/runtime/`
  - Evidence:
    - Timestamp: 2026-05-02 22:10 - Completed Slice G episodic memory and retrieval substrate ...
  - Notes:
    - Durable memory authority remains disk-backed episodic entries; Redis is cache acceleration only. Semantic/vector memory, API/desktop rendering, and tool-executor behavior were not included.

- Timestamp: 2026-05-01 01:19
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice E local service substrate, Redis cache layer, and fail-closed internet-search runtime.
  - Location:
    - `docker-compose.yml`, `.env.example`
    - `config/search/`, `config/models/search.yaml`
    - `backend/app/cache/`, `backend/app/runtimes/internetsearch/`
    - `backend/app/routing/`, `backend/app/core/settings.py`, `backend/tests/`
  - Evidence:
    - Timestamp: 2026-05-01 01:05 - Completed Slice E infrastructure and internet-search substrate ...
  - Notes:
    - This is substrate/runtime capability for later consumers; user-facing tool behavior, retrieval orchestration, hardware acceleration, and agent runtime behavior were not included.

- Timestamp: 2026-04-30 11:13
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice D durable backend API and desktop application surface.
  - Location:
    - `desktop/`
    - `backend/app/api/`
    - `backend/app/services/`
    - `backend/app/personality/`, `backend/tests/`
  - Evidence:
    - Timestamp: 2026-04-30 11:12 - Completed Slice D durable application surface ...
  - Notes:
    - Consolidates D.2 desktop host and later Slice D surface work; durable desktop/backend shell was added, while tools, agents, and resident shared-stream voice were not included.

- Timestamp: 2026-04-28 06:04
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice C canonical turn/session engine, artifacts, working memory, interruption behavior, and proving host.
  - Location:
    - `backend/app/conversation/`, `backend/app/cognition/`
    - `backend/app/artifacts/`, `backend/app/memory/`
    - `backend/app/personality/`, `backend/app/services/`
    - `scripts/run_jarvis.py`, `backend/tests/`
  - Evidence:
    - Timestamp: 2026-04-28 06:04 - Completed Slice C canonical turn/session engine and proving-host foundation ...
  - Notes:
    - Voice and text share one turn engine; durable desktop/API shell, episodic memory, tools, agents, hardware acceleration, and verified llama.cpp runtime wiring were not included.

- Timestamp: 2026-04-26 19:45
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice B cross-platform voice runtime families, model catalog/acquisition, and runtime validation gates.
  - Location:
    - `backend/app/runtimes/`
    - `backend/app/models/`, `config/models/`
    - `backend/app/routing/`, `config/app/policies.yaml`
    - `scripts/ensure_models.py`, `scripts/validate_backend.py`, `backend/tests/`
  - Evidence:
    - Timestamp: 2026-04-26 19:45 - Completed Slice B cross-platform voice runtime foundation ...
  - Notes:
    - STT, TTS, LLM, and Wake runtime families were device-parameterized and CPU-validated; QNN STT execution, conversation/session, desktop shell, service substrate, tools, and agents were not included.

- Timestamp: 2026-04-24 17:16
  - State: Verified
  - Host class(es): Windows x64 / amd64 and Windows ARM64 / arm64 validated
  - Summary: Established Slice A hardware profiling, provisioning, readiness, validation, and metadata-only QNN foundation.
  - Location:
    - `backend/app/core/`
    - `backend/app/hardware/`
    - `scripts/provision.py`, `scripts/validate_backend.py`, `scripts/bootstrap.py`, `scripts/ensure_models.py`
    - `backend/tests/`
    - `reports/diagnostics/`, `reports/validation/`
  - Evidence:
    - Timestamp: 2026-04-24 17:16 - Completed Slice A hardware, provisioning, readiness, validation, and QNN structural foundation ...
  - Notes:
    - Slice A established hardware/provisioning/readiness authority only; runtime/model/voice execution and durable desktop surface were not included.

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
