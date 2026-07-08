# QNN NPU Acceleration for Kokoro TTS (ARM64 Handoff Guide)

This guide outlines the codebase changes and configuration steps required to enable hardware acceleration for Kokoro TTS using the Qualcomm QNN Execution Provider on Windows ARM64 (Snapdragon X Elite) devices.

---

## 1. Codebase Surface Changes

To enable QNN acceleration in the TTS runtime, two files need to be modified:

### A. TTS Runtime Layer
File: [kokoro_onnx_runtime.py](file:///e:/WORK/CODE/GitHub/bentman/Repositories/JARVISv7/backend/app/runtimes/tts/kokoro_onnx_runtime.py)

Add support for the QNN session creator in `_load_model()`. The structure should align with the Whisper STT runtime's use of `create_qnn_session`:

```python
    def _load_model(self) -> Any:
        if self._model is None:
            if not self.is_available():
                raise RuntimeError(f"TTS model files are unavailable at {self.model_path}")
            from kokoro_onnx import Kokoro
            import onnxruntime as rt

            provider_name = _provider_for_device(self.device)
            if provider_name == "QNNExecutionProvider":
                # Use the repo-owned QNN session creator utility
                from backend.app.hardware.qnn_provider import create_qnn_session
                # disable_cpu_fallback=False is recommended to allow unsupported operators to fall back
                session, _ = create_qnn_session(self.onnx_path, disable_cpu_fallback=False)
                self._model = Kokoro.from_session(session, str(self.voices_path))
            elif provider_name is not None:
                providers = [provider_name]
                if provider_name != "CPUExecutionProvider":
                    providers.append("CPUExecutionProvider")
                session = rt.InferenceSession(str(self.onnx_path), providers=providers)
                self._model = Kokoro.from_session(session, str(self.voices_path))
            else:
                self._model = Kokoro(str(self.onnx_path), str(self.voices_path))
        return self._model
```

### B. Hardware Readiness Layer
File: [readiness.py](file:///e:/WORK/CODE/GitHub/bentman/Repositories/JARVISv7/backend/app/hardware/readiness.py)

Update `derive_tts_device_readiness` to check for QNN capability flags and return `"qnn"` as the active device instead of failing closed to `"cpu"`:

```python
    # QNN on ARM64 Activation:
    if profile.npu_available and profile.npu_vendor == "qualcomm":
        qnn_tokens_present = all(
            _has_token(preflight, token)
            for token in (
                "import:onnxruntime-qnn",
                "ep:QNNExecutionProvider",
                "dll:QnnHtp",
            )
        )
        if qnn_tokens_present:
            return ("qnn", True, "qnn prerequisites proven; selecting qnn")
```

---

## 2. Model Compatibility (Critical)

Qualcomm Hexagon NPUs (HTP) generally do not execute standard FP32 ONNX models and will either fail session creation or force slow software fallbacks.
*   **Model Export:** Obtain or export an FP16-precision version of the Kokoro ONNX model (`kokoro-v1.0-fp16.onnx`).
*   **QNN Serialization (Optional):** Pre-compiling/serializing the ONNX model into a QNN context binary using Qualcomm QNN SDK command-line tools (`qnn-onnx-converter` and `qnn-model-lib-generator`) can be done to eliminate the startup compilation latency.

---

## 3. Execution Steps on ARM Device

1.  **Dependency Provisioning:**
    Run provisioning on the ARM target to ensure dependencies and platform-specific wheels are correctly resolved:
    ```powershell
    backend/.venv/Scripts/python scripts/provision.py
    ```
2.  **Model Setup:**
    Place the target FP16 model in the local model directory (`models/tts/kokoro-v1.0-onnx`) and ensure it matches the `onnx_path` configuration.
3.  **Run Unit and Readiness Tests:**
    Execute the unit test suite to verify that `qnn` is resolved as the selected device:
    ```powershell
    backend/.venv/Scripts/python -m pytest backend/tests/unit/runtimes/tts/test_tts_runtime.py
    backend/.venv/Scripts/python scripts/validate_backend.py unit
    ```
4.  **Confirm Selection:**
    Ensure `"qnn"` is listed as the selected TTS device in the startup readiness mapping:
    ```powershell
    backend/.venv/Scripts/python -c "from backend.app.services.startup_context import load_startup_context; print(load_startup_context().readiness['tts'])"
    ```
