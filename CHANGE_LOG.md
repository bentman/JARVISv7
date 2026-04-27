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
  - Note: Local Ollama live validation used `phi4-mini`. Cloud runtimes are policy-gated stubs only, llama.cpp remains deferred to H.1, and no Slice B completion or `SYSTEM_INVENTORY.md` update is claimed.
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
