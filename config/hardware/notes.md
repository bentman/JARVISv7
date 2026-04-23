# Hardware Operator Notes

Human-readable prerequisites for hardware-family extras. Package sets live
in `pyproject.toml` under `[project.optional-dependencies]`; this file holds
only the non-pip artifacts and environment configuration that an operator
must supply per host.

Vendor-specific gating that PEP 508 environment markers cannot express
(NPU vendor detection, CUDA availability) is applied by
`backend/app/hardware/provisioning.py::resolve_required_extras()`.

---

## NVIDIA + CUDA (extra: `hw-gpu-nvidia-cuda`)

- NVIDIA driver installed and working (`nvidia-smi` returns without error).
- CUDA runtime libraries on PATH, including cuDNN and cuBLAS for the ONNX
  Runtime CUDA execution provider's required version.
- On Windows, `backend/app/hardware/preflight.py` owns DLL discovery and
  `os.add_dll_directory` calls. No runtime file touches these.

## AMD GPU (extra: `hw-gpu-amd`)

- On Windows: DirectML runtime is part of Windows 10 1903+. Verify with
  `dxdiag` that the GPU reports a Feature Level of 12_0 or higher.
- On Linux: ROCm deferred to slice H.3. Package set will be populated then.

## Intel GPU (extra: `hw-gpu-intel`)

- On Windows: DirectML path. Same prerequisites as AMD Windows entry above.
- Integrated Intel GPUs (UHD / Iris Xe) work on DirectML but are
  substantially slower than discrete GPUs.

## Qualcomm NPU / QNN (extra: `hw-npu-qualcomm-qnn`)

Slot defined in slice A.6; inference wired in H.2.

- **QAIRT SDK** installed by the operator. Download from Qualcomm and set
  the SDK root path via environment variable.
- Backend HTP DLL (`QnnHtp.dll`) must be discoverable; preflight owns the
  discovery logic. Operator supplies the absolute path in `.env`:
  - `QAIRT_SDK_PATH=<absolute path to QAIRT root>`
- Quantized Whisper ONNX / QNN context-binary models are **generated on
  an x64 host** per ONNX Runtime QNN documentation. The `onnx` package
  has install issues on ARM64; quantization tooling must run on x64.
- Platform: Windows ARM64 only for now. `onnxruntime-qnn>=2.0.0` publishes
  `win_arm64` wheels for CPython 3.11 / 3.12 / 3.13 per PyPI listing.

## Wake — openWakeWord (primary; base install)

- No operator setup for the default. The pre-trained `hey_jarvis` model
  is acquired by `scripts/ensure_models.py` from the openWakeWord v0.5.1
  release URLs (model file + companion `melspectrogram.onnx` +
  `embedding_model.onnx`).
- Model files are `.onnx` — architecture-independent across Windows x64
  and Windows ARM64.
- Custom "jarvis"-only (no "hey" prefix) training is deferred. When done,
  it is a Linux / WSL / Colab operator task: openWakeWord's automated
  training pipeline depends on Piper TTS, which is Linux-only.

## Wake — Porcupine (extra: `hw-wake-porcupine`)

Optional alternative runtime.

- **PICOVOICE_ACCESS_KEY**: required. Set via `.env`. Obtain free dev-tier
  key from Picovoice Console (one keyword at a time for free tier).
- **PVPORCUPINE_MODEL_PATH**: path to custom `.ppn` keyword file if a
  custom keyword is used. Built-in English "jarvis" does not need a
  `.ppn`; pass `keywords=['jarvis']` instead.
- Custom `.ppn` files are platform-optimized at training time in
  Picovoice Console. Whether a single Windows `.ppn` covers both x64 and
  ARM64 is not definitively documented — plan for per-arch files and
  validate with Picovoice support before committing to a single file.

## TTS — Kokoro (base install on all hosts)

- `kokoro-onnx` is a pure-Python wheel installable on both x64 and ARM64.
- Phonemizer dependency: `espeak-ng` may be required by the ONNX pipeline
  depending on chosen voice pack. Install via:
  - Windows: <https://github.com/espeak-ng/espeak-ng/releases> (MSI installer)
  - Linux: `apt install espeak-ng` or distro equivalent
- Model files (`kokoro-v1.0.onnx` + `voices-v1.0.bin`) acquired by
  `scripts/ensure_models.py`.

## Desktop (Tauri) — per-arch developer prerequisites

Documented in `README.md` and `desktop/README.md`. Summary:

- **Windows x64 dev**: Rust stable, Node LTS, MSVC v143 build tools,
  WebView2 runtime.
- **Windows ARM64 dev**: Rust stable + `rustup target add aarch64-pc-windows-msvc`;
  Node LTS (ARM64 where available); **MSVC v143 — VS 2022 C++ ARM64 build
  tools** per Tauri's Windows installer docs; WebView2 runtime.
- Cross-compile x64 → ARM64: escape hatch via
  `tauri build --target aarch64-pc-windows-msvc --bundles nsis`. Not the
  primary dev path.

## Environment variables consumed at runtime

Set in `.env` at repo root (never commit `.env`; commit `.env.example` only).

- `APP_NAME` — identifier used in logging and traces.
- `CONFIG_PATH`, `DATA_PATH`, `MODEL_PATH` — filesystem roots.
- `USE_LOCAL_MODEL`, `LOCAL_MODEL_FETCH`, `LLAMA_CPP_MODEL_PATH` — local
  llama.cpp gating (activated in H.1).
- `USE_OLLAMA`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` — Ollama local LLM path.
- `TTS_MODELS`, `STT_MODELS`, `WAKE_MODEL` — model artifact roots.
- `PVPORCUPINE_MODEL_PATH`, `PICOVOICE_ACCESS_KEY` — Porcupine extra only.
- `QAIRT_SDK_PATH` — QNN extra only.
