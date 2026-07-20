# SYSTEM_INVENTORY.md
> Authoritative capability ledger. This is not a roadmap or config reference.
> Inventory entries must reflect only observable artifacts in this repository:
> files, directories, executable code, configuration, scripts, and explicit UI text.
> Do not include intent, design plans, or inferred behavior.

## Rules
- Write a component entry for a capability or feature group observed in the repository.
- Ordering: Entries are maintained in descending chronological order (newest first, oldest last).
- Append location: New entries must be added at the top directly under `## Inventory Entries`.
- Corrections or clarifications go only below the `## Inventory Appendix` section.
- Each entry must include:

- Timestamp: `YYYY-MM-DD HH:MM`
  - State: Verified, Implemented, or Scaffold
  - Host class(es): validated on
  - Summary: current observable capability
  - Location: current repository locations
  - Evidence: supporting `CHANGE_LOG.md` references or reproducible validation
  - Notes: optional constraints or exclusions

## States
- Verified: validated with evidence working
- Implemented: code exists, not yet validated end-to-end
- Scaffold: boundary exists but no operational implementation is claimed

---

## Inventory Entries

---

## Inventory Appendix

---

## Consolidated Inventory History

- Timestamp: 2026-07-18 08:06
  - State: Verified
  - Host class(es): Linux AMD64 validated on WSL2 with NVIDIA CUDA
  - Summary: Managed Linux AMD64 llama.cpp CUDA build, artifact verification, sidecar serving, and portable-model CPU fallback.
  - Location:
    - `scripts/ensure_models.py`
    - `backend/app/services/local_llm_startup.py`
    - `backend/app/services/local_llm_sidecar.py`
    - `config/models/llm.yaml`
    - `runtimes/llama.cpp/linux-amd64-cuda/`
  - Evidence:
    - Timestamp: 2026-07-18 08:06 - Linux CUDA source-build, sidecar verification, and CPU fallback.
  - Notes:
    - WSL2 is the validation environment, not a separate host class.

- Timestamp: 2026-07-08 13:52
  - State: Verified
  - Host class(es): Windows AMD64; Windows ARM64 where noted
  - Summary: Resident voice operation with PTT and wake modes, persistent desktop mode/voice preferences, live phase/status reporting, diagnostics, endpointing, interruption handling, and recoverable no-speech behavior.
  - Location:
    - `backend/app/services/`
    - `backend/app/conversation/`
    - `backend/app/runtimes/stt/`, `tts/`, and `wake/`
    - `backend/app/api/`
    - `desktop/src/`
    - `config/models/tts.yaml`
  - Evidence:
    - Timestamp: 2026-07-08 13:52 - Resident voice persistence and restoration.
    - Timestamp: 2026-07-07 20:24 - TTS voice selector behavior and persistence.
    - Timestamp: 2026-07-07 07:30 - Resident voice stabilization through AA.7.
  - Notes:
    - openWakeWord is the only wake runtime.

- Timestamp: 2026-07-08 10:59
  - State: Verified
  - Host class(es): Windows AMD64 and Windows ARM64 Qualcomm QNN as applicable
  - Summary: Kokoro ONNX TTS supports CPU plus validated CUDA, DirectML, and Qualcomm QNN execution paths with readiness-driven device selection.
  - Location:
    - `backend/app/runtimes/tts/kokoro_onnx_runtime.py`
    - `backend/app/runtimes/tts/tts_runtime.py`
    - `backend/app/hardware/readiness.py`
    - `config/models/tts.yaml`
  - Evidence:
    - Timestamp: 2026-07-08 10:59 - Qualcomm QNN Kokoro TTS validation.
    - Timestamp: 2026-07-08 07:52 - CUDA and DirectML Kokoro TTS validation.

- Timestamp: 2026-07-04 22:11
  - State: Verified
  - Host class(es): Windows AMD64 and Windows ARM64 as applicable
  - Summary: Backend startup facts, readiness/degraded reporting, session and latest-turn diagnostics, desktop state presentation, and copyable backend startup diagnostics.
  - Location:
    - `backend/app/services/startup_context.py`
    - `backend/app/api/`
    - `scripts/bootstrap.py`
    - `scripts/run_backend.py`
    - `scripts/run_jarvis.py`
    - `scripts/validate_backend.py`
    - `desktop/src/`, `desktop/src-tauri/`
  - Evidence:
    - Timestamp: 2026-07-04 22:11 - Startup, readiness, diagnostics, and desktop-state validation.

- Timestamp: 2026-07-04 16:08
  - State: Verified
  - Host class(es): Windows AMD64 and Windows ARM64
  - Summary: Structured personality profiles compile into prompt policy, generation defaults, behavior traits, style guards, backend-confirmed selection, and provenance-aware prompt rendering.
  - Location:
    - `config/personality/`
    - `backend/app/personality/`
    - `backend/app/cognition/`
    - `backend/app/conversation/`
    - `backend/app/api/routes/personality.py`
    - desktop profile-selection surfaces
  - Evidence:
    - Timestamp: 2026-07-04 22:11 - Personality request-path and runtime-profile validation.
    - Timestamp: 2026-06-12 11:46 - Structured personality policy envelope.

- Timestamp: 2026-07-03 13:19
  - State: Verified
  - Host class(es): Windows AMD64, Windows ARM64, and Linux AMD64 where recorded
  - Summary: Local-first LLM stack with model catalog tiers, managed llama.cpp artifacts and sidecar lifecycle, readiness-aware serve profiles, operator model policy, and Ollama fallback.
  - Location:
    - `config/models/llm.yaml`
    - `backend/app/models/`
    - `backend/app/services/local_llm_startup.py`
    - `backend/app/services/local_llm_sidecar.py`
    - `backend/app/runtimes/llm/`
    - `backend/app/routing/runtime_selector.py`
    - `runtimes/llama.cpp/`
  - Evidence:
    - Timestamp: 2026-07-18 08:06 - Linux CUDA and CPU fallback.
    - Timestamp: 2026-07-03 13:19 - Local LLM tier activation.
    - Timestamp: 2026-06-24 07:48 - Managed llama.cpp artifacts and profiles.
    - Timestamp: 2026-06-18 04:59 - Managed local LLM runtime and sidecar.
  - Notes:
    - No cloud LLM provider capability is present or claimed.

- Timestamp: 2026-06-30 05:44
  - State: Verified
  - Host class(es): Windows ARM64 Qualcomm QNN; Windows AMD64 non-selection validation
  - Summary: ONNX Whisper STT supports CPU and readiness-selected accelerator paths including validated CUDA and Qualcomm QNN execution.
  - Location:
    - `backend/app/runtimes/stt/onnx_whisper_runtime.py`
    - `backend/app/runtimes/stt/stt_runtime.py`
    - `backend/app/hardware/qnn_provider.py`
    - `backend/app/hardware/readiness.py`
    - `config/models/stt.yaml`
  - Evidence:
    - Timestamp: 2026-06-30 05:44 - Qualcomm QNN Whisper STT validation.
    - Timestamp: 2026-05-13 14:57 - Voice acceleration normalization and matrix validation.
  - Notes:
    - The removed secondary `OnnxAsrRuntime` is not part of this capability.

- Timestamp: 2026-06-26 10:51
  - State: Verified
  - Host class(es): Windows AMD64 and Windows ARM64
  - Summary: Shared resident microphone stream, wake/PTT invocation, bounded realtime event coordination, utterance segmentation, barge-in/interruption handling, and canonical turn delegation.
  - Location:
    - `backend/app/services/resident_voice_invocation.py`
    - `backend/app/services/voice_service.py`
    - `backend/app/services/wake_monitor.py`
    - `backend/app/conversation/realtime/`
    - `backend/app/conversation/engine.py`
    - `desktop/src/`
  - Evidence:
    - Timestamp: 2026-06-26 10:51 - Resident shared-stream voice validation.
    - Timestamp: 2026-06-13 18:21 - Realtime session boundary.

- Timestamp: 2026-06-15 08:14
  - State: Verified
  - Host class(es): Windows AMD64 and Windows ARM64
  - Summary: Default-disabled agent policy, validated agent spec catalog, append-only local ledger, and read-only status/trace API.
  - Location:
    - `backend/app/agents/ledger.py`
    - `backend/app/agents/policy.py`
    - `backend/app/agents/specs.py`
    - `backend/app/api/routes/agents.py`
    - `backend/app/api/schemas/agents.py`
    - `config/agents/specs/`
  - Evidence:
    - Timestamp: 2026-06-15 08:14 - Disabled agent policy/spec and read-only trace boundary.
  - Notes:
    - No agent creator, planner, executor, critic, curator, learner, tools, model calls, or autonomous execution is present.

- Timestamp: 2026-06-14 10:32
  - State: Verified
  - Host class(es): Windows AMD64
  - Summary: Session lifecycle, deterministic timelines, bounded continuity packets, working-memory context, persisted turn/session artifacts, and conservative closeout metadata.
  - Location:
    - `backend/app/conversation/`
    - `backend/app/artifacts/`
    - `backend/app/memory/working.py`
    - `backend/app/services/session_service.py`
  - Evidence:
    - Timestamp: 2026-06-14 10:32 - Conversation continuity and session memory boundary.

- Timestamp: 2026-05-30 06:58
  - State: Verified
  - Host class(es): Windows AMD64 and Windows ARM64
  - Summary: Desktop operator shell with readiness, degraded-state, session, resident voice, wake, personality, settings, diagnostics, and conversation surfaces.
  - Location:
    - `desktop/src/`
    - `desktop/src-tauri/`
    - `backend/app/api/`
    - `backend/app/services/`
  - Evidence:
    - Timestamp: 2026-07-04 22:11 - Desktop startup/readiness/diagnostics polish.
    - Timestamp: 2026-05-30 06:58 - Operator desktop/settings and readiness.
    - Timestamp: 2026-04-30 11:12 - Durable desktop/backend application surface.

- Timestamp: 2026-05-13 14:57
  - State: Verified
  - Host class(es): Windows AMD64 and Windows ARM64
  - Summary: Hardware profiling, dependency preflight, device readiness, provisioning-extra resolution, and host-gated acceleration validation for supported runtime families.
  - Location:
    - `backend/app/hardware/`
    - `backend/tests/runtime/acceleration_matrix/`
    - `scripts/provision.py`
    - `pyproject.toml`
    - `config/hardware/notes.md`
  - Evidence:
    - Timestamp: 2026-05-13 14:57 - Acceleration sequence normalization and live matrix extension.
    - Timestamp: 2026-05-13 09:10 - Voice acceleration matrix and full-turn gates.

- Timestamp: 2026-05-02 22:10
  - State: Verified
  - Host class(es): Windows AMD64, Windows ARM64, and Linux ARM64 where recorded
  - Summary: Disk-backed episodic and SQLite semantic memory, hybrid retrieval, bounded prompt-context injection, Redis retrieval-cache acceleration, transactional semantic writes, and atomic artifact persistence.
  - Location:
    - `backend/app/memory/`
    - `backend/app/cache/`
    - `backend/app/artifacts/`
    - `backend/app/conversation/engine.py`
    - `backend/app/cognition/prompt_assembler.py`
  - Evidence:
    - Timestamp: 2026-07-17 06:10 - Retrieval/cache and persistence hardening.
    - Timestamp: 2026-05-02 22:10 - Episodic memory and retrieval substrate.
  - Notes:
    - Redis is acceleration, not durable memory authority.

- Timestamp: 2026-05-01 01:05
  - State: Verified
  - Host class(es): Windows AMD64 and Windows ARM64
  - Summary: Local Redis and SearXNG service composition plus fail-closed SearXNG, DDGS, and Tavily internet-search runtime providers.
  - Location:
    - `docker-compose.yml`
    - `config/search/`
    - `backend/app/cache/`
    - `backend/app/runtimes/internetsearch/`
    - `backend/app/core/settings.py`
  - Evidence:
    - Timestamp: 2026-05-01 01:05 - Infrastructure and internet-search runtime substrate.
  - Notes:
    - These providers have no normal conversation or agent invocation path.

- Timestamp: 2026-04-30 11:12
  - State: Verified
  - Host class(es): Windows AMD64 and Windows ARM64
  - Summary: FastAPI application with health, readiness, diagnostics, configuration, session, task, status, personality, and agent status/trace routes backed by explicit application services.
  - Location:
    - `backend/app/api/`
    - `backend/app/services/`
    - `backend/app/conversation/`
    - `backend/app/personality/`
    - `desktop/`
  - Evidence:
    - Timestamp: 2026-04-30 11:12 - Durable backend API and desktop application surface.
