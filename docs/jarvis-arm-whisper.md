# Export Whisper Fixture for Windows ARM64 Qualcomm QNN

This sheet is for AMD64-host fixture generation for later JARVISv7 Windows ARM64 QNN validation. It does not modify runtime/provider code and does not stage files into `models\stt`.

The only intended JARVIS artifact is a zip package stored at:

```text
docs\temp\jarvis-whisper-qualcomm-qnn-YYYYMMDDHHMMSS.zip
```

The zip contains local output under the external export workspace, including `manifest.json`, `pip-freeze.txt`, and any downloaded Qualcomm Workbench export files when export is explicitly enabled.

## Target Machine

- Windows AMD64 fixture host for export/package creation.
- Python launcher `py` available for creating the external export venv.
- Qualcomm AI Hub / Workbench account only when running Workbench export.
- JARVISv7 cloned locally.

The helper uses an external Qualcomm venv:

```text
$exportRoot\.venv-qualcomm
```

It does not use `backend\.venv`, does not use `requirements.txt`, does not change ARM64 provisioning, and does not stage files into `models\stt`.

The intended ARM64 side-by-side model identity is:

```text
whisper-qualcomm-qnn
```

The intended ARM64 staging folder is:

```text
models\stt\whisper-qualcomm-qnn
```

This is separate from the existing `whisper-base-en-qnn-snapdragon-x-elite` entry.

## Safety Model

Default behavior is safe: the helper creates a local package and manifest but does not call Qualcomm Workbench export and does not download remote artifacts.

Workbench export is gated by both:

```powershell
-RunWorkbenchExport
```

and a typed confirmation:

```text
RUN-WORKBENCH-EXPORT
```

Without both, the script never calls:

```powershell
qai_hub_models.models.whisper_base.export
```

Use `-InspectOnly` to write an inspection manifest/zip without creating the venv, installing packages, configuring AI Hub, or running Workbench export.

Use `-RunWorkbenchExport` to submit the encoder/decoder compile jobs through Qualcomm Workbench. The helper captures job/model IDs from Workbench output into `workbench-ids.json` when they are visible in command output.

Use `-DownloadCompletedArtifacts` to download completed Workbench encoder/decoder artifacts without creating new remote jobs. IDs must come from `workbench-ids.json` or explicit parameters.

## Qualcomm AI Hub / Workbench Basis

Qualcomm documents AI Hub / Workbench setup and model export workflows at:

```text
https://aihub.qualcomm.com/get-started
https://workbench.aihub.qualcomm.com/docs/
```

Local implementation evidence from the installed `qai_hub_models 0.56.0` package:

```powershell
pip install "qai_hub_models[whisper-base]"
python -m qai_hub_models.models.whisper_base.export --help
```

The installed exporter exposes:

```text
--target-runtime precompiled_qnn_onnx
--components encoder decoder
--device "Snapdragon X Elite CRD"
```

The helper follows Qualcomm's configured-client model: write
`%USERPROFILE%\.qai_hub\client.ini` from `QAI_HUB_API_TOKEN`, use the `qai_hub`
Python client, retrieve completed jobs/models, call `target.download(...)`, extract
downloaded zips, and package the local output.

## Qualcomm API Environment

Set the API token in the process environment before any command that contacts Workbench:

```powershell
$env:QAI_HUB_API_TOKEN = "<YOUR_API_TOKEN>"
```

The helper writes this to:

```text
%USERPROFILE%\.qai_hub\client.ini
```

with:

```text
api_url = https://workbench.aihub.qualcomm.com
web_url = https://workbench.aihub.qualcomm.com
client_mode = cli
```

The helper also sets these for Python child processes:

```text
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
```

Those avoid Windows console encoding failures when Workbench status output includes Unicode characters.

## Dependency Alignment

The script embeds the current JARVISv7 ARM64 QNN runtime package set from `pyproject.toml` and adds the Qualcomm export package:

```text
onnxruntime>=1.24.4; platform_machine=='ARM64' and sys_platform=='win32'
onnxruntime-qnn>=2.3.0; platform_machine=='ARM64' and sys_platform=='win32'
onnx>=1.16; platform_machine=='ARM64' and sys_platform=='win32'
transformers>=4.40; platform_machine=='ARM64' and sys_platform=='win32'
qai_hub_models[whisper-base]
```

On AMD64, the ARM64-only runtime requirements are marker-skipped. Do not pin older ONNX Runtime versions, do not use `--no-deps`, and do not uninstall/reinstall the repo ARM64 QNN stack.

## Workspace Layout

Keep Qualcomm export work outside the repo. This helper defaults to:

```powershell
$jarvisRoot = "E:\WORK\CODE\GitHub\bentman\Repositories\JARVISv7"
$exportRoot = "E:\WORK\jarvis-dev\whisper-qnn"
$venvDir = "$exportRoot\.venv-qualcomm"
$outputDir = "$exportRoot\output\whisper-qualcomm-qnn-<timestamp>"
```

The helper writes only the final zip into the repo:

```text
$jarvisRoot\docs\temp\
```

## Recommended Safe Commands

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

Workbench export run:

```powershell
$env:QAI_HUB_API_TOKEN = "<YOUR_API_TOKEN>"
.\docs\jarvis-arm-whisper.ps1 -RunWorkbenchExport
```

The script will still require the operator to type:

```text
RUN-WORKBENCH-EXPORT
```

before creating remote Qualcomm jobs/models.

This submits compile/export work to Qualcomm Workbench with:

```text
--target-runtime precompiled_qnn_onnx
--components encoder decoder
--skip-profiling
--skip-inferencing
```

The helper records discovered IDs in:

```text
workbench-ids.json
```

Download already-completed artifacts from a captured ID file:

```powershell
$env:QAI_HUB_API_TOKEN = "<YOUR_API_TOKEN>"
.\docs\jarvis-arm-whisper.ps1 `
  -DownloadCompletedArtifacts `
  -workbenchIdsInputPath "E:\WORK\jarvis-dev\whisper-qnn\output\<run>\workbench-ids.json"
```

Download already-completed artifacts from explicit IDs:

```powershell
$env:QAI_HUB_API_TOKEN = "<YOUR_API_TOKEN>"
.\docs\jarvis-arm-whisper.ps1 `
  -DownloadCompletedArtifacts `
  -encoderJobId "<ENCODER_JOB_ID>" `
  -encoderModelId "<ENCODER_MODEL_ID>" `
  -decoderJobId "<DECODER_JOB_ID>" `
  -decoderModelId "<DECODER_MODEL_ID>"
```

If a job ID is not available but the model ID is known, leave that job ID blank and pass the model ID. The downloader tries job target-model download first, then falls back to model download.

## Export Command Shape

When `-RunWorkbenchExport` is confirmed, the helper runs:

```powershell
$exportRoot\.venv-qualcomm\Scripts\python.exe -m qai_hub_models.models.whisper_base.export `
  --target-runtime precompiled_qnn_onnx `
  --device "Snapdragon X Elite CRD" `
  --components encoder decoder `
  --skip-profiling `
  --skip-inferencing `
  --output-dir "$exportRoot\output\whisper-qualcomm-qnn-<timestamp>\export"
```

During the Workbench export process, the helper writes:

```text
workbench-export.stdout.txt
workbench-export.stderr.txt
workbench-ids.json
download-monitor.txt
```

The download monitor records the export directory file count and byte total while the Workbench export process is running.

During completed-artifact download, the helper writes:

```text
workbench-download.stdout.txt
workbench-download.stderr.txt
download-monitor.txt
download-completed-artifacts.py
```

The download monitor records the export directory file count and byte total while the
download process is running.

## Manifest

`manifest.json` includes:

- timestamp
- JARVIS model name
- JARVIS model path
- recommended ARM64 staging layout
- output directory
- export directory
- zip path
- exact command
- `inspect_only`
- `workbench_export_requested`
- `completed_artifact_download_requested`
- encoder/decoder job and model IDs
- `workbench_ids_path`
- `workbench_ids_input_path`
- captured Workbench job/model IDs, when discoverable from command output
- stdout/stderr paths
- download stdout/stderr paths
- download monitor path

## Expected Zip Contents

For inspect/default local package runs:

```text
manifest.json
pip-freeze.txt
export\
```

For confirmed Workbench export runs, `export\` should also contain Qualcomm-produced artifacts. Before using the archive in JARVIS runtime selection, inspect whether `export\` contains the ONNX files expected by `QnnWhisperRuntime`:

```text
encoder\...\model.onnx
encoder\...\model.bin
decoder\...\model.onnx
decoder\...\model.bin
```

If Qualcomm's `whisper_base` export produces a different structure, record the produced layout before changing runtime/catalog code.

For completed-artifact downloads, the known-good package shape is:

```text
export\encoder\encoder_target.onnx.zip
export\encoder\extracted\job_jgooj3vkg_optimized_onnx\model.onnx
export\encoder\extracted\job_jgooj3vkg_optimized_onnx\model.bin
export\decoder\decoder_target.onnx.zip
export\decoder\extracted\job_jpvejvwrg_optimized_onnx\model.onnx
export\decoder\extracted\job_jpvejvwrg_optimized_onnx\model.bin
```

The intended ARM64 staged model layout is:

```text
models\stt\whisper-qualcomm-qnn\encoder\model.onnx
models\stt\whisper-qualcomm-qnn\encoder\model.bin
models\stt\whisper-qualcomm-qnn\decoder\model.onnx
models\stt\whisper-qualcomm-qnn\decoder\model.bin
```

Keep `whisper-base-en-qnn-snapdragon-x-elite` side-by-side and unchanged unless a separate approved slice changes it.

## ARM64 Runtime Validation After Staging

After a future model-acquisition step stages the package through repo-approved paths, validate from repo root on ARM64:

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

Required live evidence:

- `profile` includes `ep:QNNExecutionProvider`.
- QNN hardware gate passes.
- QNN STT live transcript passes.
- CPU fallback remains disabled for QNN proof.
- Unit and regression validation pass.

## Troubleshooting

- Workbench export skipped: pass `-RunWorkbenchExport` and type `RUN-WORKBENCH-EXPORT`.
- Completed artifact download skipped: pass `-DownloadCompletedArtifacts` with `-workbenchIdsInputPath` or explicit job/model IDs.
- AI Hub auth failure: set `QAI_HUB_API_TOKEN` or configure `qai-hub.exe` in `$exportRoot\.venv-qualcomm`.
- Device name rejected: start with Qualcomm's `"Snapdragon X Elite CRD"` device name.
- Export produces no encoder/decoder `model.onnx` plus `model.bin`: do not force runtime selection. Record the produced layout and update the next slice accordingly.
