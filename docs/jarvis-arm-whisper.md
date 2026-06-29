# JARVIS ARM Whisper QNN Artifact Helper

This document explains how to use `docs\jarvis-arm-whisper.ps1` to prepare or inspect a Qualcomm QNN Whisper artifact package for JARVISv7.

The normal workflow has two hosts:

- **AMD64 Windows host:** creates, inspects, exports, or downloads a portable artifact package.
- **ARM64 Snapdragon host:** stages the package into JARVIS and proves QNN execution.

The helper is intentionally conservative. It does not modify runtime/provider code, and it does not stage files into `models\stt` from the AMD64 host.

## Output

The only intended repo-side handoff artifact from the AMD64 helper is a zip under:

```text
docs\temp\
```

The final ARM64 model identity is:

```text
whisper-qualcomm-qnn
```

The final ARM64 staging folder is:

```text
models\stt\whisper-qualcomm-qnn
```

This side-by-side model is separate from the older `whisper-base-en-qnn-snapdragon-x-elite` entry.

## Requirements

For AMD64 package generation or download:

- Windows AMD64 host.
- Local JARVISv7 clone.
- Python launcher `py`.
- Internet access.
- Qualcomm AI Hub / Workbench account when contacting Workbench.
- Qualcomm AI Hub API token when exporting or downloading Workbench artifacts.

For ARM64 runtime validation:

- Windows ARM64 Snapdragon host.
- Repo ARM64 environment: `backend\.venv`.
- QNN provider readiness with `QNNExecutionProvider` and `QnnHtp.dll` available.
- The prepared zip copied or present under `docs\temp`.

## Qualcomm account setup

A Qualcomm account is required for Workbench export and completed-artifact download. It is not required for `-InspectOnly` or local dry-run checks.

Use Qualcomm's account and API-token flow:

```text
https://aihub.qualcomm.com/get-started
```

The important pieces are:

1. Create or sign into a Qualcomm ID.
2. Open AI Hub / Workbench account settings.
3. Copy your AI Hub API token.
4. Set it in the PowerShell session before running any Workbench command.

```powershell
$env:QAI_HUB_API_TOKEN = "<YOUR_API_TOKEN>"
```

The helper writes the local AI Hub client config for the current Windows user when an API token is present. Do not commit tokens or generated config files.

## Safety model

The default behavior is safe. The helper can create a local package and manifest without submitting remote Qualcomm work.

Workbench export is intentionally gated. It only runs when both are true:

```powershell
-RunWorkbenchExport
```

and the operator types:

```text
RUN-WORKBENCH-EXPORT
```

A Workbench export creates remote Qualcomm jobs and model records. This is expected behavior. Use it only when a new export is needed.

Completed-artifact download does not create new remote jobs. It downloads already-created Workbench models by captured IDs or explicit job/model IDs.

## Common commands

Run from the JARVIS repo root.

Inspect only:

```powershell
.\docs\jarvis-arm-whisper.ps1 -InspectOnly
```

Dry run:

```powershell
.\docs\jarvis-arm-whisper.ps1 -WhatIf
```

Default local package run, with no Workbench export:

```powershell
.\docs\jarvis-arm-whisper.ps1
```

Create a new Workbench export:

```powershell
$env:QAI_HUB_API_TOKEN = "<YOUR_API_TOKEN>"
.\docs\jarvis-arm-whisper.ps1 -RunWorkbenchExport
```

Download already-completed artifacts from a captured ID file:

```powershell
$env:QAI_HUB_API_TOKEN = "<YOUR_API_TOKEN>"
.\docs\jarvis-arm-whisper.ps1 -DownloadCompletedArtifacts -workbenchIdsInputPath "<PATH_TO_WORKBENCH_IDS_JSON>"
```

Download already-completed artifacts from explicit IDs:

```powershell
$env:QAI_HUB_API_TOKEN = "<YOUR_API_TOKEN>"
.\docs\jarvis-arm-whisper.ps1 -DownloadCompletedArtifacts -encoderModelId "<ENCODER_MODEL_ID>" -decoderModelId "<DECODER_MODEL_ID>"
```

If a job ID is known, it may also be supplied. Model IDs are usually less error-prone when downloading final optimized artifacts.

## What the helper creates

The helper keeps Qualcomm work outside the repo by default:

```text
<exportRoot>\.venv-qualcomm
<exportRoot>\output\...
```

The repo receives only the final zip package:

```text
docs\temp\jarvis-whisper-qualcomm-qnn-YYYYMMDDHHMMSS.zip
```

A package normally includes:

```text
manifest.json
pip-freeze.txt
export\
```

A completed-artifact download should include encoder and decoder QNN artifacts somewhere under `export\`:

```text
encoder\...\model.onnx
encoder\...\model.bin
decoder\...\model.onnx
decoder\...\model.bin
```

The `.onnx` files are small ONNX Runtime EPContext wrappers. The compiled QNN model payload is in the paired `.bin` files.

## ARM64 staging layout

On the ARM64 Snapdragon host, stage the selected encoder and decoder artifacts into the side-by-side model folder:

```text
models\stt\whisper-qualcomm-qnn\encoder\model.onnx
models\stt\whisper-qualcomm-qnn\encoder\model.bin
models\stt\whisper-qualcomm-qnn\decoder\model.onnx
models\stt\whisper-qualcomm-qnn\decoder\model.bin
models\stt\whisper-qualcomm-qnn\provenance\manifest.json
```

Keep the older QNN model folder unchanged unless a separate approved slice changes it:

```text
models\stt\whisper-base-en-qnn-snapdragon-x-elite
```

## ARM64 validation

Run validation from the repo root on the ARM64 host.

```powershell
backend\.venv\Scripts\python scripts\validate_backend.py profile
backend\.venv\Scripts\python scripts\ensure_models.py --family stt --model whisper-qualcomm-qnn --verify-only
$env:JARVISV7_LIVE_TESTS = "1"
backend\.venv\Scripts\python -m pytest backend\tests\runtime\hardware\test_qnn_gate_live.py -q
$env:JARVISV7_LIVE_TESTS = "1"
backend\.venv\Scripts\python -m pytest backend\tests\runtime\voice\test_stt_live.py -q -k "qnn and whisper_qualcomm_qnn"
backend\.venv\Scripts\python scripts\validate_backend.py unit
backend\.venv\Scripts\python scripts\validate_backend.py regression
```

Required evidence:

- `profile` reports `ep:QNNExecutionProvider`.
- `profile` reports `dll:QnnHtp`.
- `ensure_models` reports `whisper-qualcomm-qnn` ready.
- Encoder and decoder sessions load with QNN primary and CPU fallback disabled.
- Live QNN STT transcript test passes.
- Unit and regression validation pass.

## Workbench cleanup

If an export is interrupted, Workbench may still contain jobs and model records. This is normal.

Use the Workbench UI to inspect the timestamp cluster for the aborted run. Cancel active jobs first. Delete only records that clearly belong to the aborted run and are not needed for a packaged artifact.

Typical generated records include:

```text
job_*_optimized_onnx
job_*.onnx
job_*.bin
job_*.dlc
hf_whisper_encoder.pt
hf_whisper_decoder.pt
```

Do not delete shared or older records unless they are clearly from the run being cleaned up.

## Troubleshooting

- Missing API token: set `QAI_HUB_API_TOKEN` before Workbench export or download.
- Workbench export skipped: pass `-RunWorkbenchExport` and type the confirmation phrase.
- Completed download skipped: pass `-DownloadCompletedArtifacts` with either an ID file or explicit IDs.
- Wrong job ID: retry with the target model ID from the Workbench Models page.
- Missing encoder/decoder ONNX and BIN files: stop and inspect the package layout before changing runtime code.
- ARM64 QNN session fails: do not accept CPU fallback. Capture the exact failure and confirm `QNNExecutionProvider` and `QnnHtp.dll` are present.

## References

Qualcomm AI Hub account setup and API token flow:

```text
https://aihub.qualcomm.com/get-started
```

Qualcomm AI Hub / Workbench documentation:

```text
https://workbench.aihub.qualcomm.com/docs/
```

Qualcomm `CompileJob` API reference:

```text
https://workbench.aihub.qualcomm.com/docs/hub/generated/qai_hub.CompileJob.html
```

Qualcomm `Model` API reference:

```text
https://workbench.aihub.qualcomm.com/docs/hub/generated/qai_hub.Model.html
```
