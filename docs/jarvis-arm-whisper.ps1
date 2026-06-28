<#
.SYNOPSIS
Replace the Whisper QNN model for JARVISv7 Windows ARM64 Snapdragon X Elite.

.DESCRIPTION
Manual helper for replacing the JARVISv7 Whisper QNN model artifact when the installed
onnxruntime / onnxruntime-qnn version has moved ahead of the QAIRT version the current
model was compiled against.

Run this script on an x64 machine (Windows x64 or Linux x86-64). The qai_hub_models
tooling requires AMD64 Python and will fail on ARM64 Python.

The script installs qai_hub_models into a local x64 venv, exports encoder and decoder
as precompiled_qnn_onnx for Snapdragon X Elite via Qualcomm AI Hub, downloads the
results, and stages them under the repo model path.

.NOTES
Qualcomm AI Hub account and API token required. Register at https://aihub.qualcomm.com
then configure: qai-hub configure --api_token <YOUR_API_TOKEN>

Run from PowerShell on the x64 machine before copying model files to the ARM64 device.

.PARAMETER JarvisRoot
Path to the JARVISv7 repository root.

.PARAMETER ExportWorkDir
Path to the external developer workspace for the x64 venv and export output.

.PARAMETER AiHubToken
Qualcomm AI Hub API token. If omitted, the script uses the token already configured
in the local qai-hub profile (from a prior `qai-hub configure` call).

.PARAMETER TranscriptPath
Path to the command transcript. Defaults under ExportWorkDir.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Low')]
param(
    [string] $JarvisRoot    = "D:\WORK\CODE\GitHub\bentman\Repositories\JARVISv7",
    [string] $ExportWorkDir = "D:\WORK\jarvis-dev\whisper-qnn",
    [string] $AiHubToken   = "",
    [string] $TranscriptPath = ""
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FilePath,

        [string[]] $Arguments = @()
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Description,

        [Parameter(Mandatory = $true)]
        [ScriptBlock] $Action
    )

    if ($PSCmdlet.ShouldProcess($Description)) {
        Write-Host ""
        Write-Host "==> $Description"
        & $Action
    }
    else {
        Write-Host "WhatIf: $Description"
    }
}

if (-not (Test-Path $JarvisRoot)) {
    throw "JARVISv7 root does not exist: $JarvisRoot"
}

if (-not (Test-Path $ExportWorkDir)) {
    New-Item -ItemType Directory -Force -Path $ExportWorkDir | Out-Null
}

$JarvisRoot    = (Resolve-Path $JarvisRoot).Path
$ExportWorkDir = (Resolve-Path $ExportWorkDir).Path

if ([string]::IsNullOrWhiteSpace($TranscriptPath)) {
    $TranscriptPath = Join-Path $ExportWorkDir "$(Get-Date -Format yyyyMMddHHmmss)_jarvis-arm-whisper-transcript.txt"
}

$venvDir   = Join-Path $ExportWorkDir ".venv-x64"
$venvPy    = Join-Path $venvDir "Scripts\python.exe"
$venvPip   = Join-Path $venvDir "Scripts\pip.exe"
$outputDir = Join-Path $ExportWorkDir "output"

$modelRoot   = Join-Path $JarvisRoot "models\stt\whisper-base-en-qnn-snapdragon-x-elite"
$dateTag     = Get-Date -Format "yyyyMMdd"
$modelSubDir = Join-Path $modelRoot "whisper_base-precompiled_qnn_onnx-$dateTag"

Start-Transcript -Path $TranscriptPath -Force
try {
    Write-Host "JARVISv7 root:     $JarvisRoot"
    Write-Host "Export work dir:   $ExportWorkDir"
    Write-Host "Output dir:        $outputDir"
    Write-Host "Model staging dir: $modelSubDir"
    Write-Host "Transcript:        $TranscriptPath"

    # -------------------------------------------------------------------------
    Invoke-Step "Verify x64 Python is available" {
        $pyPath = (Get-Command python.exe -ErrorAction Stop).Source
        $arch   = & python.exe -c "import platform; print(platform.machine())"
        Write-Host "Python: $pyPath"
        Write-Host "Arch:   $arch"
        if ($arch -notmatch "AMD64|x86_64") {
            throw "x64 Python required for qai_hub_models export. Found arch: $arch"
        }
    }

    # -------------------------------------------------------------------------
    Invoke-Step "Create x64 venv" {
        if (-not (Test-Path $venvPy)) {
            Invoke-Native "python.exe" @("-m", "venv", $venvDir)
        }
        else {
            Write-Host "Venv already exists: $venvDir"
        }
        Invoke-Native $venvPy @("-m", "pip", "install", "--upgrade", "pip", "--quiet")
    }

    # -------------------------------------------------------------------------
    Invoke-Step "Install qai_hub_models[whisper-base]" {
        Invoke-Native $venvPip @("install", "qai_hub_models[whisper-base]", "--quiet")
    }

    # -------------------------------------------------------------------------
    Invoke-Step "Configure Qualcomm AI Hub token" {
        if (-not [string]::IsNullOrWhiteSpace($AiHubToken)) {
            Invoke-Native (Join-Path $venvDir "Scripts\qai-hub.exe") @(
                "configure", "--api_token", $AiHubToken
            )
        }
        else {
            Write-Host "AiHubToken parameter not provided; using existing qai-hub profile."
            Write-Host "If export fails with auth errors, re-run with -AiHubToken <token>."
        }
    }

    # -------------------------------------------------------------------------
    Invoke-Step "Prepare output directory" {
        if (Test-Path $outputDir) {
            Remove-Item $outputDir -Recurse -Force
        }
        New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
    }

    # -------------------------------------------------------------------------
    Invoke-Step "Export WhisperEncoder (precompiled_qnn_onnx, Snapdragon X Elite)" {
        Invoke-Native $venvPy @(
            "-m", "qai_hub_models.models.whisper_base.export",
            "--chipset",        "qualcomm-snapdragon-x-elite",
            "--target-runtime", "precompiled_qnn_onnx",
            "--components",     "WhisperEncoder",
            "--output-dir",     $outputDir
        )
    }

    # -------------------------------------------------------------------------
    Invoke-Step "Export WhisperDecoder (precompiled_qnn_onnx, Snapdragon X Elite)" {
        Invoke-Native $venvPy @(
            "-m", "qai_hub_models.models.whisper_base.export",
            "--chipset",        "qualcomm-snapdragon-x-elite",
            "--target-runtime", "precompiled_qnn_onnx",
            "--components",     "WhisperDecoder",
            "--output-dir",     $outputDir
        )
    }

    # -------------------------------------------------------------------------
    Invoke-Step "Verify exported files" {
        $encoderPath = Join-Path $outputDir "encoder.onnx"
        $decoderPath = Join-Path $outputDir "decoder.onnx"

        if (-not (Test-Path $encoderPath)) {
            throw "encoder.onnx not found in output dir. Check component names with: python -m qai_hub_models.models.whisper_base.export --help"
        }
        if (-not (Test-Path $decoderPath)) {
            throw "decoder.onnx not found in output dir. Check component names with: python -m qai_hub_models.models.whisper_base.export --help"
        }

        $enc = Get-Item $encoderPath
        $dec = Get-Item $decoderPath
        Write-Host "encoder.onnx: $($enc.Length) bytes"
        Write-Host "decoder.onnx: $($dec.Length) bytes"

        if ($enc.Length -eq 0) { throw "encoder.onnx is empty" }
        if ($dec.Length -eq 0) { throw "decoder.onnx is empty" }
    }

    # -------------------------------------------------------------------------
    Invoke-Step "Remove stale model subdirectories" {
        Get-ChildItem $modelRoot -Directory -ErrorAction SilentlyContinue |
            ForEach-Object {
                Write-Host "Removing old model directory: $($_.FullName)"
                Remove-Item $_.FullName -Recurse -Force
            }
    }

    # -------------------------------------------------------------------------
    Invoke-Step "Stage new model files in JARVISv7" {
        New-Item -ItemType Directory -Force -Path $modelSubDir | Out-Null

        Copy-Item (Join-Path $outputDir "encoder.onnx") (Join-Path $modelSubDir "encoder.onnx") -Force
        Copy-Item (Join-Path $outputDir "decoder.onnx") (Join-Path $modelSubDir "decoder.onnx") -Force

        Write-Host "encoder.onnx -> $modelSubDir"
        Write-Host "decoder.onnx -> $modelSubDir"
    }

    # -------------------------------------------------------------------------
    Write-Host ""
    Write-Host "Export helper completed. Model files staged in:"
    Write-Host "  $modelSubDir"
    Write-Host ""
    Write-Host "Next steps (on the ARM64 device, from JARVISv7 repo root):"
    Write-Host "  1. Update config\models\stt.yaml url to match the new AI Hub release version."
    Write-Host "  2. backend\.venv\Scripts\python scripts\ensure_models.py --family stt --verify-only"
    Write-Host "  3. backend\.venv\Scripts\python scripts\validate_backend.py unit"
    Write-Host "  4. backend\.venv\Scripts\python scripts\validate_backend.py regression"
    Write-Host "  5. Set JARVISV7_LIVE_TESTS=1 and run test_qnn_gate_live.py"
}
finally {
    Stop-Transcript
}
