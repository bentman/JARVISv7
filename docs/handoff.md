# Cross-Device Handoff

This file preserves enough context for another device or Codex session to continue without chat history. Add a new timestamped entry at the top before switching devices or ending work that another host class should continue. Keep entries short and evidence-focused. User normally handles git push/pull.

## Entries

### 2026-06-17 19:59 -05:00 — R.8 AMD64 real local llama.cpp app proof

- Active slice/sub-slice: Slice R / R.8 tandem live local LLM validation correction.
- Last worked on: Windows AMD64.
- Most recent change: Cut back the overbuilt R.8 repair path. Removed the new shared bootstrap/API/test-fixture direction, kept the proving-host path in `scripts/run_jarvis.py`, and verified the actual app text path starts a real local `llama-server.exe`, loads the selected GGUF, selects `llama.cpp`, completes one text turn, and stops the sidecar.
- Validation run: `backend\.venv\Scripts\python scripts\ensure_models.py --family llm --model assistant-small-q4 --verify-only` PASS (`ready=true`, selected GGUF present); `USE_LOCAL_MODEL=true` + `LLAMA_CPP_MANAGED=true` `backend\.venv\Scripts\python scripts\run_jarvis.py --text-only --turns 1 --trace-to reports\validation\slice_r_app_live` PASS with `llm_selected runtime=llama.cpp`, model `assistant-small-q4`, profile `windows_amd64_cpu`, `server is listening on http://127.0.0.1:8080`, `final_state=IDLE`, and non-empty `response_text`; `Get-Process -Name llama-server -ErrorAction SilentlyContinue` returned no process; focused sidecar pytest passed (`18 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260618005915-regression.txt`); `git diff --check` passed with line-ending warnings only.
- Close state: AMD64 CPU-only local llama.cpp application path is now real `PASS`. This corrects the earlier degraded/mock-heavy R.8 record for AMD64. AMD64 CUDA is still not live-validated. ARM64 local llama.cpp remains unproven/degraded until repeated on ARM64 hardware with model and binary evidence.
- Next needed: Windows ARM64 should repeat the real R.8 path or record explicit degraded reasons. Do not update `SYSTEM_INVENTORY.md` until R.9 closes on both required host classes.
- Next host class: Windows ARM64.

### 2026-06-17 19:13 -05:00 — R.8 ARM64 degraded live validation leg

- Active slice/sub-slice: Slice R / R.8 tandem live local LLM validation.
- Last worked on: Windows ARM64.
- Most recent change: Validated the already-landed R.8 live test shape on ARM64 without product code changes. Selected GGUF, ARM64 CPU llama-server binary, and ARM64 QNN llama-server binary were absent; live llama.cpp tests skipped with sidecar connection refused; Ollama fallback live validation passed.
- Validation run: `backend\.venv\Scripts\python scripts\ensure_models.py --family llm --verify-only` returned expected degraded state (`Degraded-no-local-model-artifact`); live LLM pytest with `JARVISV7_LIVE_TESTS=true` passed with local skips (`1 passed, 2 skipped`); live turn pytest with workspace `TMP`/`TEMP` passed with local/x64 skips (`10 passed, 2 skipped`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260618001029-regression.txt`). Fingerprint: `arch=arm64 python=3.13.13 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`.
- Close state: ARM64 CPU-only `Degraded-no-local-model-artifact` plus `Degraded-sidecar-unreachable`; ARM64 NPU/QNN `SKIP-no-viable-binary`; Ollama fallback `PASS`.
- Note: This does not close Slice R. No model artifact was downloaded, no real local llama.cpp sidecar was launched, real local llama.cpp completion is still not proven on ARM64, and no `SYSTEM_INVENTORY.md` update was made. Slice R remains open until all changes are verified live.
- Next needed: Acquire the selected GGUF and appropriate `llama-server.exe`, start the sidecar, then rerun live LLM and live turn validators on both AMD64 and ARM64 so R.8 can be closed with real local llama.cpp completion evidence.
- Next host class: Either host can continue R.8 artifact acquisition/live proof.

### 2026-06-17 19:04 -05:00 — R.8 AMD64 code-change/degraded live leg

- Active slice/sub-slice: Slice R / R.8 tandem live local LLM validation.
- Last worked on: Windows AMD64.
- Most recent change: Added live-gated llama.cpp availability/generation tests and a local llama.cpp text-turn live test beside the existing Ollama live tests. Registered `requires_llama_cpp` for strict pytest markers and added conftest helpers for llama.cpp base URL/model name.
- Validation run: `backend\.venv\Scripts\python scripts\ensure_models.py --family llm --verify-only` reported `Degraded-no-local-model-artifact` for `models\llm\assistant-small-q4\qwen2.5-0.5b-instruct-q4_k_m.gguf`. Configured AMD64 CPU/CUDA and ARM64 CPU `llama-server.exe` paths were absent. Live LLM validator with `JARVISV7_LIVE_TESTS=true` passed (`1 passed, 3 skipped`): Ollama fallback passed, local llama.cpp skipped with connection refused. Live turn validator with workspace `TMP`/`TEMP` passed (`9 passed, 3 skipped`): local llama.cpp turn skipped with connection refused. Regression passed (`119 passed, 4 deselected`, report `reports\validation\20260618000309-regression.txt`). `git diff --check` passed with line-ending warnings only. Fingerprint: `arch=amd64 python=3.12.10 extras=[hw-cpu-base,hw-x64-base,hw-gpu-nvidia-cuda,dev] readiness=ready`.
- Note: Real local llama.cpp completion is still not proven on AMD64. Current AMD64 CPU-only close state is `Degraded-no-local-model-artifact` plus `Degraded-sidecar-unreachable`; AMD64 CUDA remains missing configured binary/unvalidated. No `SYSTEM_INVENTORY.md` update was made.
- Next needed: Windows ARM64 should validate the same R.8 test shape. To actually close R.8 as live-complete on either host, acquire the selected GGUF and appropriate `llama-server.exe`, start the sidecar, then rerun live LLM and live turn validators. If artifacts remain absent on ARM64, record the explicit degraded/skipped close state.
- Next host class: Windows ARM64.

### 2026-06-17 18:52 -05:00 — R.7 ARM64 validation leg

- Active slice/sub-slice: Slice R / R.7 runtime selection, readiness, and trace.
- Last worked on: Windows ARM64.
- Most recent change: Validated the already-landed R.7 selector/readiness behavior on ARM64 without product code changes. `select_llm()` prefers viable managed local llama.cpp, then Ollama, then policy-gated cloud, then null; readiness surfaces LLM trace metadata and degraded reasons without claiming CUDA/QNN validation.
- Validation run: Focused R.7 pytest passed (`74 passed`, one existing Starlette `TestClient` deprecation warning); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260617235140-regression.txt`). Fingerprint: `arch=arm64 python=3.13.13 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`.
- Note: R.7 is now validated on both AMD64 and ARM64 according to the tandem host rule. No model artifact was downloaded, no real sidecar process was launched, no live completion was attempted, and no `SYSTEM_INVENTORY.md` update was made. Real local llama.cpp completion remains required in R.8 before Slice R closeout.
- Next needed: Start R.8 tandem live local LLM validation with real model, binary, sidecar, HTTP generation, and selector/readiness evidence. Validate CPU-only first; keep AMD64 CUDA and ARM64 QNN explicit as pass/degraded/skipped based on evidence.
- Next host class: Either host can begin R.8, but live validation evidence must be tracked for both AMD64 and ARM64 or record explicit degraded/skipped reasons.

### 2026-06-17 18:46 -05:00 — R.7 AMD64 code-change leg

- Active slice/sub-slice: Slice R / R.7 runtime selection, readiness, and trace.
- Last worked on: Windows AMD64.
- Most recent change: Extended the existing `select_llm()` path to prefer viable managed local llama.cpp, then Ollama, then policy-gated cloud, then null. `SelectionTrace` now carries optional local model/route/serve profile/accelerator/base URL/selected/degraded metadata. Startup state stores the LLM trace, and `/readiness` surfaces LLM trace metadata without claiming CUDA/QNN validation.
- Validation run: Focused R.7 pytest passed (`58 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260617234636-regression.txt`); `git diff --check` passed with line-ending warnings only. Fingerprint: `arch=amd64 python=3.12.10 extras=[hw-cpu-base,hw-x64-base,hw-gpu-nvidia-cuda,dev] readiness=ready`.
- Note: No model artifact was downloaded, no real sidecar process was launched, no live completion was attempted, and no `SYSTEM_INVENTORY.md` update was made. Real local llama.cpp completion remains required in R.8 before Slice R closeout.
- Next needed: Windows ARM64 should run focused R.7 pytest, regression, and diff check against the same changes. After R.7 validates on both hosts, proceed to R.8 tandem live local LLM validation with real model/binary/sidecar evidence.
- Next host class: Windows ARM64.

### 2026-06-17 18:40 -05:00 — R.6 ARM64 validation leg

- Active slice/sub-slice: Slice R / R.6 `LlamaCppLLM` HTTP runtime.
- Last worked on: Windows ARM64.
- Most recent change: Validated the already-landed R.6 HTTP runtime behavior on ARM64 without product code changes. `LlamaCppLLM` remains HTTP-client only, probes `/v1/models` with health fallback, posts `/v1/chat/completions`, maps generation defaults, handles empty/timeout/invalid/unsupported responses, keeps `runtime_name()` stable, and remains default-disabled before R.7 selection changes.
- Validation run: Focused R.6 pytest passed (`40 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260617233937-regression.txt`). Fingerprint: `arch=arm64 python=3.13.13 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`.
- Note: R.6 is now validated on both AMD64 and ARM64 according to the tandem host rule. HTTP tests are mocked for this sub-slice. No model artifact was downloaded, no real sidecar process was launched, runtime selection was not changed, and no `SYSTEM_INVENTORY.md` update was made. Real local llama.cpp completion remains required before Slice R closeout.
- Next needed: Start R.7 runtime selection, readiness, and trace. Selection must prefer viable managed local LLM only when profile/model/binary/sidecar evidence supports it, then fall back to Ollama/cloud/null with truthful degraded reasons.
- Next host class: Either host can begin R.7, but code-changing work must validate on both AMD64 and ARM64 or record an explicit degraded/skipped reason.

### 2026-06-17 18:35 -05:00 — R.6 AMD64 code-change leg

- Active slice/sub-slice: Slice R / R.6 `LlamaCppLLM` HTTP runtime.
- Last worked on: Windows AMD64.
- Most recent change: Activated `backend/app/runtimes/llm/local_runtime.py::LlamaCppLLM` as an HTTP client for the managed sidecar endpoint. It probes `/v1/models` with health fallback, calls `/v1/chat/completions`, maps generation defaults into OpenAI-compatible payloads, keeps `runtime_name()` stable, and remains disabled by default unless explicitly configured or supplied sidecar status so R.7 still owns selection changes.
- Validation run: Focused R.6 pytest passed (`40 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260617233539-regression.txt`); `git diff --check` passed with line-ending warnings only. Fingerprint: `arch=amd64 python=3.12.10 extras=[hw-cpu-base,hw-x64-base,hw-gpu-nvidia-cuda,dev] readiness=ready`.
- Note: HTTP tests are mocked for this sub-slice. No model artifact was downloaded, no real sidecar process was launched, runtime selection was not changed, and no `SYSTEM_INVENTORY.md` update was made. Real local llama.cpp completion must still be validated before Slice R closeout.
- Next needed: Windows ARM64 should run focused R.6 pytest, regression, and diff check against the same changes. Confirm default-disabled behavior still prevents accidental local runtime selection before R.7.
- Next host class: Windows ARM64.

### 2026-06-17 18:24 -05:00 — R.5 ARM64 validation leg

- Active slice/sub-slice: Slice R / R.5 sidecar lifecycle service.
- Last worked on: Windows ARM64.
- Most recent change: Validated the already-landed R.5 lifecycle service behavior on ARM64 without product code changes. `LocalLLMSidecarService` uses mocked/injectable process creation, supports idempotent start/stop, deterministic restart, restart-required reporting for changed model/profile, degraded start failures, status metadata, and health probe delegation.
- Validation run: Focused R.5 pytest passed (`32 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260617232221-regression.txt`). Fingerprint: `arch=arm64 python=3.13.13 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`.
- Note: R.5 is now validated on both AMD64 and ARM64 according to the tandem host rule. Unit tests use mocked process creation only. No model artifact was downloaded, no real sidecar process was launched, no HTTP runtime was activated, runtime selection was not changed, and no `SYSTEM_INVENTORY.md` update was made.
- Next needed: Start R.6 `LlamaCppLLM` HTTP runtime. It must remain an HTTP client only and use mocked HTTP tests first; no Python inference bindings or in-process model loading.
- Next host class: Either host can begin R.6, but code-changing work must validate on both AMD64 and ARM64 or record an explicit degraded/skipped reason.

### 2026-06-17 13:37 -05:00 — R.5 AMD64 code-change leg

- Active slice/sub-slice: Slice R / R.5 sidecar lifecycle service.
- Last worked on: Windows AMD64.
- Most recent change: Extended `backend/app/services/local_llm_sidecar.py` with `LocalLLMSidecarService`, an idempotent lifecycle wrapper around the R.4 command builder. It owns mocked/injectable process start, stop, restart, status, PID, last command, selected profile metadata, last degraded/error reason, restart-required reporting for changed model/profile, and health probe delegation. It does not change `LlamaCppLLM`, runtime selection, model/profile selection, or HTTP generation.
- Validation run: Focused R.5 pytest passed (`25 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260617183734-regression.txt`); `git diff --check` passed with line-ending warnings only. Fingerprint: `arch=amd64 python=3.12.10 extras=[hw-cpu-base,hw-x64-base,hw-gpu-nvidia-cuda,dev] readiness=ready`.
- Note: Unit tests use mocked process creation only. No model artifact was downloaded, no real sidecar process was launched, runtime selection was not changed, and no `SYSTEM_INVENTORY.md` update was made. R.5 is not complete until Windows ARM64 validates the same lifecycle behavior or records an explicit degraded/skipped reason.
- Next needed: Windows ARM64 should run focused R.5 pytest, regression, and diff check against the same changes. Confirm idempotent lifecycle behavior and restart-required reporting on ARM64.
- Next host class: Windows ARM64.

### 2026-06-17 13:31 -05:00 — R.4 ARM64 validation leg

- Active slice/sub-slice: Slice R / R.4 sidecar command builder.
- Last worked on: Windows ARM64.
- Most recent change: Validated the already-landed R.4 command-builder behavior on ARM64 without product code changes. `backend/app/services/local_llm_sidecar.py` returns argv-style `llama-server` command plans only, covers ARM64 CPU command construction, warns on unsupported launch keys/values, and closes ARM64 QNN missing binary as degraded without launching a process.
- Validation run: Focused R.4 pytest passed (`24 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260617183058-regression.txt`). Fingerprint: `arch=arm64 python=3.13.13 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`.
- Note: R.4 is now validated on both AMD64 and ARM64 according to the tandem host rule. No model artifact was downloaded, no sidecar process was launched, runtime selection was not changed, and no `SYSTEM_INVENTORY.md` update was made.
- Next needed: Start R.5 sidecar lifecycle service. Lifecycle work must remain separate from model/profile selection and HTTP generation, use mocked process creation in tests, and stay idempotent.
- Next host class: Either host can begin R.5, but code-changing work must validate on both AMD64 and ARM64 or record an explicit degraded/skipped reason.

### 2026-06-17 13:28 -05:00 — R.4 AMD64 code-change leg

- Active slice/sub-slice: Slice R / R.4 sidecar command builder.
- Last worked on: Windows AMD64.
- Most recent change: Added `backend/app/services/local_llm_sidecar.py` as a command-builder-only service helper. It consumes `LLMServeProfileResolution` and returns an argv-style `llama-server` command plan with `--model`, `--host`, `--port`, supported launch tuning, warnings for unsupported launch keys/values, and degraded states for missing binary/model paths. It does not launch a process.
- Validation run: Focused R.4 pytest passed (`17 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260617182749-regression.txt`); `git diff --check` passed. Fingerprint: `arch=amd64 python=3.12.10 extras=[hw-cpu-base,hw-x64-base,hw-gpu-nvidia-cuda,dev] readiness=ready`.
- Note: No model artifact was downloaded, no sidecar process was launched, runtime selection was not changed, and no `SYSTEM_INVENTORY.md` update was made. R.4 is not complete until Windows ARM64 validates the same command-builder behavior or records an explicit degraded/skipped reason.
- Next needed: Windows ARM64 should run focused R.4 pytest, regression, and diff check against the same changes. Confirm ARM64 CPU command construction and ARM64 QNN degraded command behavior.
- Next host class: Windows ARM64.

### 2026-06-17 13:22 -05:00 — R.3 ARM64 validation leg

- Active slice/sub-slice: Slice R / R.3 local LLM serve profile resolution.
- Last worked on: Windows ARM64.
- Most recent change: Validated the already-landed R.3 resolver behavior on ARM64 without product code changes. `backend/app/models/llm_profiles.py` selects `windows_arm64_cpu` first for the current host, reports missing local GGUF and missing `llama-server.exe` as degraded evidence, and keeps ARM64 QNN as a degraded/skipped candidate until viable binary/model/runtime evidence exists.
- Validation run: Focused R.3 pytest passed (`21 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260617182208-regression.txt`). Fingerprint: `arch=arm64 python=3.13.13 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`.
- Note: R.3 is now validated on both AMD64 and ARM64 according to the tandem host rule. No model artifact was downloaded, no sidecar command was built, runtime selection was not changed, and no `SYSTEM_INVENTORY.md` update was made.
- Next needed: Start R.4 sidecar command builder. It must consume the selected serve profile and return an argv-style command list only; no process launch.
- Next host class: Either host can begin R.4, but code-changing work must validate on both AMD64 and ARM64 or record an explicit degraded/skipped reason.

### 2026-06-17 13:15 -05:00 — R.3 AMD64 code-change leg

- Active slice/sub-slice: Slice R / R.3 local LLM serve profile resolution.
- Last worked on: Windows AMD64.
- Most recent change: Added `backend/app/models/llm_profiles.py` as a resolution-only helper under model/catalog ownership. It selects the current host CPU-only llama.cpp serve profile, returns model id, route, profile id, model path, binary path, base URL, accelerator, launch tuning, generation defaults, selected reason, and degraded evidence. Missing local GGUF and missing `llama-server.exe` report degraded reasons; AMD64 CUDA and ARM64 QNN remain degraded/skipped candidates until later binary/model/runtime evidence exists.
- Validation run: Focused R.3 pytest passed (`20 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260617181533-regression.txt`); `git diff --check` passed. Fingerprint: `arch=amd64 python=3.12.10 extras=[hw-cpu-base,hw-x64-base,hw-gpu-nvidia-cuda,dev] readiness=ready`.
- Note: No model artifact was downloaded, no sidecar command was built, runtime selection was not changed, and no `SYSTEM_INVENTORY.md` update was made. R.3 is not complete until Windows ARM64 validates the same resolver behavior or records an explicit degraded/skipped reason.
- Next needed: Windows ARM64 should run focused R.3 pytest, regression, and diff check against the same changes. Confirm ARM64 CPU profile selection and QNN skipped/degraded candidate behavior.
- Next host class: Windows ARM64.

### 2026-06-17 13:09 -05:00 — R.2 ARM64 validation leg

- Active slice/sub-slice: Slice R / R.2 local LLM model artifact fetch and verification.
- Last worked on: Windows ARM64.
- Most recent change: Validated the already-landed R.2 catalog/script behavior on ARM64 without product code changes. `config/models/llm.yaml` selects `qwen2.5-0.5b-instruct-q4_k_m.gguf`; `scripts/ensure_models.py --family llm --verify-only` reports the missing GGUF as `Degraded-no-local-model-artifact`; dry-run plans the selected artifact without download.
- Validation run: Focused R.2 pytest passed (`16 passed`); `backend\.venv\Scripts\python scripts\ensure_models.py --family llm --verify-only` returned expected nonzero degraded state; `backend\.venv\Scripts\python scripts\ensure_models.py --family llm --dry-run` passed; `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260617180737-regression.txt`). Fingerprint: `arch=arm64 python=3.13.13 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`.
- Note: R.2 is now validated on both AMD64 and ARM64 according to the tandem host rule. No model artifact was downloaded, no sidecar/runtime validation was attempted, and no `SYSTEM_INVENTORY.md` update was made.
- Next needed: Start R.3 local LLM serve profile resolution. Selection must start with the current host CPU-only profile; AMD64 CUDA and ARM64 QNN remain degraded/skipped until profiler/preflight, binary, and artifact evidence support them.
- Next host class: Either host can begin R.3, but code-changing work must validate on both AMD64 and ARM64 or record an explicit degraded/skipped reason.

### 2026-06-17 13:04 -05:00 — R.2 AMD64 code-change leg

- Active slice/sub-slice: Slice R / R.2 local LLM model artifact fetch and verification.
- Last worked on: Windows AMD64.
- Most recent change: Pointed `config/models/llm.yaml` at the selected lower-quant Qwen2.5 0.5B Instruct GGUF artifact (`qwen2.5-0.5b-instruct-q4_k_m.gguf`) and extended the existing `scripts/ensure_models.py` catalog acquisition/verification path to handle single-file LLM artifacts. LLM verify now reports missing local GGUF as `Degraded-no-local-model-artifact`; dry-run reports the planned artifact without downloading.
- Validation run: Focused R.2 pytest passed (`16 passed`); `backend\.venv\Scripts\python scripts\ensure_models.py --family llm --verify-only` produced the expected degraded/nonzero missing-artifact state; `backend\.venv\Scripts\python scripts\ensure_models.py --family llm --dry-run` passed and planned `qwen2.5-0.5b-instruct-q4_k_m.gguf`; `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`119 passed, 4 deselected`, report `reports\validation\20260617180423-regression.txt`). Fingerprint: `arch=amd64 python=3.12.10 extras=[hw-cpu-base,hw-x64-base,hw-gpu-nvidia-cuda,dev] readiness=ready`.
- Note: No model artifact was downloaded, no sidecar/runtime validation was attempted, and no `SYSTEM_INVENTORY.md` update was made. R.2 is not complete until Windows ARM64 validates the same catalog/script behavior or records an explicit degraded/skipped reason.
- Next needed: Windows ARM64 should run focused R.2 pytest, `ensure_models.py --family llm --verify-only`, `ensure_models.py --family llm --dry-run`, regression, and diff check against the same changes.
- Next host class: Windows ARM64.

### 2026-06-17 12:57 -05:00 — R.1 ARM64 validation leg

- Active slice/sub-slice: Slice R / R.1 local LLM settings and catalog shape.
- Last worked on: Windows ARM64.
- Most recent change: Validated the already-landed R.1 settings and catalog shape on ARM64 without product code changes. `config/models/llm.yaml` defaults to lower-quant `assistant-small-q4`, includes `windows_arm64_cpu`, keeps `windows_arm64_qnn` as `declared-degraded` with `SKIP-no-viable-binary`, and keeps llama.cpp declarative only.
- Validation run: Focused R.1 pytest passed (`30 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`116 passed, 4 deselected`, report `reports\validation\20260617175623-regression.txt`). Fingerprint: `arch=arm64 python=3.13.13 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`.
- Note: R.1 is now validated on both AMD64 and ARM64 according to the tandem host rule. No `SYSTEM_INVENTORY.md` update; R.1 added declarative shape/settings only and did not activate local llama.cpp runtime behavior.
- Next needed: Start R.2 local LLM model artifact fetch and verification. Do not launch or validate a sidecar before R.2 verifies or degrades the selected lower-quant GGUF artifact path.
- Next host class: Either host can begin R.2, but code-changing work must validate on both AMD64 and ARM64 or record an explicit degraded/skipped reason.

### 2026-06-17 11:55 -05:00 — R.1 AMD64 code-change leg

- Active slice/sub-slice: Slice R / R.1 local LLM settings and catalog shape.
- Last worked on: Windows AMD64.
- Most recent change: Added llama.cpp sidecar settings, expanded `.env.example`, replaced `config/models/llm.yaml` with an existing-catalog-compatible `default_model`/`models` shape, declared lower-quant `assistant-small-q4` as the development target, added AMD64/ARM64 CPU-only serve profiles, kept AMD64 CUDA and ARM64 QNN as evidence-gated placeholders, and moved the SearXNG default to `8888`.
- Validation run: Focused R.1 pytest passed (`24 passed`); `backend\.venv\Scripts\python scripts\validate_backend.py regression` passed (`116 passed, 4 deselected`, report `reports\validation\20260617165457-regression.txt`); `git diff --check` passed with line-ending warnings only. Full `validate_backend.py unit` is blocked by unrelated agent ledger ordering assertions outside R.1.
- Note: Agent ledger ordering issue is recorded in `bug_fix.md`; proposed fix is separate from Slice R.1.
- Next needed: Windows ARM64 should validate the same R.1 files and behavior, especially settings parsing, catalog loading, ARM64 CPU profile shape, accelerator placeholder truth, regression, and diff check. Do not start R.2 until ARM64 records R.1 validation or a justified degraded/skipped reason.
- Next host class: Windows ARM64.

### 2026-06-17 11:45 -05:00 — R.0 hardware/binary census closed on ARM64

- Active slice/sub-slice: Slice R / R.0 hardware and binary evidence census.
- Last worked on: Windows ARM64.
- Most recent change: Non-mutating census closeout. Current host is ARM64 Windows laptop, 10 logical cores, 15.61 GB RAM, Qualcomm NPU present, QNN available, CUDA unavailable, DirectML candidate true. Existing AMD64 handoff evidence records a Windows AMD64 laptop with NVIDIA RTX 3060 12 GB VRAM, CUDA available, Intel NPU present, QNN unavailable, and local/GPU/CUDA LLM flags true.
- Validation run: `backend\.venv\Scripts\python scripts\validate_backend.py profile` passed on ARM64. Fingerprint: `arch=arm64 python=3.13.13 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready`.
- R.0 notes: Upstream llama.cpp release `b9682` lists Windows x64 CPU and Windows arm64 CPU assets, so CPU-only sidecar binaries are viable without source compilation for both target host classes. It also lists Windows x64 CUDA 12/13, Vulkan, OpenVINO, SYCL, and HIP assets. No Windows arm64 QNN sidecar asset was observed, so ARM64 NPU/QNN remains declared/degraded only. Repo state still has local llama.cpp not wired: `config/models/llm.yaml` marks `local.state: not_wired`, `LlamaCppLLM` is unavailable/NotImplemented, and `scripts/ensure_models.py` treats LLM as `ollama_manages_models`.
- R.0 close state: Windows AMD64 CPU-only `PASS-binary-available`; Windows ARM64 CPU-only `PASS-binary-available`; Windows AMD64 GPU/CUDA candidate `PASS-binary-available-not-runtime-validated`; Windows ARM64 NPU/QNN candidate `SKIP-no-viable-binary`.
- Chosen direction before R.1: proceed with a JARVIS-managed external `llama-server`-class sidecar, with Ollama retained as existing fallback and model-manager path until later sub-slices wire repo-managed GGUF artifacts.
- Next needed: Start R.1 local LLM settings and catalog shape. Continue one sub-slice at a time and preserve AMD64/ARM64 evidence separately.
- Next host class: Windows AMD64 or Windows ARM64 can start R.1, but any code-changing sub-slice must validate on both host classes or record an explicit degraded/skipped reason.

### 2026-06-17 11:34 -05:00 — R.0 hardware/binary census on AMD64

- Active slice/sub-slice: Slice R / R.0 hardware and binary evidence census.
- Last worked on: Windows AMD64.
- Most recent change: Non-mutating census only. Current host is AMD64 Windows laptop, 24 logical cores, 63.7 GB RAM, NVIDIA RTX 3060 12 GB VRAM, CUDA available, Intel NPU present, QNN unavailable. `supports_local_llm`, `supports_gpu_llm`, and `supports_cuda_llm` are true; `directml_candidate` is true.
- Validation run: `backend\.venv\Scripts\python scripts\validate_backend.py profile` passed. Fingerprint: `arch=amd64 python=3.12.10 extras=[hw-cpu-base,hw-x64-base,hw-gpu-nvidia-cuda,dev] readiness=ready`.
- R.0 notes: Upstream llama.cpp latest release observed Windows x64 CPU, Windows arm64 CPU, Windows x64 CUDA 12/13, Windows x64 Vulkan, Windows x64 SYCL, and Windows x64 HIP assets. No Windows arm64 QNN sidecar asset was observed. Repo state confirms `config/models/llm.yaml` still marks local llama.cpp as `state: not_wired`, `LlamaCppLLM` is still unavailable/NotImplemented, and `scripts/ensure_models.py` still treats LLM as `ollama_manages_models`.
- Next needed: Windows ARM64 must run the same R.0 profile/preflight census and confirm CPU-only binary viability before R.0 closeout. R.1/R.2 must handle catalog shape and lower-quant model artifact fetch/verification before any sidecar/runtime validation.
- Next host class: Windows ARM64.

### 2026-06-16 14:15 -05:00 — Slice R dependency-order correction

- Active slice/sub-slice: Group R planning; no implementation sub-slice active yet.
- Last worked on: Windows AMD64.
- Most recent change: Reworked Group R to require hardware/profile evidence and model artifact fetch/verification before sidecar/runtime validation; clarified tandem AMD64/ARM64 closeout rules.
- Validation run: `git diff --check` passed on Windows AMD64; Git reported only LF-to-CRLF normalization notice for `slices.md`.
- Next needed: Begin R.0 hardware/binary census before any implementation work.
- Next host class: Windows AMD64 can continue R.0; Windows ARM64 must validate the same sub-slice before closeout.

### 2026-06-16 12:12 -05:00 — Slice R planning update

- Active slice/sub-slice: Group R planning; no implementation sub-slice active yet.
- Last worked on: Windows AMD64.
- Most recent change: Integrated Decisions 1-10 into Group R in `slices.md` and added this handoff shape.
- Validation run: `git diff --check` passed on Windows AMD64; Git reported only LF-to-CRLF normalization notice for `slices.md`.
- Next needed: Start R.0/R.1 only after choosing the next approved sub-slice.
- Next host class: Windows AMD64 can continue planning; Windows ARM64 should pick up once CPU-only profile/validation work begins.
