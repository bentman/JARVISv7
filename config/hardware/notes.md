## ARM64 (Snapdragon X Elite) — Acceleration Chain

### STT device priority
1. QNN (Snapdragon X Elite HTP) — verified
   - Requires the `hw-npu-qualcomm-qnn` extra, QNN execution-provider readiness, QAIRT runtime libraries, and the QNN model artifact.
2. CPU — fallback when QNN prerequisites or artifacts are unavailable

### TTS device priority
1. QNN (Snapdragon X Elite HTP) — verified
   - Kokoro uses a QNN InferenceSession with CPU fallback enabled.
2. CPU — fallback when QNN readiness is unavailable

### LLM
- Managed llama.cpp is the primary local runtime; Windows ARM64 CPU and user-staged Adreno OpenCL paths are verified.
- QNN/Hexagon LLM acceleration remains unavailable. Ollama remains the fallback runtime.

### Wake
- openWakeWord (CPU) — primary; no hardware acceleration targeted

---

## x64 (Intel + NVIDIA) — Acceleration Chain

### STT device priority
1. CUDA — verified when the NVIDIA CUDA execution provider is ready
2. DirectML — supported when the DirectML execution provider is ready
3. CPU — fallback when accelerated providers are unavailable

### TTS device priority
1. CUDA — verified
2. DirectML — supported when the DirectML execution provider is ready
3. CPU — fallback when accelerated providers are unavailable

### LLM
- Managed llama.cpp CPU and NVIDIA CUDA serve paths are verified. Ollama remains the fallback runtime.

### Wake
- openWakeWord (CPU) — primary

### Non-pip prerequisites
- NVIDIA acceleration requires a compatible driver and CUDA toolkit discovered by preflight.
- Qualcomm QNN acceleration requires the QAIRT SDK/runtime libraries and `QAIRT_SDK_PATH` when automatic discovery is insufficient.
- Dependency selection and installation remain owned by `pyproject.toml` and `scripts/provision.py`; do not install runtime packages directly.
