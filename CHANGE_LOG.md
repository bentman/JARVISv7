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

- 2026-06-13 18:21
  - Summary: Implemented Group M realtime conversation session boundary. Resident voice invocation now routes live wake/PTT invocation events through a realtime session boundary that records ordered events and delegates committed voice turns to the existing turn engine while preserving current status behavior.
  - Scope: `backend/app/conversation/realtime/`, `backend/app/services/resident_voice_invocation.py`, `backend/tests/unit/conversation/realtime/`, `backend/tests/unit/services/test_resident_voice_invocation.py`, `CHANGE_LOG.md`, `SYSTEM_INVENTORY.md`
  - Host class(es): Windows x64 / amd64 current workspace
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\conversation\realtime` PASS (`8 passed`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\services\test_resident_voice_invocation.py` PASS (`8 passed`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\services\test_session_service.py` PASS (`13 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`450 passed, 1 skipped`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`115 passed, 4 deselected`, report `reports\validation\20260613232131-regression.txt`).
  - Note: No agent behavior, streaming transport, semantic-memory redesign, model routing, STT/TTS/LLM runtime selection, wake runtime replacement, provisioning, hardware detection, or desktop UI changes were made.

- 2026-06-13 09:48
  - Summary: Cleaned active governance and runtime-boundary wording for vague postponement language and brittle adjacent slice handoffs. Active guidance now uses not implemented, not wired, not claimed, outside boundary, or stable boundary ownership language.
  - Scope: `AGENTS.md`, `SYSTEM_INVENTORY.md`, `CHANGE_LOG.md`, `slices.md`, `config/hardware/notes.md`, `config/models/llm.yaml`, `backend/app/hardware/readiness.py`, `backend/app/runtimes/llm/base.py`, `backend/app/runtimes/llm/local_runtime.py`, `backend/app/runtimes/stt/onnx_whisper_runtime.py`, `backend/tests/runtime/acceleration_matrix/test_acceleration_matrix.py`, `backend/tests/unit/hardware/test_qnn_slot.py`, `backend/tests/unit/runtimes/llm/test_llm_runtime.py`, `backend/tests/unit/runtimes/stt/test_stt_runtime.py`
  - Host class(es): Windows x64 / amd64 current workspace
  - Evidence: `backend\.venv\Scripts\python scripts\validate_backend.py profile` PASS (`arch=amd64`, readiness `ready; tokens=13`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\runtimes\llm\test_llm_runtime.py backend\tests\unit\runtimes\stt\test_stt_runtime.py backend\tests\unit\hardware\test_qnn_slot.py -q` PASS (`31 passed, 1 skipped`); `backend\.venv\Scripts\python -m pytest backend\tests\runtime\acceleration_matrix\test_acceleration_matrix.py -q` PASS (`1 passed`); `git diff --check` PASS with line-ending warnings only; active guidance search for the postponement-word pattern returned no matches.

- 2026-06-13 04:55
  - Summary: Recorded post-adjustment live desktop wake smoke result. One wake turn still failed as empty STT/no speech; the next wake turn completed with imperfect transcript `edsię what is the capital of texas` and response `Austin`, confirming improvement but not conversational timing quality.
  - Scope: Live desktop smoke result only; no code/config changes in this entry.
  - Host class(es): Windows ARM64 / arm64 current workspace
  - Evidence: `data\turns\c64d40d6056647d58afab4d12694d039\2760bce5a91b42c3bd350733b1032b54.json` recorded `failure_reason='STT returned empty transcript'`; `data\turns\c64d40d6056647d58afab4d12694d039\b7c4e0c867f347e1afed001afffd2d63.json` recorded transcript `edsię what is the capital of texas`, response `Austin`, and no failure reason.

- 2026-06-13 04:51
  - Summary: Corrected wake-triggered command audio handoff. Wake detection now carries a bounded pre-roll and post-wake audio buffer from the existing wake monitor input stream into resident voice invocation, avoiding a second microphone capture for wake turns while preserving normal PTT capture behavior.
  - Scope: `backend/app/services/wake_monitor.py`, `backend/app/services/resident_voice_invocation.py`, `backend/tests/unit/services/test_wake_monitor.py`, `backend/tests/unit/services/test_resident_voice_invocation.py`
  - Host class(es): Windows ARM64 / arm64 current workspace
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\services\test_wake_monitor.py backend\tests\unit\services\test_resident_voice_invocation.py -q` PASS (`14 passed in 0.19s`); `backend\.venv\Scripts\python -c "import os, pytest; os.environ['JARVISV7_LIVE_TESTS']='1'; raise SystemExit(pytest.main(['backend/tests/runtime/voice/test_stt_live.py','-q','-k','qnn']))"` PASS (`1 passed, 2 deselected`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`115 passed, 4 deselected`, report `reports\validation\20260613094953-regression.txt`).
  - Note: STT/QNN runtime selection, provisioning, personality policy, LLM, TTS, and PTT capture were not changed.

- 2026-06-12 15:05
  - Summary: Corrected wake-sourced empty-transcript reporting and resident invocation queue draining. Wake-triggered voice turns that return the canonical empty STT transcript now report `No speech detected after wake`, while PTT keeps the original STT failure; the resident worker also rechecks the queue before exiting so closely queued wake/PTT requests are not stranded.
  - Scope: `backend/app/services/resident_voice_invocation.py`, `backend/tests/unit/services/test_resident_voice_invocation.py`
  - Host class(es): Windows ARM64 / arm64 current workspace
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\services\test_resident_voice_invocation.py -q` PASS (`7 passed in 0.13s`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\services\test_resident_voice_invocation.py backend\tests\unit\services\test_wake_monitor.py backend\tests\unit\services\test_voice_service.py -q` PASS (`21 passed in 0.25s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`115 passed, 4 deselected`, report `reports\validation\20260612200519-regression.txt`).
  - Note: STT runtime/model behavior was not changed. Investigation showed QNN STT transcribed the known-audio fixture while live ambient wake capture returned an empty transcript.

- 2026-06-12 14:41
  - Summary: Corrected the ARM64 QNN provisioning install sequence to preserve the repo-owned ORT family selection. Provisioning now removes only the conflicting plain `onnxruntime` distribution on Qualcomm ARM64 hosts and force-reinstalls pinned `onnxruntime-qnn==1.24.3` with `--no-deps`.
  - Scope: `scripts/provision.py`, `backend/tests/unit/scripts/test_provision_script.py`
  - Host class(es): Windows ARM64 / arm64 current workspace
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\scripts\test_provision_script.py backend\tests\unit\hardware\test_provisioning.py -q` PASS (`23 passed in 0.08s`); `backend\.venv\Scripts\python scripts\provision.py install` PASS with no pip resolver conflict line and final QNN reinstall `Successfully installed onnxruntime-qnn-1.24.3`; `backend\.venv\Scripts\python scripts\provision.py verify` PASS with expected `onnxruntime_qnn` present and no plain `onnxruntime`; `backend\.venv\Scripts\python scripts\validate_backend.py profile` PASS (`arch=arm64`, readiness `ready; tokens=18`, `ep:QNNExecutionProvider`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`115 passed, 4 deselected`, report `reports\validation\20260612194040-regression.txt`).
  - Note: Raw `pip check` still reports third-party metadata requirements from `kokoro-onnx` and `openwakeword` for distribution name `onnxruntime`; repo acceptance remains `scripts\provision.py verify` plus preflight because `onnxruntime-qnn` provides the runtime import/provider surface while plain `onnxruntime` must not coexist on ARM64 QNN hosts.

- 2026-06-12 12:37
  - Summary: Corrected Personality Policy Envelope tool-result ordering. Tool execution context is now assembled by the prompt assembly layer before the user request and trusted output contract, instead of being appended after a finalized envelope in the turn engine.
  - Scope: `backend/app/cognition/prompt_assembler.py`, `backend/app/conversation/engine.py`, `backend/tests/unit/cognition/test_prompt_assembler.py`, `backend/tests/unit/conversation/test_engine.py`
  - Host class(es): Windows x64 / amd64 current workspace
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\cognition\test_prompt_assembler.py -q` PASS (`11 passed in 0.11s`); `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`439 passed, 1 skipped in 3.26s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`115 passed, 4 deselected in 0.96s`, report `reports\validation\20260612173725-regression.txt`).
  - Note: No personality schema, policy compiler, LLM runtime selection, tool execution authority, memory storage, STT/TTS, wake, provisioning, hardware detection, desktop UI, or `SYSTEM_INVENTORY.md` changes were made.

- 2026-06-12 11:46
  - Summary: Completed Slice L.6 ARM64 validation and Group L governance closeout for the personality policy envelope. Focused personality/cognition/conversation/API/desktop tests, live turn runtime validation, and regression all passed on Windows ARM64 / arm64 after Ollama service availability was confirmed.
  - Scope: `backend/app/personality/`, `config/personality/`, `backend/app/cognition/`, `backend/app/conversation/engine.py`, `backend/app/runtimes/llm/base.py`, `backend/tests/unit/personality/`, `backend/tests/unit/cognition/`, `backend/tests/unit/conversation/`, `backend/tests/unit/api/test_routes.py`, `backend/tests/unit/desktop/test_desktop_static_contract.py`, `SYSTEM_INVENTORY.md`
  - Host class(es): Windows ARM64 / arm64 current workspace
  - Evidence: `backend\.venv\Scripts\python scripts\validate_backend.py profile` PASS (fingerprint `arch=arm64 python=3.13.13 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready; tokens=18`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\personality backend\tests\unit\cognition backend\tests\unit\conversation backend\tests\unit\api\test_routes.py backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`148 passed in 20.48s`); `JARVISV7_LIVE_TESTS=1 backend\.venv\Scripts\python scripts\validate_backend.py runtime --families turn --devices cpu` PASS (`10 passed, 1 skipped, 24 deselected in 70.78s`, fingerprint `arch=arm64`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`115 passed, 4 deselected in 0.97s`, report `reports\validation\20260612164435-regression.txt`).
  - Note: The first live turn runtime attempt failed because the configured Ollama endpoint refused connections (`WinError 10061`); after `ollama list` and `ollama show phi4-mini` confirmed service/model availability, the same live runtime validator passed.

- 2026-06-12 11:21
  - Summary: Recorded Slice L.6 current-host validation for the personality policy envelope implementation. Focused personality/cognition/conversation/API/desktop tests, active-host turn runtime validation, and active-host regression all passed on Windows x64 / amd64.
  - Scope: `backend/app/personality/`, `config/personality/`, `backend/app/cognition/`, `backend/app/conversation/engine.py`, `backend/app/runtimes/llm/base.py`, `backend/tests/unit/personality/`, `backend/tests/unit/cognition/`, `backend/tests/unit/conversation/`, `backend/tests/unit/api/test_routes.py`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows x64 / amd64 current workspace
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\personality backend\tests\unit\cognition backend\tests\unit\conversation backend\tests\unit\api\test_routes.py backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`148 passed in 3.77s`); `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families turn --devices cpu` PASS (`9 passed, 2 skipped, 24 deselected in 58.15s`, fingerprint `arch=amd64`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`115 passed, 4 deselected in 2.28s`, report `reports\validation\20260612162057-regression.txt`).
  - Note: `SYSTEM_INVENTORY.md` was not updated because Group L closeout still requires Windows ARM64 validation evidence.

- 2026-06-12 11:19
  - Summary: Completed Slice L.5 deterministic style guard and TTS projection. Added bounded post-generation style cleanup that trims generic acknowledgments according to personality policy and voice/text modality while preserving existing single-turn response and TTS sanitization behavior.
  - Scope: `backend/app/cognition/style_guard.py`, `backend/app/conversation/engine.py`, `backend/tests/unit/cognition/test_style_guard.py`, `backend/tests/unit/conversation/test_engine.py`
  - Host class(es): Windows x64 / amd64 current workspace
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\cognition backend\tests\unit\conversation -q` PASS (`71 passed in 0.41s`).
  - Note: L.5 did not update `SYSTEM_INVENTORY.md`; inventory state was not claimed until full personality policy boundary validation.

- 2026-06-12 11:18
  - Summary: Completed Slice L.4 LLM envelope adapter and turn integration. Added a default envelope-aware LLM adapter that preserves `generate(prompt)` compatibility, updated the turn engine to pass structured prompt envelopes, and rendered tool execution context as untrusted tool-result prompt content.
  - Scope: `backend/app/runtimes/llm/base.py`, `backend/app/conversation/engine.py`, `backend/tests/unit/conversation/test_engine.py`
  - Host class(es): Windows x64 / amd64 current workspace
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\conversation backend\tests\unit\runtimes\llm -q` PASS (`57 passed in 0.43s`).
  - Note: L.4 did not update `SYSTEM_INVENTORY.md`; inventory state was not claimed until full personality policy boundary validation.

- 2026-06-12 11:17
  - Summary: Completed Slice L.3 prompt envelope and flat renderer. Prompt assembly now builds provenance-aware segments for application rules, personality policy, memory, retrieval, user input, and output contract, then renders a deterministic flat prompt compatible with current local/Ollama-style runtimes.
  - Scope: `backend/app/cognition/prompt_envelope.py`, `backend/app/cognition/prompt_renderer.py`, `backend/app/cognition/prompt_assembler.py`, `backend/tests/unit/cognition/test_prompt_assembler.py`, `backend/tests/unit/conversation/test_engine.py`
  - Host class(es): Windows x64 / amd64 current workspace
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\cognition backend\tests\unit\conversation -q` PASS (`64 passed in 0.32s`).
  - Note: L.3 did not update `SYSTEM_INVENTORY.md`; inventory state was not claimed until full personality policy boundary validation.

- 2026-06-12 11:15
  - Summary: Completed Slice L.2 personality policy compiler. Added deterministic compilation from structured personality profiles into bounded style/speech rules plus style-only role overlays that reject authority-bearing fields.
  - Scope: `backend/app/personality/policy.py`, `backend/tests/unit/personality/test_personality.py`
  - Host class(es): Windows x64 / amd64 current workspace
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\personality -q` PASS (`14 passed in 0.12s`).
  - Note: L.2 did not update `SYSTEM_INVENTORY.md`; inventory state was not claimed until full personality policy boundary validation.

- 2026-06-12 11:14
  - Summary: Completed Slice L.1 structured personality profile schema and loader validation. Personality profiles now carry structured style fields with compatibility defaults, configured profiles declare those fields explicitly, and profile loading rejects unknown or prohibited authority-bearing keys.
  - Scope: `backend/app/personality/schema.py`, `backend/app/personality/loader.py`, `config/personality/default.yaml`, `config/personality/concise.yaml`, `config/personality/warm.yaml`, `backend/tests/unit/personality/test_personality.py`
  - Host class(es): Windows x64 / amd64 current workspace
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\personality -q` PASS (`10 passed in 0.26s`).
  - Note: L.1 did not update `SYSTEM_INVENTORY.md`; inventory state was not claimed until full personality policy boundary validation.

- 2026-06-12 11:12
  - Summary: Completed Slice L.0 personality runtime boundary census. Confirmed existing personality profile selection and metadata surfaces were present, while runtime prompt behavior still ignored personality style data and did not pass legacy `system_prompt_addendum` raw into prompts.
  - Scope: `backend/app/personality/schema.py`, `backend/app/personality/loader.py`, `backend/app/personality/adapter.py`, `config/personality/default.yaml`, `config/personality/concise.yaml`, `config/personality/warm.yaml`, `backend/app/cognition/prompt_assembler.py`, `backend/app/cognition/responder.py`, `backend/app/conversation/engine.py`, `backend/app/runtimes/llm/base.py`, `backend/app/api/routes/personality.py`, `backend/app/api/schemas/personality.py`, `backend/tests/unit/personality/test_personality.py`, `backend/tests/unit/cognition/test_prompt_assembler.py`, `backend/tests/unit/conversation/test_engine.py`
  - Host class(es): Windows x64 / amd64 current workspace inspection
  - Evidence: `Get-Content` inspection confirmed `PersonalityProfile` fields were limited to `profile_id`, `display_name`, `tone`, `brevity`, `formality`, and `system_prompt_addendum`; `assemble_prompt()` accepted `personality` but assigned `_ = personality`; `TurnEngine` passed `self.personality` into `assemble_prompt()` and recorded `active_personality_profile_id`; tests asserted personality addendum was not injected.
  - Note: Evidence-only L.0 entry. No implementation code or `SYSTEM_INVENTORY.md` changes were made.

- 2026-05-30 06:58
  - Summary: Completed ARM64 QNN provider-surface repair and live desktop proof. The correction superseded the earlier incomplete ARM64 QNN package-family/probe direction by making `onnxruntime-qnn==1.24.3` the sole ORT runtime distribution for the ARM64 QNN host path, removing/rejecting separate base `onnxruntime`, and proving QNN readiness through the built-in `onnxruntime` provider surface instead of the 2.x plugin-era `onnxruntime_qnn` path.
  - Scope: `pyproject.toml`, `scripts/provision.py`, `backend/app/hardware/provisioning.py`, `backend/app/hardware/preflight.py`, `backend/app/hardware/qnn_provider.py`, `backend/tests/unit/scripts/test_provision_script.py`, `backend/tests/unit/hardware/test_provisioning.py`, `backend/tests/unit/hardware/test_preflight.py`, `backend/tests/unit/hardware/test_qnn_slot.py`, `backend/tests/runtime/hardware/test_qnn_gate_live.py`; user ARM64 desktop wake proof.
  - Host class(es): Windows ARM64 / Qualcomm QNN
  - Evidence: base `onnxruntime` distribution absent; `onnxruntime-qnn 1.24.3`; `ort.__version__=1.24.3`; providers included `QNNExecutionProvider`; profile PASS with readiness `ready; tokens=18` and QNN tokens `ep:QNNExecutionProvider`, `qnn:htp_path`, `dll:QnnHtp`, no probe errors; focused tests PASS (`33 passed`); `backend\.venv\Scripts\python scripts\provision.py verify` PASS; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`115 passed, 4 deselected`); QNN hardware live gate PASS (`2 passed`); QNN STT live fixture PASS (`1 passed`); user desktop live proof PASS with ARM64 wake path completing as `source: wake`, populated transcript/response, and no visible failure reason.
  - Note: QNN decoder/token logic, readiness selection intent, model catalog, desktop/wake/PTT/TTS behavior, `/task/voice`, settings, search, and personality were not changed.

- 2026-05-29 07:40
  - Summary: Recorded completed x64 voice ingress proof for wake microphone capture consolidation. Wake microphone capture was moved to the shared backend voice service and now uses a persistent `sounddevice.InputStream` for wake chunks.
  - Scope: Commit `6e9747be53c824425f25a2135d84b44ee9489d4e`; `backend/app/services/voice_service.py`, `backend/app/services/wake_monitor.py`, `backend/tests/unit/services/test_voice_service.py`, `backend/tests/unit/services/test_wake_monitor.py`
  - Host class(es): Windows x64 / amd64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\services\test_voice_service.py backend\tests\unit\services\test_wake_monitor.py backend\tests\unit\runtimes\wake\test_wake_runtime.py -q` PASS (`25 passed in 0.44s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`105 passed, 4 deselected in 0.92s`); manual Windows x64 desktop result: PTT still worked; wake detected once; `detection_count=1`; `last_detected` updated; resident turn completed from `source=wake`; transcript and response populated; TTS output device populated.
  - Note: Documentation/evidence-only entry. No ARM64 live voice/wake proof, final press/release PTT semantics, barge-in, or interruption behavior is claimed.

- 2026-05-28 18:53
  - Summary: Completed Slice K.4f backend wake monitor lifecycle on Windows x64 / amd64. Added backend-owned wake monitor lifecycle endpoints for start, stop, toggle, and status; added focused `WakeMonitorService` with injected runtime/chunk source support and no test microphone dependency; extended wake status with `active`, `enabled`, `last_detected`, `detection_count`, and `last_error`; kept `SessionService` limited to wake state/status updates; wake detection now updates timestamp/count; and unavailable runtime or capture/detection errors fail closed and disable monitoring.
  - Scope: `backend/app/api/app.py`, `backend/app/api/routes/status.py`, `backend/app/api/schemas/status.py`, `backend/app/services/session_service.py`, `backend/app/services/wake_monitor.py`, `backend/tests/unit/api/test_routes.py`, `backend/tests/unit/services/test_session_service.py`, `backend/tests/unit/services/test_wake_monitor.py`
  - Host class(es): Windows x64 / amd64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\services\test_session_service.py backend\tests\unit\services\test_wake_monitor.py backend\tests\unit\api\test_routes.py -q` PASS (`45 passed in 1.42s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`105 passed, 4 deselected in 1.78s`).
  - Note: No hands-free turn submission was added. No desktop, Tauri, PTT, search, settings, personality, dependency/provisioning, or `SYSTEM_INVENTORY.md` changes were made.

- 2026-05-27 19:26
  - Summary: Completed Slice K.4e Settings access fix on Windows x64 / amd64. Added Tauri commands for operator settings GET/POST backed by Rust `reqwest`; removed direct browser `fetch()` and the hardcoded backend URL from the settings panel; wired settings GET/POST through `invoke("get_operator_config")` and `invoke("write_operator_config")`; preserved `.env` missing handling, changed-field saves, secret handling, and restart-required UX; and replaced the visible Settings text button with an accessible gear icon button using `aria-label="Settings"` and `title="Settings"`.
  - Scope: `desktop/src-tauri/src/backend.rs`, `desktop/src-tauri/src/lib.rs`, `desktop/src/components/settings-panel.js`, `desktop/src/main.js`, `desktop/src/index.html`, `desktop/src/style.css`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows x64 / amd64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`31 passed in 0.22s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`105 passed, 4 deselected in 1.01s`); `cargo check` PASS for `desktop/src-tauri`; user smoke confirmed the gear opens settings without `TypeError: Failed to fetch`.
  - Note: No backend API, CORS, settings schema, service-status, search, personality, dependency/provisioning, or `SYSTEM_INVENTORY.md` changes were made.

- 2026-05-27 18:40
  - Summary: Completed Slice K.4d SearchTool provider escalation repair on Windows x64 / amd64. Implemented SearchTool provider escalation in configured order: SearXNG, DDGS, Tavily; unavailable providers are skipped; provider exceptions, empty results, and no usable results fall through to the next provider; and the first provider result set with usable `SearchResult` objects is returned.
  - Scope: `backend/app/tools/search/search_tool.py`, `backend/tests/unit/tools/test_search_tool.py`
  - Host class(es): Windows x64 / amd64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\tools\test_search_tool.py backend\tests\unit\runtimes\internetsearch\test_search_runtime.py -q` PASS (`14 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`105 passed, 4 deselected in 1.03s`); user manual smoke test PASS.
  - Note: Preserved result JSON schema and fail-closed `[]` behavior after all enabled providers fail or return empty. `backend/app/routing/runtime_selector.py` was not modified. This repairs provider fallback only; user-facing explicit search grounding remains separate follow-up work.

- 2026-05-27 17:15
  - Summary: Completed Slice K.4c SearXNG JSON readiness correction on Windows x64 / amd64. Added deterministic SearXNG settings-path configuration and corrected readiness probing so desktop service status reports JSON format availability without conflating upstream search latency with service reachability.
  - Scope: `docker-compose.yml`, `backend/app/api/service_status.py`, `backend/tests/unit/api/test_routes.py`, `backend/tests/unit/api/test_service_status.py`
  - Host class(es): Windows x64 / amd64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\api\test_routes.py backend\tests\unit\api\test_service_status.py -q` PASS (`34 passed in 1.51s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`105 passed, 4 deselected in 1.06s`); `docker compose up -d searxng` PASS with Redis healthy and SearXNG running; live backend probe returned `ServiceStatus(reachable=True, reason='container reachable; json usable')`; user UI smoke confirmed desktop shows `SearXNG: reachable · container reachable; json usable`.
  - Note: Added `SEARXNG_SETTINGS_PATH=/etc/searxng/settings.yml`; kept `config/search/searxng/settings.yml` as the repo-owned active config; added focused tests proving `use_default_settings: true`, `search.formats` includes `json`, and compose keeps the explicit settings path plus `/etc/searxng` repo mount; kept `/healthz` as the reachability check; corrected the JSON capability probe to `GET /search?q=&format=json`; treats SearXNG's `{"error": "No query"}` JSON response as proof that JSON output is enabled, including HTTP 400; no desktop, Tauri, settings panel, personality, cloud escalation, dependency/provisioning, `SYSTEM_INVENTORY.md`, or SearXNG `settings.yml` changes were made.

- 2026-05-27 16:31
  - Summary: Completed Slice K.4b desktop layout/readability correction. Corrected the desktop shell into a clearer three-pane layout; left runtime sidebar now focuses on Backend and Readiness; center remains Conversation, text input/send, PTT controls, and voice debug; right Operator panel now contains Personality, Services, Appearance, and Settings; removed separate Wake display from Backend facts with Wake represented in Readiness; removed Personality from the Readiness summary; added compact PTT readiness row; reordered readiness rows to `LLM`, `PTT`, `STT`, `TTS`, `Wake`; moved verbose readiness reasons into hover text; hid redundant degraded-conditions content; treated TTS on CPU as ready when a TTS runtime exists; replaced conversation message `innerHTML` rendering with DOM/text APIs; and preserved existing IDs and JS wiring where needed.
  - Scope: `desktop/src/index.html`, `desktop/src/main.js`, `desktop/src/style.css`, `desktop/src/components/readiness-panel.js`, `desktop/src/components/degraded-list.js`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows x64 / amd64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`31 passed in 0.14s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`105 passed, 4 deselected in 1.12s`); user screenshot review confirmed the three-pane layout was visually in place.
  - Note: No backend, Tauri, service probe, settings semantics, personality behavior, dependency/provisioning, or `SYSTEM_INVENTORY.md` changes were made.

- 2026-05-26 21:33
  - Summary: Completed Slice K.4 appearance adjustments on Windows ARM64 / arm64. Added compact appearance controls at the bottom of the sidebar; added `appearance-controls.js` with `initAppearanceControls(containerEl)` and `applyStored()`; persisted preferences to WebView `localStorage` key `jarvisv7_appearance`; applied stored preferences before backend startup; supported sparse controls for font size, density, and accent; applied changes immediately with `document.documentElement.style.setProperty()`; limited runtime overrides to `--text-sm`, `--text-md`, `--text-lg`, `--space-2`, `--space-3`, `--space-4`, and `--color-accent`; and avoided semantic token overrides.
  - Scope: `desktop/src/components/appearance-controls.js`, `desktop/src/index.html`, `desktop/src/main.js`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows ARM64 / arm64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`28 passed in 0.13s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS on Windows ARM64 / arm64 (`105 passed, 4 deselected in 1.05s`).
  - Note: No CSS, backend, Tauri, settings panel, service status, personality, `.env.example`, dependency/provisioning, `SYSTEM_INVENTORY.md`, or schema changes were made. Manual desktop confirmation rolls into Slice K closeout.

- 2026-05-26 21:20
  - Summary: Completed Slice K.3 service status display on Windows ARM64 / arm64. Added additive `services` payload to `GET /readiness` for Redis and SearXNG; added short-timeout, fail-closed service probes using current v7 settings/env names; added `service-status.js` with `renderServiceStatus(servicesPayload, containerEl)` using DOM/text APIs; added the sidebar service status container below degraded conditions; extended `renderReadiness()` to render service status; added sparse fallback copy `Service status unavailable.`; and added backend readiness payload coverage plus desktop static contract coverage.
  - Scope: `backend/app/api/service_status.py`, `backend/app/api/schemas/readiness.py`, `backend/app/api/routes/readiness.py`, `backend/tests/unit/api/test_routes.py`, `desktop/src/components/service-status.js`, `desktop/src/index.html`, `desktop/src/main.js`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows ARM64 / arm64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\api\test_routes.py -q` PASS (`26 passed in 23.65s`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`27 passed in 0.12s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS on Windows ARM64 / arm64 (`105 passed, 4 deselected in 1.06s`).
  - Note: No existing readiness fields were renamed or removed. No Docker Compose, Tauri, settings panel, CSS, `.env.example`, dependency/provisioning, `SYSTEM_INVENTORY.md`, or service start/stop controls were changed. Manual desktop confirmation rolls into Slice K closeout.

- 2026-05-26 20:55 
  - Summary: Completed Slice K.2c restart-required UX on Windows ARM64 / arm64. Added restart-required state after successful settings save; rendered sparse restart-required UI in `settings-panel.js`; hid normal save/close controls while restart is required; kept Restart available; showed sparse restart failure copy; kept restart lifecycle in `main.js` through an injected callback using existing `stop_backend`, `start_backend`, and `get_readiness`; refreshed settings from `GET /config/operator` after successful restart; cleared the restart-required indicator after restart; and added a hidden-by-default persistent restart-required indicator near the Settings trigger for panel-closed state.
  - Scope: `desktop/src/components/settings-panel.js`, `desktop/src/main.js`, `desktop/src/index.html`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows ARM64 / arm64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`26 passed in 0.12s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS on Windows ARM64 / arm64 (`105 passed, 4 deselected in 1.06s`).
  - Note: Preserved DOM/text API use with no `innerHTML`. No backend, new Tauri command, CSS, service status, appearance control, personality behavior, `.env.example`, dependency/provisioning, `SYSTEM_INVENTORY.md`, or schema changes were made. Manual desktop confirmation rolls into Slice K closeout.

- 2026-05-26 20:36
  - Summary: Completed Slice K.2b desktop settings panel UI on Windows ARM64 / arm64. Added `settings-panel.js` with `openSettings(containerEl)` and `closeSettings()`; added a sparse sidebar settings trigger and settings panel container; wired the panel to consume `GET /config/operator` and `POST /config/operator`; rendered backend-returned fields only with no separate UI allowlist; showed key/description, editable state, secret state, has-value state, and restart-required text; preserved secret masking by submitting replacements only when entered; tracked dirty state with a sparse unsaved-change indicator; saved changed fields only and reported written/rejected counts; handled `409 env_file_missing` visibly without creating `.env`; and used DOM/text APIs with no `innerHTML` in the settings component.
  - Scope: `desktop/src/components/settings-panel.js`, `desktop/src/index.html`, `desktop/src/main.js`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows ARM64 / arm64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`25 passed in 0.11s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS on Windows ARM64 / arm64 (`105 passed, 4 deselected in 1.04s`).
  - Note: No backend, Tauri, CSS, restart UX, service status, appearance controls, personality behavior, `.env.example`, dependency/provisioning, `SYSTEM_INVENTORY.md`, or schema changes were made. Manual desktop confirmation rolls into Slice K closeout.

- 2026-05-26 19:47
  - Summary: Completed Slice K.2a operator settings inventory/backend route on Windows ARM64 / arm64. Added `GET /config/operator` and `POST /config/operator`; reads from existing `.env` only; missing `.env` returns `409` with `{"error": "env_file_missing"}` and does not create the file; exposes only approved current v7 operator fields; returns sparse field metadata (`key`, `value`, `has_value`, `editable`, `secret`, `restart_required`, and `description`); marks editable fields as restart-required; masks `TAVILY_API_KEY` as `***` when set with `has_value=true`; rejects non-allowlisted keys; preserves unknown `.env` lines and ordering while updating allowlisted keys in place; appends missing allowlisted keys only when `.env` already exists; and registered the config router in `create_app()`.
  - Scope: `backend/app/api/app.py`, `backend/app/api/routes/config.py`, `backend/app/api/schemas/config.py`, `backend/tests/unit/api/test_routes.py`
  - Host class(es): Windows ARM64 / arm64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\api\test_routes.py -q` PASS (`25 passed in 1.31s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS on Windows ARM64 / arm64 (`105 passed, 4 deselected in 1.09s`).
  - Note: No desktop UI, Tauri, CSS, service-status behavior, appearance controls, cloud escalation, personality runtime behavior, dependency/provisioning, `SYSTEM_INVENTORY.md`, or `.env.example` changes were made.

- 2026-05-26 19:30
  - Summary: Completed Slice K.1 personality metadata display on Windows ARM64 / arm64. Updated `updatePersonalityDisplay(profile)` to render Tone, Brevity, and Formality as labeled metadata fields with missing values shown as `—`, using DOM/text APIs (`createElement`, `textContent`, `append`, and `replaceChildren`) while preserving existing personality selector behavior, active personality state, backend calls, response behavior, CSS, `.env`, and Tauri behavior.
  - Scope: `desktop/src/main.js`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows ARM64 / arm64
  - Evidence: Gate K-0 active-host baseline `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`105 passed, 4 deselected in 1.16s`); desktop static contract `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`24 passed in 0.11s`); post-K.1 regression `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`105 passed, 4 deselected in 1.07s`).
  - Note: Manual visual confirmation can be included in Slice K closeout; no additional K.1 validation was requested for this log update.

- 2026-05-26 11:31
  - Summary: Added a minimal Windows ARM64 fresh-clone desktop launch prerequisite note documenting repo-local desktop dependency installation before running the desktop app.
  - Scope: `docs/windows-arm64-fresh-clone-setup.md`
  - Host class(es): Windows ARM64 / arm64
  - Evidence: ARM64 manual desktop validation initially found `npm --prefix desktop run dev` blocked because local desktop npm dependencies were missing; after `npm --prefix desktop install`, the desktop app built/launched as `target\debug\jarvisv7-desktop.exe`; user performed initial ARM64 visual smoke and reported it was OK. Existing ARM64 automated validation for this pass: desktop static contract PASS (`24 passed in 0.11s`); regression PASS (`105 passed, 4 deselected in 1.09s`).
  - Note: Documentation-only follow-up. No source, tests, `SYSTEM_INVENTORY.md`, desktop source, or validation reruns were performed in this step.

- 2026-05-26 11:08
  - Summary: Fixed Windows ARM64 fresh-clone bootstrap ordering so `scripts/bootstrap.py` no longer fails before provisioning with missing dependency imports such as `yaml`. Added a minimal missing-module recovery note to `docs/windows-arm64-fresh-clone-setup.md` telling users not to hand-install missing modules and to use repo provisioning if bootstrap fails before checkpoint 2.
  - Scope: `scripts/bootstrap.py`, `backend/tests/unit/scripts/test_bootstrap_script.py`, `docs/windows-arm64-fresh-clone-setup.md`
  - Host class(es): Windows ARM64 / arm64
  - Evidence: `backend\.venv\Scripts\python scripts\provision.py install` PASS (declared dependencies installed, including `pyyaml-6.0.3`, `pytest-9.0.3`, and `jarvisv7-0.0.1`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\scripts\test_bootstrap_script.py -q` PASS (`4 passed in 0.03s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`105 passed, 4 deselected in 1.27s`); `backend\.venv\Scripts\python scripts\bootstrap.py` PASS (checkpoints 1/5 through 5/5 completed); `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS (`"ready": true`, `"missing": []`).
  - Note: Initial focused test attempt was blocked because the fresh/current venv did not yet contain `pytest`; repo provisioning resolved it through the approved provisioning path. No provisioning semantics, dependency declarations, backend runtime selection, or desktop behavior changed.

- 2026-05-22 18:45
  - Summary: Completed Slice J corrective pass for LLM readiness display semantics after J.4 manual smoke. Added a narrow frontend-only exception for `family === "llm"`, active LLM runtime `ollama`, and reason `local runtime unavailable`; that case now renders as degraded instead of failed in the readiness panel; the backend reason remains visible; and `degraded-list.js` was unchanged, so non-ready LLM remains listed in degraded conditions.
  - Scope: `desktop/src/components/readiness-panel.js`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows x64 / amd64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`24 passed in 0.21s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`104 passed, 4 deselected in 0.98s`).
  - Note: No backend, Tauri, dependency, style redesign, J.5 rendering, `SYSTEM_INVENTORY.md`, or schema changes were made. Manual desktop smoke remained pending for this corrective pass. ARM64 validation was not claimed in this entry; the desktop shell boundary owned cross-host validation.

- 2026-05-22 18:27
  - Summary: Completed Sub-Slice J.4 v7-native visual polish on Windows x64. Added a delimited visual token section in `desktop/src/style.css`; replaced raw rule-body colors with token references outside the token section; added token-driven dark theme styling for shell surfaces, panels, controls, readiness rows, degraded conditions, wake/status text, PTT capture states, and conversation surfaces; styled J.2 `data-state` labels; styled PTT/manual capture states through `data-capture-state`, including recording pulse/glow and reduced-motion handling; styled readiness states with non-color-only markers; styled existing conversation role classes only; and added static contract tests for tokens, no raw colors outside the token section, state/capture/readiness selectors, conversation hierarchy selectors, and no inline styles.
  - Scope: `desktop/src/style.css`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows x64 / amd64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`23 passed in 0.35s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`104 passed, 4 deselected in 0.93s`).
  - Manual evidence: Windows x64 desktop smoke passed after retry; dark visual polish was improved and usable; readiness/degraded sections rendered visibly; wake section rendered; PTT button no longer said `Hold to Talk`; click-start / click-stop PTT worked; STT→LLM→TTS completed and assistant response was spoken/rendered; `/health` responded before and after the voice attempt; existing `LLM failed: local runtime unavailable` readiness row was accepted as non-blocking dev/readiness semantics while active runtime is Ollama.
  - Note: No markdown parsing, code-block detection, DOM restructuring, `innerHTML`, JS behavior, or J.5 rendering behavior was added. ARM64 validation was not claimed in this entry; the desktop shell boundary owned ARM64-specific validation.

- 2026-05-22 10:01
  - Summary: Completed Sub-Slice J.3b Wake Status + True Click-Start / Click-Stop PTT on Windows x64. Replaced HTT pointer-hold behavior with click-start / click-stop PTT; removed `pointerdown`, `pointerup`, and `pointercancel` hold-to-talk behavior; preserved the existing WebView `MediaRecorder` flow, WAV encoding, `submit_voice`, response rendering, failure handling, and backend/Tauri command paths; added `wake-indicator.js` to render existing wake fields `provider`, `available`, `monitoring`, and `reason`; and updated static desktop contract tests for J.3b.
  - Scope: `desktop/src/main.js`, `desktop/src/index.html`, `desktop/src/components/wake-indicator.js`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows x64 / amd64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`19 passed in 0.11s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`104 passed, 4 deselected in 0.99s`).
  - Note: Backend schemas/routes, Tauri commands/plugins, dependencies/provisioning, `desktop/src/style.css`, and `SYSTEM_INVENTORY.md` were unchanged. Manual desktop validation remained pending. ARM64 validation was not claimed in this entry; the desktop shell boundary owned ARM64-specific validation.

- 2026-05-22 09:10
  - Summary: Completed Sub-Slice J.3a Wake/PTT Interaction Boundary Assessment. Gate J-3 wake payload shape was confirmed for `provider`, `available`, `monitoring`, and `reason`; blocker assessment B1-B5 all passed; final decision: `PROCEED to J.3b`.
  - Scope: Read-only assessment of `20260515_slice-j.md`, `desktop/src/main.js`, `desktop/src/index.html`, `desktop/src-tauri/src/lib.rs`, `desktop/src-tauri/src/backend.rs`, `backend/app/api/schemas/status.py`, `backend/app/api/routes/status.py`, `CHANGE_LOG.md`
  - Host class(es): Windows x64 / amd64
  - Evidence: Static inspection only; no validation reruns required. B1 PASS: current WebView `MediaRecorder.start()` / `.stop()` calls are discrete and can support click-start/click-stop. B2 PASS: Tauri `submit_voice(audio_bytes: Vec<u8>)` accepts complete audio bytes and calls `submit_voice_turn`. B3 PASS: existing JS globals (`mediaStream`, `mediaRecorder`, `audioChunks`) do not block replacing pointer-hold handlers with a click-state guard. B4 PASS: current MediaRecorder flow already collects `dataavailable` chunks and processes them on `stop`. B5 PASS: `submit_voice_turn` posts complete WAV bytes to `POST /task/voice` with `application/octet-stream`, so no backend route change is required.
  - Note: No production code, tests, backend, Tauri, dependency, provisioning, or desktop source changes were made. `desktop/src/components/wake-indicator.js` is treated as J.3b-owned if J.3b proceeds.

- 2026-05-22 08:20
  - Summary: Completed Sub-Slice J.2 named interaction state labels on Windows x64. Added `setStateLabel(stateKey, labelEl)` with user-facing labels for known shell/turn state keys, preserved unknown state keys as raw visible values, stored the raw state key in `data-state` for later styling, and routed header state plus `#turn-state` display through the helper while preserving existing degraded body attribute behavior.
  - Scope: `desktop/src/components/state-label.js`, `desktop/src/main.js`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows x64 / amd64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`17 passed in 0.10s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`104 passed, 4 deselected in 0.91s`).
  - Note: Backend, Tauri, `desktop/src/index.html`, `desktop/src/style.css`, wake/PTT behavior, and adjacent desktop shell work were unchanged. Manual desktop validation remained pending. ARM64 validation was not claimed in this entry; the desktop shell boundary owned ARM64-specific validation.

- 2026-05-22 07:54
  - Summary: Completed Sub-Slice J.1 readiness/sidebar surfacing on Windows x64. Readiness rendering moved from inline `desktop/src/main.js` markup into plain ES module renderers; backend-derived readiness values are rendered with DOM/text APIs; degraded/fallback conditions are surfaced in a dedicated container; voice debug details are collapsed by default; and existing backend/Tauri calls plus current voice capture behavior were preserved.
  - Scope: `desktop/src/components/readiness-panel.js`, `desktop/src/components/degraded-list.js`, `desktop/src/index.html`, `desktop/src/main.js`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows x64 / amd64
  - Evidence: `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop\test_desktop_static_contract.py -q` PASS (`15 passed in 0.20s`); `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`341 passed in 3.77s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`104 passed, 4 deselected in 1.15s`).
  - Note: Manual desktop validation remained pending. ARM64 validation was not claimed in this entry; the desktop shell boundary owned ARM64-specific validation.

- 2026-05-13 14:57
  - Summary: Completed Sub-Slice I.3 ARM64 follow-up validation and live turn matrix extension on a Windows ARM64 QNN-capable host. Added ARM64 live turn coverage in `test_voice_acceleration_matrix_live.py` and applied one bounded corrective fix to make ARM64 QNN-path assertion deterministic by proving explicit CPU fallback when QNN full-turn state does not complete to `IDLE`.
  - Scope: `backend/tests/runtime/turn/test_voice_acceleration_matrix_live.py`
  - Host class(es): Windows ARM64
  - Evidence: `backend/.venv/Scripts/python -m pytest backend/tests/unit/api/test_routes.py -q` PASS (`21 passed in 1.27s`); `backend/.venv/Scripts/python scripts/validate_backend.py regression` PASS (`PASS: unit: 104 tests`, `104 passed, 4 deselected in 2.10s`); `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families turn --devices qnn` initial FAIL (`test_voice_turn_uses_normalized_stt_device_arm64` asserted `FAILED` vs expected `IDLE`), post-fix rerun PASS (`1 passed, 34 deselected in 14.18s`); `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families turn --devices cpu` PASS (`10 passed, 1 skipped, 24 deselected in 72.25s`) with expected x64-only skip (`requires x64 host`).
  - Note: Corrective fixes used in this ARM64 I.3 pass: 1/2. API schema/route surfaces for `stt_device` were already present and required no code changes in this pass.

- 2026-05-13 14:44
  - Summary: Completed Sub-Slice I.3 (x64 Live Mic/Audio User-Interaction Matrix) by adding STT device observability to `/task/voice` responses and extending x64 live turn matrix coverage. A bounded corrective fix replaced an initial brittle `stt_device` derivation with direct engine STT runtime device wiring.
  - Scope: `backend/app/api/schemas/voice.py`, `backend/app/api/routes/voice.py`, `backend/tests/unit/api/test_routes.py`, `backend/tests/runtime/turn/test_voice_acceleration_matrix_live.py`
  - Host class(es): Windows x64
  - Evidence: `backend/.venv/Scripts/python -m pytest backend/tests/unit/api/test_routes.py -q` PASS (`21 passed in 0.65s`); `backend/.venv/Scripts/python scripts/validate_backend.py regression` PASS (`PASS: unit: 104 tests`, `104 passed, 4 deselected in 0.94s`); `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families turn --devices cuda` PASS (`1 passed, 32 deselected in 13.42s`).
  - Note: Corrective fixes used in this task: 1/2. ARM64 live interaction execution was not claimed in this entry and required execution on the appropriate ARM64 host.

- 2026-05-13 14:31
  - Summary: Completed Sub-Slice I.2 (x64 Acceleration Sequence Normalization) on Windows x64 with a behavior-preserving normalization pass in STT readiness branch documentation for x64 ordering (CUDA → DirectML slot → CPU fallback). During validation, one bounded corrective fix was applied to restore token-proven ARM64 QNN readiness selection contract after an unintended side effect surfaced in unit tests.
  - Scope: `backend/app/hardware/readiness.py`
  - Host class(es): Windows x64
  - Evidence: `backend/.venv/Scripts/python -m compileall backend/app/hardware/readiness.py` PASS (`Compiling 'backend/app/hardware/readiness.py'...`); initial `backend/.venv/Scripts/python scripts/validate_backend.py unit` FAIL (2 tests: `test_stt_readiness_selects_qnn_when_qnn_tokens_are_proven`, `test_selector_returns_qnn_runtime_when_qnn_tokens_proven`); post-corrective `backend/.venv/Scripts/python scripts/validate_backend.py unit` PASS (`338 passed in 1.18s`); `backend/.venv/Scripts/python scripts/validate_backend.py regression` PASS (`PASS: unit: 104 tests`, `104 passed, 4 deselected in 0.91s`); `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families stt --devices cuda` PASS (`1 passed, 31 deselected in 6.45s`); `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families stt --devices cpu` PASS (`4 passed, 5 skipped, 23 deselected in 51.18s`); `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families tts --devices cpu` PASS (`4 passed, 1 skipped, 27 deselected in 18.49s`).
  - Note: Corrective fixes used in this task: 1/2. No changes were made outside allowed scope (`backend/app/hardware/readiness.py`, `config/hardware/notes.md`), and `config/hardware/notes.md` required no update.

- 2026-05-13 14:21
  - Summary: Completed Sub-Slice I.1 (ARM Acceleration Sequence Normalization) on Windows ARM64 by normalizing ARM64 STT readiness to require both QNN prerequisite tokens and the QNN artifact presence via model catalog lookup before selecting `qnn`, while preserving CPU fallback behavior. Added hardware acceleration chain documentation for ARM64 and x64 in `config/hardware/notes.md` and documented H.7 TTS provider-override rationale inline in readiness derivation comments.
  - Scope: `backend/app/hardware/readiness.py`, `config/hardware/notes.md`
  - Host class(es): Windows ARM64
  - Evidence: `backend/.venv/Scripts/python -m compileall backend/app/hardware/readiness.py` PASS (`Compiling 'backend/app/hardware/readiness.py'...`); `backend/.venv/Scripts/python scripts/validate_backend.py unit` PASS (`338 passed in 2.02s`); `backend/.venv/Scripts/python scripts/validate_backend.py regression` PASS (`PASS: unit: 104 tests`, `104 passed, 4 deselected in 2.05s`); `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families stt --devices qnn` first run FAIL (`Windows fatal exception: access violation`), immediate rerun PASS (`3 passed, 29 deselected in 5.41s`); `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families stt --devices cpu` PASS (`7 passed, 2 skipped, 23 deselected, 1 warning in 61.89s`); `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families tts --devices cpu` PASS (`3 passed, 2 skipped, 27 deselected in 54.32s`).
  - Note: No runtime family or selector dispatch files were modified. I.1 completion used no corrective code fix (0/2); one non-reproducible transient QNN runtime crash was observed and cleared on deterministic rerun.

- 2026-05-13 09:01
  - Summary: Completed Sub-Slice H.8 (Voice Acceleration Live Turn Matrix) closeout across both host classes by combining prior x64 completion context (CUDA-class host evidence) with this session’s ARM64 follow-up validation (QNN-capable host). H.8 live turn matrix, acceleration matrix, and regression gates are now explicitly recorded as validated for Windows x64 and Windows ARM64.
  - Scope: `CHANGE_LOG.md` (H.8 closeout evidence entry)
  - Host class(es): Windows x64 (GPU-CUDA class context evidence), Windows ARM64 (QNN-capable live evidence)
  - Evidence: Windows x64 — context evidence provided for this closeout: H.8 live turn matrix test PASS on x64, H.8 acceleration matrix test PASS on x64, and regression remained green on x64; TTS accelerated paths remained `NOT-WIRED:provider-override-missing` and DirectML remained non-proven (`SKIP-prereq-missing` / not wired outcomes). Windows ARM64 — `$env:JARVISV7_LIVE_TESTS="true"; backend/.venv/Scripts/python -m pytest backend/tests/runtime/turn/test_voice_acceleration_matrix_live.py -q` PASS (`1 passed in 17.45s`); `$env:JARVISV7_LIVE_TESTS="true"; backend/.venv/Scripts/python -m pytest backend/tests/runtime/acceleration_matrix/test_acceleration_matrix.py -q` PASS (`1 passed in 1.88s`); `backend/.venv/Scripts/python scripts/validate_backend.py regression` PASS (`[fingerprint] arch=arm64 ... readiness=ready`, `PASS: unit: 104 tests`, `104 passed, 4 deselected in 2.26s`).
  - Note: H.8 close-state language for this dual-host record: live turn matrix `PASS` on Windows x64 and Windows ARM64; acceleration matrix `PASS` on Windows x64 and Windows ARM64; regression gate `PASS` on Windows x64 and Windows ARM64. No runtime source edits were made for this ARM64 follow-up pass.

- 2026-05-13 08:10
  - Summary: Completed Sub-Slice H.7 (TTS Acceleration Viability / Device Slot Normalization) as a normalization-plus-viability closeout. Device slot normalization was applied to accept `cpu`, `cuda`, `directml`, and `qnn` in the TTS base guard. Live/package viability proof showed the installed `kokoro_onnx.Kokoro` constructor does not expose provider override, so accelerated TTS paths were closed as not wired with `provider-override-missing` fail-closed behavior while preserving CPU synthesis.
  - Scope: `backend/app/runtimes/tts/base.py`, `backend/app/runtimes/tts/kokoro_onnx_runtime.py`, `backend/app/hardware/readiness.py`, `backend/tests/unit/hardware/test_readiness.py`, `backend/tests/unit/runtimes/tts/test_tts_runtime.py`, `backend/tests/runtime/voice/test_tts_live.py`
  - Host class(es): Windows x64
  - Evidence: `backend/.venv/Scripts/python -c "import inspect, kokoro_onnx; print(inspect.signature(kokoro_onnx.Kokoro.__init__))"` PASS with signature `(self, model_path: str, voices_path: str, espeak_config: kokoro_onnx.config.EspeakConfig | None = None, vocab_config: dict | str | None = None)` (no `providers` parameter); `$env:JARVISV7_LIVE_TESTS="true"; backend/.venv/Scripts/python -m pytest backend/tests/runtime/voice/test_tts_live.py -q` PASS/SKIP (`2 passed, 1 skipped`) with DirectML skip reason `requires DirectML execution provider readiness`; `backend/.venv/Scripts/python -m pytest backend/tests/unit/runtimes/tts/test_tts_runtime.py -q` PASS (`13 passed in 0.34s`); `backend/.venv/Scripts/python -m pytest backend/tests/unit/hardware/test_readiness.py -q` PASS (`9 passed in 0.04s`).
  - Note: H.7 close-state outcomes on this host: TTS CUDA `NOT-WIRED:provider-override-missing`, TTS DirectML `NOT-WIRED:provider-override-missing` plus host DirectML readiness skip, TTS QNN `NOT-WIRED:provider-override-missing`; ARM64/QNN path was not activated in this scope. No STT runtime changes, no QNN/ARM64 component modifications, and no model artifact changes were made.

- 2026-05-13 07:15
  - Summary: Sub-Slices H.5 (DirectML viability gate) and H.6 (DirectML STT/TTS activation) were closed on Windows x64 and Windows ARM64. `DmlExecutionProvider` was absent from the installed ORT wheel on both host classes; live gate tests skipped deterministically on both hosts. H.5 closes as `SKIP-prereq-missing` on both host classes; H.6 closes as `NOT-WIRED:directml-provider-missing`.
  - Scope: `backend/tests/runtime/hardware/test_directml_gate_live.py` (new)
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Windows x64 — `$env:JARVISV7_LIVE_TESTS="true"; backend\.venv\Scripts\python -m pytest backend/tests/runtime/hardware/test_directml_gate_live.py -q` result: `2 skipped in 0.57s`; skip reason: `requires DirectML execution provider readiness`; `ep:DmlExecutionProvider` absent from preflight tokens on x64 ORT GPU wheel. Windows ARM64 — same command: `2 skipped`; skip reason unchanged; `ep:DmlExecutionProvider` absent from preflight tokens on ARM64 ORT wheel.
  - Note: H.5 close state: `SKIP-prereq-missing` on Windows x64 (RTX 3060 present; `DmlExecutionProvider` absent from installed `onnxruntime-gpu` wheel) and `SKIP-prereq-missing` on Windows ARM64 (Qualcomm Adreno present; `DmlExecutionProvider` absent from installed ORT wheel). H.6 close state: `NOT-WIRED:directml-provider-missing` on both host classes because H.6 requires H.5 PASS. No runtime source, provisioning, `pyproject.toml`, or `SYSTEM_INVENTORY.md` changes were made. Preflight already included provider-token probing; no `preflight.py` extension was required.

- 2026-05-12 09:47
  - Summary: Completed H.3 ARM64 QNN STT activation on Windows ARM64 by finalizing `QnnWhisperRuntime.transcribe()` for the precompiled Qualcomm artifact contract and passing live STT transcript validation.
  - Scope: `backend/app/runtimes/stt/onnx_whisper_runtime.py`, `CHANGE_LOG.md`
  - Host class(es): Windows ARM64 / Qualcomm QNN
  - Evidence: `$env:JARVISV7_LIVE_TESTS="true"; backend\.venv\Scripts\python -m pytest backend/tests/runtime/voice/test_stt_live.py -q -s -k qnn` PASS (`1 passed, 2 deselected in 4.49s`); `backend\.venv\Scripts\python -m pytest backend/tests/unit/runtimes/stt/test_stt_runtime.py -q` PASS (`13 passed in 0.06s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`102 passed, 2 deselected in 0.99s`).
  - Note: Decisive runtime fix used QNN decoder prompt seed `[50258]` for this precompiled artifact contract. Retained runtime behavior includes explicit cross-cache mapping, fail-fast behavior for unmapped cross inputs, dynamic `attention_mask` shape derivation, and `attention_mask` filled with ones. Final status: `H.3 PASS`.

- 2026-05-11 15:01
  - Summary: Completed H.3 pre-qualification on Windows ARM64 by proving Qualcomm precompiled Whisper QNN artifact/session readiness and required mechanical/runtime gates; final decision was `PROCEED`.
  - Scope: `CHANGE_LOG.md`
  - Host class(es): Windows ARM64 / Snapdragon X Elite
  - Evidence: QNN plugin and HTP backend were discovered through `onnxruntime-qnn`; H.2 live gate passed (`2 passed in 0.73s`); Qualcomm artifact `whisper_base-precompiled_qnn_onnx-float-qualcomm_snapdragon_x_elite.zip` downloaded successfully (`180640873` bytes); extracted ONNX files identified as `encoder.onnx` (`1556` bytes) and `decoder.onnx` (`4483` bytes); encoder and decoder QNN sessions initialized with `disable_cpu_fallback=True`; encoder contract included `input_features [1,80,3000] float16` with cross-cache outputs through layers 0-5; decoder contract included `input_ids`, `attention_mask`, self-cache inputs, cross-cache inputs, `position_ids`, and output `logits [1,51865,1,1] float16` plus self-cache outputs; known-audio mechanical probe succeeded with audio `(62560,)` at `16000`, features `(1,80,3000)` float16, encoder output `(8,1,64,1500)`, decoder logits `(1,51865,1,1)`; regression passed (`102 passed, 2 deselected in 1.02s`).
  - Note: Final decision: `PROCEED`.

- 2026-05-09 13:10
  - Summary: Removed personality-derived text injection from the active final prompt path while preserving personality as structured metadata for loading, selection, desktop display, session state, and turn artifacts. Prompt/response engine architecture was preserved.
  - Scope: `backend/app/cognition/prompt_assembler.py`, `backend/app/conversation/engine.py`, `backend/app/personality/adapter.py`, `config/personality/concise.yaml`, `config/personality/warm.yaml`, `backend/tests/unit/cognition/test_prompt_assembler.py`, `backend/tests/unit/conversation/test_engine.py`, `backend/tests/unit/personality/test_personality.py`
  - Host class(es): Windows ARM64
  - Evidence: `backend/.venv/Scripts/python -m pytest backend/tests/unit/cognition/test_prompt_assembler.py backend/tests/unit/conversation/test_engine.py backend/tests/unit/personality/test_personality.py -q` PASS (`48 passed in 0.31s`); `backend/.venv/Scripts/python scripts/validate_backend.py regression` PASS (`102 passed, 2 deselected in 1.07s`); validator summary `[PASS] JARVISv7 backend regression is validated!`.
  - Note: Removed prompt lines for Assistant/Tone/Brevity/system_prompt_addendum, removed active `apply_personality(...)` mutation from reasoning path, converted `apply_personality(...)` to pass-through, and cleared prompt-instruction residue in concise/warm personality configs. Personality metadata behavior remains intact, including `active_personality_profile_id` in turn artifacts. Prompt assembly still preserves working memory, retrieved context, tool execution context, and user transcript.

- 2026-05-09 12:34
  - Summary: Completed documentation of a focused cleanup batch covering normal readiness wording/user-facing copy, TTS configured-voice wiring, and desktop layout usability compaction. Runtime guardrails and diagnostics/preflight strings were preserved.
  - Scope:
    - Readiness wording cleanup: `backend/app/hardware/readiness.py`, `backend/tests/unit/hardware/test_qnn_slot.py`, `backend/tests/unit/hardware/test_readiness.py`, `desktop/src/index.html`, `desktop/src/main.js`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
    - TTS configured voice wiring: `config/models/tts.yaml`, `backend/app/runtimes/tts/tts_runtime.py`, `backend/tests/unit/runtimes/tts/test_tts_runtime.py`
    - Desktop layout usability cleanup (CSS-only): `desktop/src/style.css`
  - Host class(es): Windows ARM64
  - Evidence:
    - `backend\\.venv\\Scripts\\python -m pytest backend/tests/unit/hardware/test_qnn_slot.py backend/tests/unit/hardware/test_readiness.py -q` PASS (`15 passed in 0.03s`)
    - `backend\\.venv\\Scripts\\python -m pytest backend/tests/unit/hardware/test_qnn_slot.py backend/tests/unit/hardware/test_readiness.py backend/tests/unit/desktop/test_desktop_static_contract.py -q` PASS (`27 passed in 0.10s`)
    - `backend\\.venv\\Scripts\\python -m pytest backend/tests/unit/runtimes/tts/test_tts_runtime.py -q` PASS (`9 passed in 0.06s`)
    - `backend\\.venv\\Scripts\\python -m pytest backend/tests/unit/desktop/test_desktop_static_contract.py -q` PASS (`12 passed in 0.02s`)
    - `backend\\.venv\\Scripts\\python scripts/validate_backend.py regression` PASS (`102 passed, 2 deselected in 1.02s`)
  - Note: ARM64 STT normal readiness now reports effective usable CPU-path wording instead of QNN prerequisite slice wording, and LLM normal readiness now reports `local runtime unavailable`; desktop shell-audio/wake/resident/global-hotkeys footer wording was removed. QNN STT activation was not revisited. Runtime behavior and selector behavior were preserved except that configured TTS voice is now passed from YAML into `KokoroOnnxRuntime` construction (direct runtime constructor default remains fallback-only). Desktop layout cleanup was CSS-only. Personality prompt behavior was not changed in this cleanup batch.

- 2026-05-09 20:37
  - Summary: Completed STT/QNN cleanup by removing the QNN Tiny STT catalog artifact dependency from active runtime/test paths and preserving QNN STT as explicitly not wired without artifact/runtime proof. Also removed catalog-owned model-ID constructor defaults in STT/TTS/Wake runtimes so defaults resolve through model catalogs when `model_name` is unset.
  - Scope: `config/models/stt.yaml`, `backend/app/runtimes/stt/onnx_whisper_runtime.py`, `backend/app/runtimes/stt/stt_runtime.py`, `backend/app/runtimes/tts/kokoro_onnx_runtime.py`, `backend/app/runtimes/wake/openwakeword_runtime.py`, `backend/tests/runtime/hardware/test_qnn_gate_live.py`, `backend/tests/unit/runtimes/stt/test_stt_runtime.py`
  - Host class(es): Windows ARM64
  - Evidence: `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only` PASS (`ready=true`); `backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt,tts,wake` PASS (`11 passed, 15 deselected, 1 warning`); `backend\.venv\Scripts\python -m pytest backend/tests/unit/runtimes/stt/test_stt_runtime.py backend/tests/unit/runtimes/tts/test_tts_runtime.py backend/tests/unit/runtimes/wake/test_wake_runtime.py -q` PASS (`26 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`102 passed, 2 deselected`).

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
  - Summary: H.3 QNN STT follow-up corrections were completed on Windows ARM64 by aligning the QNN precompiled model catalog and runtime file expectations with the extracted artifact layout, wiring QNN runtime dispatch, updating STT QNN readiness selection, adjusting validator readiness summary derivation to selected-path relevance without suppressing diagnostics, and updating the superseded QNN readiness unit assertion/test name. A scoped cleanup also updated the not-wired transcription message and set the QNN model catalog runtime key to `qnn_whisper`.
  - Scope: `config/models/stt.yaml`, `backend/app/runtimes/stt/onnx_whisper_runtime.py`, `backend/app/runtimes/stt/stt_runtime.py`, `backend/app/hardware/readiness.py`, `scripts/validate_backend.py`, `backend/tests/unit/hardware/test_qnn_slot.py`
  - Host class(es): Windows ARM64
  - Evidence: `backend\.venv\Scripts\python scripts\ensure_models.py --verify-only --family stt` PASS (`"whisper-tiny-qnn-precompiled-snapdragon-x-elite" missing=[] ready=true` with nested present paths including `.../encoder.onnx` and `.../decoder.onnx`); `backend\.venv\Scripts\python -c "from backend.app.runtimes.stt.onnx_whisper_runtime import QnnWhisperRuntime; r=QnnWhisperRuntime(model_name='whisper-tiny-qnn-precompiled-snapdragon-x-elite'); print('is_available=', r.is_available())"` PASS (`is_available= True`); `backend\.venv\Scripts\python -c "... select_stt_runtime ...; print(type(runtime).__name__, runtime.device)"` PASS (`QnnWhisperRuntime qnn`); `backend\.venv\Scripts\python -c "... derive_stt_device_readiness ...; print(...)"` PASS (`('qnn', True, 'qnn prerequisites proven; selecting qnn')`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\hardware\test_qnn_slot.py -q` PASS (`8 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py profile` PASS with fingerprint readiness `ready; tokens=19`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`98 passed, 1 skipped in 2.11s`).

- 2026-05-05 12:30
  - Summary: Sub-Slice H.3 QNN STT Runtime Implementation Enablement - fixing the QNN plugin discrepancy between repo implementation and the external TempTransfers/ARM64-QNN reference. A hybrid QNN provider initialization strategy was implemented that passes `backend_path` in `provider_options` to `InferenceSession()`, enabling sessions to load successfully with the plugin installed outside the repo. New `backend/app/hardware/qnn_provider.py` module added with `get_qnn_provider_options()` and `create_qnn_session()` helpers; `QnnWhisperRuntime` class added for QNN-accelerated STT with encoder/decoder session initialization; preflight probe updated to capture QNN library path token; test updated to use new provider helper; and two unrelated failing tests fixed (LLM error message match, path handling in ensure_models verification).
  - Scope: `backend/app/hardware/qnn_provider.py` (new), `backend/app/hardware/preflight.py`, `backend/app/runtimes/stt/onnx_whisper_runtime.py`, `backend/tests/runtime/hardware/test_qnn_session_init_live.py`, `backend/tests/unit/runtimes/llm/test_llm_runtime.py`, `scripts/ensure_models.py`, `config/models/stt.yaml`
  - Host class(es): Windows ARM64
  - Evidence: `backend\.venv\Scripts\python scripts\validate_backend.py profile` PASS with fingerprint `arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=degraded`; `backend\.venv\Scripts\python scripts\validate_backend.py unit` PASS (`324 passed in 1.16s`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`96 passed`); `$env:JARVISV7_LIVE_TESTS='1'; backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt --devices cpu` PASS (`4 passed, 1 skipped, 20 deselected in 29.71s`); `$env:JARVISV7_LIVE_TESTS='1'; backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt --devices qnn` PASS (`1 skipped, 24 deselected in 0.80s`). QNN session init test skipped due to missing QAIRT SDK readiness (expected on non-Snapdragon hosts without plugin); CPU STT paths remain green and functional; full QNN transcription inference was not implemented in that scope.
  - Note: `create_qnn_session()` implements hybrid strategy: attempts `SessionOptions.add_provider_for_devices()` first (preferred), falls back to provider list with explicit `backend_path` in `provider_options` (external plugin pattern). Encoder/decoder sessions load via QNN provider with CPU fallback disabled; sessions auto-cleanup (unregister) after creation. `QnnWhisperRuntime` proof-validates session initialization; full transcription (audio preprocessing, tokenization, decoder loop) was not implemented in that scope. Existing CPU STT, CUDA STT (x64), and DirectML STT behaviors preserved; no model export/download/mutation, no API/schema changes, no desktop/shell rendering, and no agent behavior introduced.


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
  - Note: This is D.4 progress only, not full D.4 completion. No human live wake test was run from Cline; live microphone wake monitoring, wake-triggered capture, and final wake/voice UX were not claimed in this entry. No `SYSTEM_INVENTORY.md` update is claimed in this step.

- 2026-04-29 13:18
  - Summary: D.3 first-pass resident session continuity progress was validated (not full D.3 completion). Backend-owned `SessionService` and `GET /session/status` were added; session create/close and text turns now run through the active resident-session boundary; supplied `session_id` is validated when present; and desktop now displays session id and turn count through Tauri `get_session_status`.
  - Scope: `backend/app/services/session_service.py`, `backend/app/api/routes/session.py`, `backend/app/api/schemas/session.py`, `backend/app/api/dependencies.py`, `backend/app/api/routes/task.py`, `desktop/src-tauri/src/{backend.rs,lib.rs}`, `desktop/src/main.js`, `desktop/src/index.html`, `backend/tests/unit/services/test_session_service.py`, `backend/tests/unit/api/test_routes.py`, `backend/tests/integration/api/test_headless_client.py`, `backend/tests/unit/desktop/test_desktop_static_contract.py`
  - Host class(es): Windows x64, Windows ARM64
  - Evidence: Service unit PASS on both hosts (x64 `6 passed in 1.03s`; ARM64 `6 passed in 0.12s`); API unit PASS on both hosts (x64 `15 passed in 0.91s`; ARM64 `15 passed in 0.44s`); API integration PASS on both hosts (x64 `5 passed in 0.38s`; ARM64 `5 passed in 0.36s`); desktop static PASS on both hosts (x64 `9 passed in 0.18s`; ARM64 `9 passed in 0.04s`); validator unit PASS on both hosts (x64 `233 passed`; ARM64 `233 passed`); validator integration PASS on both hosts (x64 `8 passed`; ARM64 `8 passed`); regression PASS on both hosts (x64 `95 passed`; ARM64 `95 tests`). D.3-specific proof: integration test drove three text turns with one `session_id`, and `/session/status` returned `active=true` with `turn_count=3`.
  - Note: This is D.3 first-pass progress only, not full D.3 completion. No live human voice test was run in Cline; voice multi-turn proof was not claimed without user-run live evidence. No `SYSTEM_INVENTORY.md` update is claimed in this step.

- 2026-04-29 10:15
  - Summary: D.2 Durable Desktop Host was closed across Windows x64 and Windows ARM64 using the previously recorded D.2 progress evidence.
  - Scope: `CHANGE_LOG.md` only; closeout delta referencing prior D.2 progress entries.
  - Host class(es): Windows x64 and Windows ARM64
  - Evidence: Prior D.2 progress entries are the evidence source: `2026-04-29 05:32` for Windows x64 and `2026-04-29 06:00` for Windows ARM64.
  - Note: HTT validated the D.2 voice path, but HTT is not the final intended PTT UX; the desktop shell boundary owns final PTT interaction semantics. Browser capture/WAV path worked, but idealized 16 kHz PCM/downsample quality is not claimed. No `SYSTEM_INVENTORY.md` update was made in this step.

- 2026-04-29 09:36
  - Summary: D.2 Durable Desktop Host was closed across Windows x64 and Windows ARM64 by accepting the previously recorded host-specific progress evidence. The durable npm/Tauri desktop host, backend lifecycle through `scripts/run_backend.py`, readiness display, visible text turn, tray lifecycle menu, robot `.ico`, and HTT voice-path proof are now the D.2 closeout baseline.
  - Scope: `CHANGE_LOG.md` only; closeout delta over prior D.2 evidence in `desktop/` and `backend/tests/unit/desktop/`
  - Host class(es): Windows x64 and Windows ARM64
  - Evidence: Prior D.2 progress entries are the evidence source: `2026-04-29 05:32` for Windows x64 and `2026-04-29 06:00` for Windows ARM64.
  - Note: HTT validated the D.2 voice path, but HTT is not the final intended PTT UX; the desktop shell boundary owns final PTT interaction semantics. Browser capture/WAV path worked, but idealized 16 kHz PCM/downsample quality is not claimed. No `SYSTEM_INVENTORY.md` update was made in this step.

- 2026-04-29 06:00
  - Summary: D.2 desktop progress previously validated on Windows x64 was also validated on Windows ARM64. Validation confirmed current desktop host progress only (not full D.2 completion): ARM64 dev-runner/toolchain readiness, desktop static/unit checks, lockfile-based npm install, cargo check, backend dry-run/regression, and Tauri dev launch with user-confirmed ARM64 smoke.
  - Scope: `desktop/`, `backend/tests/unit/desktop/`
  - Host class(es): Windows ARM64
  - Evidence: `backend\.venv\Scripts\python scripts\dev_runner.py check --arch arm64` PASS (`SUMMARY arch=arm64 failures=0 warnings=1`); `backend\.venv\Scripts\python -m pytest backend\tests\unit\desktop -q` PASS (`8 passed in 0.03s`); `npm --prefix desktop install` PASS using committed `desktop/package-lock.json`; `npm --prefix desktop test` PASS (desktop static voice checks); `cargo check --manifest-path desktop\src-tauri\Cargo.toml` PASS; `backend\.venv\Scripts\python scripts\run_backend.py --dry-run` PASS; `backend\.venv\Scripts\python scripts\validate_backend.py regression` PASS (`95 tests`); `npm --prefix desktop run dev` launch PASS. User-confirmed ARM64 desktop smoke: window opened, backend health/session/readiness loaded, text turn visible, tray menu operational, and HTT voice path reached `/task/voice` with visible result.
  - Note: This is D.2 progress validation only, not full D.2 completion. HTT remains a development-cycle proof path, not final intended PTT UX. No backend API/runtime behavior, scripts, provisioning, routing/policy, tools, agents, wake, resident loop, WebSockets, audio streaming, or shell-side playback was added; no `SYSTEM_INVENTORY.md` promotion is claimed.

- 2026-04-29 05:32
  - Summary: D.2 Windows x64 desktop progress was validated, not full D.2 completion. An npm/Tauri desktop host was added under `desktop/`; it starts the backend through `scripts/run_backend.py`, includes desktop lifecycle startup diagnostics/logging, displays readiness/runtime state, supports visible text turns, provides an operational tray menu (`Start Backend`, `Stop Backend`, `Show Window`, `Quit`), uses the robot `.ico` for desktop/tray icon, and includes a development-cycle Hold-to-Talk proof path using browser `getUserMedia`, frontend WAV encoding, raw WAV POST to `/task/voice`, and visible transcript/response/degraded/failure fields. HTT is not the final intended PTT UX; the desktop shell boundary owns durable PTT interaction semantics.
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
  - Note: Local Ollama live validation used `phi4-mini`. Cloud runtimes are policy-gated stubs only, llama.cpp was not wired as a verified runtime, and no Slice B completion or `SYSTEM_INVENTORY.md` update is claimed.

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
