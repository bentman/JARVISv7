# Replace Whisper QNN Model for Windows ARM64

This sheet covers replacing the Whisper QNN model artifact in JARVISv7 when the installed
`onnxruntime` / `onnxruntime-qnn` version has moved ahead of the QAIRT version the current
model was compiled against. It does not automate repo setup and does not modify JARVISv7
runtime code.

The expected output is a replacement model staged at:

```text
models\stt\whisper-base-en-qnn-snapdragon-x-elite\
```

containing freshly compiled `encoder.onnx`, `decoder.onnx`, and matching
`*_qairt_context.bin` files built against the QAIRT version bundled with the installed
`onnxruntime-qnn` package.

## When to Run This

Run this procedure when:

- `validate_backend.py profile` confirms `ep:QNNExecutionProvider` is present but live
  STT transcription produces empty or garbled output.
- `metadata.json` in the staged model directory shows an `onnx_runtime` version older than
  the installed `onnxruntime` package (check `backend\.venv\Lib\site-packages\onnxruntime-*.dist-info`).
- The `onnxruntime-qnn` package has been upgraded and the existing context binaries were
  compiled against a prior QAIRT version.

Symptom: `_qnn.log` in the repo root shows HTP execute records (NPU ran) but transcripts
are empty — the binary loaded but the compiled graph is mismatched to the runtime.

## Version Check

From the repo root:

```powershell
# Installed runtime versions
Get-ChildItem backend\.venv\Lib\site-packages | Where-Object Name -Like "onnxruntime*dist-info" | Select-Object Name

# Compiled model version
Get-Content models\stt\whisper-base-en-qnn-snapdragon-x-elite\*\metadata.json |
    Select-String "onnx_runtime"
```

If the `onnx_runtime` field in `metadata.json` is older than the installed `onnxruntime`
package, proceed.

## Target Machine

The export step requires an **x64 machine** (Windows x64 or Linux x86-64).
`qai_hub_models` explicitly requires AMD64 Python and will fail on ARM64 Python.

The Surface ARM64 device itself is used only to receive and validate the new model files
after the export completes.

Qualcomm AI Hub account is required. Register at:

> https://aihub.qualcomm.com

After registration, retrieve your API token from the account dashboard and run:

```powershell
qai-hub configure --api_token <YOUR_API_TOKEN>
```

## Workspace Layout

Keep the export workspace outside the repo. This example uses:

```powershell
$jarvisRoot    = "D:\WORK\CODE\GitHub\bentman\Repositories\JARVISv7"
$exportWorkDir = "D:\WORK\jarvis-dev\whisper-qnn"
if (!(Test-Path $exportWorkDir)) { New-Item -ItemType Directory -Force $exportWorkDir }
```

## Check for a Pre-Built Zip First

Before running a full AI Hub export job, probe whether a newer pre-built zip exists for the
current AI Hub Models release. The URL pattern is:

```
https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/models/whisper_base/releases/<VERSION>/whisper_base-precompiled_qnn_onnx-float-qualcomm_snapdragon_x_elite.zip
```

Replace `<VERSION>` with the next release tag above `v0.53.1` (e.g. `v0.54.0`, `v0.55.0`).

```powershell
# Probe — 200 means the zip exists; 403/404 means it does not.
$version = "v0.54.0"
$url = "https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/models/whisper_base/releases/$version/whisper_base-precompiled_qnn_onnx-float-qualcomm_snapdragon_x_elite.zip"
try {
    $response = Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing
    Write-Host "Found: $($response.StatusCode) $url"
} catch {
    Write-Host "Not found: $url"
}
```

If a valid zip is found, download it directly and skip to **Stage the Model** below.
If no newer pre-built zip is found, proceed with the AI Hub export.

## Recommended Helper Script

From the repo root on an x64 machine, run the checked-in operator helper:

```powershell
.\docs\jarvis-arm-whisper.ps1
```

The helper installs `qai_hub_models`, exports encoder and decoder as
`precompiled_qnn_onnx` for Snapdragon X Elite, downloads the resulting zip, and
stages the contents under the repo model path. Use the manual sections below when
you need to inspect or rerun individual phases.

## Install Export Tooling (x64 Machine)

Use a plain x64 Python environment — not the ARM64 repo venv:

```powershell
# Use x64 Python (not backend\.venv)
python -m venv $exportWorkDir\.venv-x64
$exportWorkDir\.venv-x64\Scripts\python -m pip install --upgrade pip
$exportWorkDir\.venv-x64\Scripts\pip install "qai_hub_models[whisper-base]"
```

Configure AI Hub credentials:

```powershell
$exportWorkDir\.venv-x64\Scripts\qai-hub configure --api_token <YOUR_API_TOKEN>
```

Verify:

```powershell
$exportWorkDir\.venv-x64\Scripts\qai-hub --version
$exportWorkDir\.venv-x64\Scripts\python -c "import qai_hub_models; print('ok')"
```

## Export Encoder and Decoder

Run encoder and decoder exports separately. Each submits a compile job to AI Hub,
waits for completion, and downloads the result into `$exportWorkDir\output`.

```powershell
$exportWorkDir\.venv-x64\Scripts\python -m qai_hub_models.models.whisper_base.export `
    --chipset qualcomm-snapdragon-x-elite `
    --target-runtime precompiled_qnn_onnx `
    --components WhisperEncoder `
    --output-dir "$exportWorkDir\output"

$exportWorkDir\.venv-x64\Scripts\python -m qai_hub_models.models.whisper_base.export `
    --chipset qualcomm-snapdragon-x-elite `
    --target-runtime precompiled_qnn_onnx `
    --components WhisperDecoder `
    --output-dir "$exportWorkDir\output"
```

Job progress is visible at https://app.aihub.qualcomm.com/jobs/ while the export runs.

Expected output under `$exportWorkDir\output`:

```text
encoder.onnx
decoder.onnx
```

Each `.onnx` file wraps a precompiled QNN context binary for Snapdragon X Elite HTP v73.

## Verify Output Files

```powershell
Get-ChildItem "$exportWorkDir\output" | Select-Object Name, Length
```

Both `encoder.onnx` and `decoder.onnx` must be present and non-zero before staging.

## Stage the Model in JARVISv7

The repo model path for this model is:

```text
models\stt\whisper-base-en-qnn-snapdragon-x-elite\
```

`stt.yaml` expects `encoder.onnx` and `decoder.onnx` to be discoverable anywhere under
that path (the runtime uses `rglob`). Place output files in a dated subdirectory to
preserve the provenance and make rollback straightforward.

```powershell
$dateTag     = Get-Date -Format "yyyyMMdd"
$modelSubDir = "$jarvisRoot\models\stt\whisper-base-en-qnn-snapdragon-x-elite\whisper_base-precompiled_qnn_onnx-$dateTag"
New-Item -ItemType Directory -Force $modelSubDir | Out-Null

Copy-Item "$exportWorkDir\output\encoder.onnx" "$modelSubDir\encoder.onnx" -Force
Copy-Item "$exportWorkDir\output\decoder.onnx" "$modelSubDir\decoder.onnx" -Force

Write-Host "Staged model files in: $modelSubDir"
```

Remove or archive the previous subdirectory to avoid stale files being picked up:

```powershell
Get-ChildItem "$jarvisRoot\models\stt\whisper-base-en-qnn-snapdragon-x-elite" -Directory |
    Where-Object FullName -NE $modelSubDir |
    ForEach-Object {
        Write-Host "Removing old model directory: $($_.FullName)"
        Remove-Item $_.FullName -Recurse -Force
    }
```

Do not commit compiled model artifacts. They are covered by `.gitignore`.

## Update stt.yaml

Update the `url` field under `whisper-base-en-qnn-snapdragon-x-elite` in
`config/models/stt.yaml` to reflect the new release version used for the export. This
keeps `ensure_models.py` pointing at a reproducible source for future provisioning:

```yaml
source:
  type: url_zip
  url: https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/models/whisper_base/releases/<NEW_VERSION>/whisper_base-precompiled_qnn_onnx-float-qualcomm_snapdragon_x_elite.zip
```

If no new pre-built zip exists for the release used (export was done via AI Hub job),
leave the `url` at the highest confirmed version and note the discrepancy in a comment.

## Validate on the ARM64 Device

Run from the repo root on the Surface with the repo virtual environment:

```powershell
# Confirm model files are found
backend\.venv\Scripts\python scripts\ensure_models.py --family stt --verify-only

# Confirm QNN EP and HTP tokens still present
backend\.venv\Scripts\python scripts\validate_backend.py profile

# Unit and regression
backend\.venv\Scripts\python scripts\validate_backend.py unit
backend\.venv\Scripts\python scripts\validate_backend.py regression
```

Expected:

- `ensure_models.py` reports STT model present.
- `profile` output includes `ep:QNNExecutionProvider` (no `:MISSING`), `dll:QnnHtp`,
  `qnn:provider_library_registered`.
- `unit` and `regression` pass.

Live QNN STT gate (requires microphone and speaker):

```powershell
$env:JARVISV7_LIVE_TESTS = "1"
backend\.venv\Scripts\python -m pytest backend\tests\runtime\hardware\test_qnn_gate_live.py -q
```

Required live evidence:

- `QNNExecutionProvider` is primary provider for both encoder and decoder sessions.
- Transcript is non-empty for the test audio input.
- No `[QNN_STT_DEBUG]` output (those prints are scaffolding to be removed separately).

## Troubleshooting

- **Export fails: `Installation will fail when using Windows ARM64 Python`** — run the
  export on an x64 machine or in a separate x64 Python installation; ARM64 Python is not
  supported by `qai_hub_models`.
- **AI Hub job fails: device not found** — confirm `qualcomm-snapdragon-x-elite` is a
  valid chipset identifier; alternatively use `--device "Snapdragon X Elite CRD"` instead
  of `--chipset`.
- **`encoder.onnx` or `decoder.onnx` not found after export** — check component names;
  the model class may use `WhisperEncoder` / `WhisperDecoder` or `HfWhisperEncoder` /
  `HfWhisperDecoder` depending on the `qai_hub_models` version. Run
  `python -m qai_hub_models.models.whisper_base.export --help` to list available components.
- **Sessions load but transcript is empty after staging** — confirm the old subdirectory
  was removed so `rglob` does not pick up stale context binaries from the previous version.
- **`ep:QNNExecutionProvider:MISSING` after staging** — the model replacement did not
  affect provider registration; re-run `validate_backend.py profile` and confirm
  `qnn:provider_library_registered` is present. If missing, re-run
  `scripts/provision.py verify`.

## Citations

- Qualcomm AI Hub Models, `whisper_base` model page and export CLI.
  https://aihub.qualcomm.com/models/whisper_base
- Qualcomm AI Hub Models GitHub, `qai_hub_models/models/whisper_base/`.
  https://github.com/qualcomm/ai-hub-models
- ONNX Runtime QNN Execution Provider documentation, context binary compatibility note.
  https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html
