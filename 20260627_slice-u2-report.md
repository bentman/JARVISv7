# Slice U2 Status Report: Active QNN Acceleration

## Scope

This report records the current Slice U2 state only. No U2 changelog entry has been written.

## Files Changed During U2

- `backend/app/hardware/qnn_provider.py`
- `backend/app/hardware/preflight.py`
- `backend/tests/unit/hardware/test_qnn_provider.py`
- `backend/tests/unit/hardware/test_preflight.py`
- `backend/tests/unit/hardware/test_qnn_slot.py`
- `backend/tests/unit/hardware/test_qnn_prerequisite.py`
- `backend/tests/unit/hardware/test_provisioning.py`

## Implemented Behavior

- Added an idempotent QNN provider activation helper in `backend/app/hardware/qnn_provider.py`.
- The helper imports `onnxruntime_qnn`, discovers the package library path, adds the package directory to the Windows DLL search path, and registers `QNNExecutionProvider` through `onnxruntime.register_execution_provider_library(...)`.
- Preflight now calls the activation helper before probing `onnxruntime.get_available_providers()` on Qualcomm QNN profiles.
- Preflight records observable activation evidence:
  - `qnn:provider_library_registered`
  - `QNNProvider:added:<onnxruntime_qnn package dir>`
  - `QNNProvider:library:<onnxruntime_providers_qnn.dll>`
- `create_qnn_session()` now attempts QNN provider activation before constructing a QNN session.
- Test fixtures were aligned to the split package shape:
  - `onnxruntime` is modeled as the provider/session API package.
  - `onnxruntime_qnn` is modeled as the QNN package root and provider-library source.
- Renamed `test_qnn_expected_requirement_specs_pin_ort_family` to `test_qnn_expected_requirement_specs_include_paired_ort_family`.

## Evidence Collected

### Package / Provider Investigation

Command:

```powershell
backend\.venv\Scripts\python -c "import onnxruntime as ort; print('ort', ort.__version__); print('providers', ort.get_available_providers()); import onnxruntime_qnn as qnn; print('qnn_file', qnn.__file__)"
```

Observed:

```text
ort 1.27.0
providers ['AzureExecutionProvider', 'CPUExecutionProvider']
qnn_file ...\backend\.venv\Lib\site-packages\onnxruntime_qnn\__init__.py
```

Command:

```powershell
backend\.venv\Scripts\python -c "import onnxruntime_qnn as qnn; print([name for name in dir(qnn) if 'path' in name.lower() or 'library' in name.lower() or 'provider' in name.lower()]); print(qnn.__file__)"
```

Observed:

```text
['LIB_DIR_FULL_PATH', '__path__', 'get_library_path', 'get_qnn_cpu_path', 'get_qnn_gpu_path', 'get_qnn_htp_path']
```

Command:

```powershell
backend\.venv\Scripts\python -c "from pathlib import Path; import onnxruntime_qnn as qnn; root=Path(qnn.__file__).resolve().parent; print(root); print([str(p) for p in root.rglob('*.dll')]); print('lib', qnn.get_library_path()); print('htp', qnn.get_qnn_htp_path())"
```

Observed package files included:

```text
onnxruntime_providers_qnn.dll
QnnCpu.dll
QnnGpu.dll
QnnHtp.dll
QnnSystem.dll
```

### In-Process Activation Probe

Command:

```powershell
backend\.venv\Scripts\python -c "import os; import onnxruntime as ort; import onnxruntime_qnn as qnn; print('before', ort.get_available_providers()); os.add_dll_directory(str(qnn.LIB_DIR_FULL_PATH)); ort.register_execution_provider_library('QNNExecutionProvider', qnn.get_library_path()); print('after', ort.get_available_providers())"
```

Observed:

```text
before ['AzureExecutionProvider', 'CPUExecutionProvider']
after ['AzureExecutionProvider', 'CPUExecutionProvider', 'QNNExecutionProvider']
```

### Focused Unit Validation

Command:

```powershell
backend\.venv\Scripts\python -m pytest backend\tests\unit\hardware\test_qnn_provider.py backend\tests\unit\hardware\test_preflight.py backend\tests\unit\hardware\test_qnn_slot.py backend\tests\unit\hardware\test_qnn_prerequisite.py backend\tests\unit\hardware\test_provisioning.py backend\tests\unit\runtimes\stt\test_stt_runtime.py -q
```

Observed:

```text
59 passed in 0.36s
```

### ARM64 Profile Validation

Command:

```powershell
backend\.venv\Scripts\python scripts\validate_backend.py profile
```

Observed:

```text
[fingerprint] arch=arm64 python=3.13.14 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready; tokens=21
```

Relevant tokens:

```text
qnn:provider_library_registered
ep:QNNExecutionProvider
import:onnxruntime-qnn
qnn:backend_path:...\backend\.venv\Lib\site-packages\onnxruntime_qnn\QnnHtp.dll
dll:QnnHtp
```

Relevant discovery log:

```text
QNNProvider:added:...\backend\.venv\Lib\site-packages\onnxruntime_qnn
QNNProvider:library:...\backend\.venv\Lib\site-packages\onnxruntime_qnn\onnxruntime_providers_qnn.dll
QnnHtp:added:...\backend\.venv\Lib\site-packages\onnxruntime_qnn
```

### Live QNN Hardware Gate

Command:

```powershell
set JARVISV7_LIVE_TESTS=1
backend\.venv\Scripts\python -m pytest backend\tests\runtime\hardware\test_qnn_gate_live.py -q
```

Observed:

```text
2 passed in 0.72s
```

### Live QNN STT Transcript Gate

Command:

```powershell
set JARVISV7_LIVE_TESTS=1
backend\.venv\Scripts\python -m pytest backend\tests\runtime\voice\test_stt_live.py -q -k qnn
```

Observed:

```text
1 failed, 2 deselected
```

Failure:

```text
This session contains graph nodes that are assigned to the default CPU EP,
but fallback to CPU EP has been explicitly disabled by the user.
```

The failing model was:

```text
models\stt\whisper-base-en-qnn-snapdragon-x-elite\...\encoder.onnx
```

## Model Artifact Observations

The QNN STT artifact directory contains small ONNX wrappers plus large QAIRT context sidecars:

```text
encoder.onnx
encoder_qairt_context.bin
decoder.onnx
decoder_qairt_context.bin
metadata.json
```

The ONNX wrappers each contain one `EPContext` node:

```text
encoder.onnx: nodes=1, ops=['EPContext'], epcontext=1
decoder.onnx: nodes=1, ops=['EPContext'], epcontext=1
```

The EPContext nodes reference adjacent context files:

```text
encoder_qairt_context.bin
decoder_qairt_context.bin
```

Temporary local probes that added EPContext metadata such as `main_context=1`, `source`, and `ep_context_type` did not make `QNNExecutionProvider` claim the node. Those probes were not committed.

## Current State

- QNN provider activation is implemented and proven at profile level.
- `QNNExecutionProvider` is now visible to ONNX Runtime after preflight activation.
- Live QNN hardware gate passes.
- Active QNN STT transcript proof does not pass.
- The blocker is no longer provider registration; it is QNN session initialization for the current precompiled STT EPContext model.

## Explicit Non-Actions

- No U2 changelog entry was written.
- No dependency downgrade, pin, or `<1.25` constraint was applied.
- No `pyproject.toml`, provisioning dependency, or install workaround was changed for U2 beyond the prior Slice U state.
- No model artifacts were modified.
