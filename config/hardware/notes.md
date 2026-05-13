## ARM64 (Snapdragon X Elite) — Acceleration Chain

### STT device priority
1. QNN (Snapdragon X Elite HTP)
   - Requires: hw-npu-qualcomm-qnn extra, ep:QNNExecutionProvider, dll:QnnHtp, artifact present
   - Proven: H.3 (2026-05-12)
2. CPU — fallback when any QNN prerequisite or artifact is missing

### TTS device priority
1. CPU — only proven path
   - kokoro_onnx.Kokoro does not expose a providers parameter (H.7)
   - Accelerated TTS deferred pending upstream package change

### LLM
- Ollama (local HTTP) — primary

### Wake
- openWakeWord (CPU) — primary; no hardware acceleration targeted

---

## x64 (Intel i9 + NVIDIA RTX 3060) — Acceleration Chain

### STT device priority
1. CUDA (NVIDIA RTX 3060)
   - Requires: hw-gpu-nvidia-cuda extra, ep:CUDAExecutionProvider
   - Proven: H.4 (2026-05-03)
2. DirectML — defined slot; currently SKIP-prereq-missing
   - DmlExecutionProvider not present in installed onnxruntime-gpu wheel (H.5 2026-05-13)
   - Gate test in place: backend/tests/runtime/hardware/test_directml_gate_live.py
   - See enabling procedure below
3. CPU — fallback when CUDA and DirectML both unproven

### TTS device priority
1. CPU — only proven path (H.7)

### LLM
- Ollama (local HTTP) — primary

### Wake
- openWakeWord (CPU) — primary

### Enabling DirectML (future operator action)
  pip install onnxruntime-directml
  $env:JARVISV7_LIVE_TESTS="true"
  python -m pytest backend/tests/runtime/hardware/test_directml_gate_live.py -q
If both tests PASS, update pyproject.toml hw-gpu extras and re-run I.2 normalization.