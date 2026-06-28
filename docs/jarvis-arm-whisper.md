# Export Whisper for Windows ARM64 Qualcomm QNN

This sheet is for end-user/manual export of a Qualcomm AI Hub Whisper Base English ONNX package for JARVISv7 Windows ARM64 QNN STT. It does not automate repo setup and does not modify JARVISv7 runtime code.

The expected output is a zip package stored at:

```text
docs\temp\jarvis-whisper-base-en-qaihub-onnx-snapdragon-x-YYYYMMDDHHMMSS.zip
```

The zip contains export output plus `manifest.json` and `pip-freeze.txt`. The package is not staged into `models\stt`.

## Target Machine

- Windows on ARM64.
- Qualcomm Snapdragon X Elite / X Plus system.
- JARVISv7 cloned locally.
- Qualcomm AI Hub account and API token.
- Python launcher `py` available for creating the external export venv.

The helper uses an external Qualcomm venv:

```text
$exportRoot\.venv-qualcomm
```

It does not use `backend\.venv`, does not use `requirements.txt`, and does not change ARM64 provisioning.

## Qualcomm AI Hub Research Basis

Qualcomm's Snapdragon X Elite AI Hub blog shows the AI Hub export pattern for
Whisper on `"Snapdragon X Elite CRD"`. The installed `qai_hub_models 0.56.0` package
exposes the Base model as `whisper_base` with the `whisper-base` extra, and its export
CLI supports `precompiled_qnn_onnx` for QNN-ready ONNX artifacts.

```powershell
pip install "qai_hub_models[whisper-base]"
python -m qai_hub_models.models.whisper_base.export --target-runtime precompiled_qnn_onnx --device "Snapdragon X Elite CRD" --components encoder decoder
```

Source:

```text
https://www.qualcomm.com/developer/blog/2025/05/deploy-ai-models-on-snapdragon-x-elite-with-qualcomm-ai-hub
```

## Repo Dependency Alignment

The script embeds the current JARVISv7 ARM64 QNN runtime package set from `pyproject.toml` and adds the Qualcomm export package:

```text
onnxruntime>=1.24.4; platform_machine=='ARM64' and sys_platform=='win32'
onnxruntime-qnn>=2.3.0; platform_machine=='ARM64' and sys_platform=='win32'
onnx>=1.16; platform_machine=='ARM64' and sys_platform=='win32'
transformers>=4.40; platform_machine=='ARM64' and sys_platform=='win32'
qai_hub_models[whisper-base]
```

If these cannot resolve together, stop and report the pip resolver output. Do not pin older ONNX Runtime versions, do not use `--no-deps`, and do not uninstall/reinstall the repo ARM64 QNN stack.

## Recommended Helper Script

From the repo root, run the checked-in operator helper:

```powershell
.\docs\jarvis-arm-whisper.ps1
```

The helper keeps Qualcomm export work under `D:\WORK\jarvis-dev\whisper-qnn`, creates or reuses `$exportRoot\.venv-qualcomm`, exports Whisper Base English ONNX artifacts through Qualcomm AI Hub, and writes the final zip under `docs\temp`.

Use the manual sections below when you need to inspect or rerun individual phases.

## Workspace Layout

Keep Qualcomm export work outside the repo. This example uses:

```powershell
$jarvisRoot = "D:\WORK\CODE\GitHub\bentman\Repositories\JARVISv7"
$exportRoot = "D:\WORK\jarvis-dev\whisper-qnn"
$venvDir = "$exportRoot\.venv-qualcomm"
$outputDir = "$exportRoot\output"
if (!(Test-Path $exportRoot)) {New-Item -ItemType Directory -Force $exportRoot}
```

The script writes only the final zip into the repo:

```text
$jarvisRoot\docs\temp\
```

## AI Hub Authentication

Register and retrieve an API token:

```text
https://aihub.qualcomm.com
```

Pass the token to the helper:

```powershell
$env:QAI_HUB_API_TOKEN = "<YOUR_API_TOKEN>"
.\docs\jarvis-arm-whisper.ps1
```

Or configure the external Qualcomm venv after it exists:

```powershell
D:\WORK\jarvis-dev\whisper-qnn\.venv-qualcomm\Scripts\qai-hub.exe configure --api_token <YOUR_API_TOKEN>
```

## Export Command Shape

The helper runs this export command from `$exportRoot\.venv-qualcomm`:

```powershell
$exportRoot\.venv-qualcomm\Scripts\python.exe -m qai_hub_models.models.whisper_base.export `
  --target-runtime precompiled_qnn_onnx `
  --device "Snapdragon X Elite CRD" `
  --components encoder decoder `
  --output-dir "$exportRoot\output\whisper-base-en-qaihub-onnx-snapdragon-x-<timestamp>\export"
```

Expected package zip name:

```text
docs\temp\jarvis-whisper-base-en-qaihub-onnx-snapdragon-x-YYYYMMDDHHMMSS.zip
```

Expected zip contents:

```text
export\
manifest.json
pip-freeze.txt
```

Before using the archive in JARVIS runtime selection, inspect whether `export\` contains the ONNX files expected by `QnnWhisperRuntime`:

```text
encoder.onnx
decoder.onnx
```

If Qualcomm's `whisper_base` ONNX export produces a different structure, record the produced layout before changing runtime/catalog code.

## Run

From repo root:

```powershell
$env:QAI_HUB_API_TOKEN = "<YOUR_API_TOKEN>"
.\docs\jarvis-arm-whisper.ps1
```

Dry run:

```powershell
.\docs\jarvis-arm-whisper.ps1 -WhatIf
```

`-WhatIf` prints the planned steps without creating `$exportRoot`, creating the venv,
installing packages, configuring AI Hub, exporting artifacts, or writing the zip.

Custom workspace:

```powershell
.\docs\jarvis-arm-whisper.ps1 `
  -jarvisRoot "D:\WORK\CODE\GitHub\bentman\Repositories\JARVISv7" `
  -exportRoot "D:\WORK\jarvis-dev\whisper-qnn" `
  -pythonExe "py"
```

## After Export

Do not commit generated zip files or extracted model artifacts unless repo policy is explicitly changed.

Use the zip as input for the next implementation step only after inspecting the produced `export\` layout. Runtime selection should not be changed until QNN encoder/decoder sessions load with `QNNExecutionProvider` primary and CPU fallback disabled for proof.

## ARM64 Runtime Validation After Staging

After a model is staged through the repo model-acquisition path, validate from repo root:

```powershell
backend\.venv\Scripts\python scripts\validate_backend.py profile
backend\.venv\Scripts\python scripts\ensure_models.py --family stt --verify-only
$env:JARVISV7_LIVE_TESTS = "1"
backend\.venv\Scripts\python -m pytest backend\tests\runtime\hardware\test_qnn_gate_live.py -q
$env:JARVISV7_LIVE_TESTS = "1"
backend\.venv\Scripts\python -m pytest backend\tests\runtime\voice\test_stt_live.py -q -k qnn
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

- Pip resolver conflict: stop and report the exact resolver output. Do not downgrade `onnxruntime` or `onnxruntime-qnn` silently.
- AI Hub auth failure: set `QAI_HUB_API_TOKEN` or configure `qai-hub.exe` in `$exportRoot\.venv-qualcomm`.
- Device name rejected: start with Qualcomm's `"Snapdragon X Elite CRD"` device name.
- Export produces no `encoder.onnx` / `decoder.onnx`: do not force runtime selection. Record the produced layout and update the next slice accordingly.

## Citations

- Qualcomm Developer Blog, "Deploy AI models on Snapdragon X Elite with Qualcomm AI Hub", May 14, 2025. Qualcomm documents the Snapdragon X Elite AI Hub export pattern using `--device "Snapdragon X Elite CRD"`.
- Local implementation evidence: `qai_hub_models 0.56.0` installed in `$exportRoot\.venv-qualcomm` provides the `whisper-base` extra, the `qai_hub_models.models.whisper_base.export` module, `precompiled_qnn_onnx`, and `encoder` / `decoder` components.
