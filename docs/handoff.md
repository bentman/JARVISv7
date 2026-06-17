# Cross-Device Handoff

This file preserves enough context for another device or Codex session to continue without chat history. Add a new timestamped entry at the top before switching devices or ending work that another host class should continue. Keep entries short and evidence-focused. User normally handles git push/pull.

## Entries

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
