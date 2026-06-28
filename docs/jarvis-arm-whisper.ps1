<#
.SYNOPSIS
Export Whisper Base English ONNX artifacts for JARVISv7 Windows ARM64 QNN.

.DESCRIPTION
Manual helper for creating a Qualcomm AI Hub Whisper export package for JARVISv7.
The script keeps the Qualcomm Python environment and export work outside the repo,
installs dependencies from the embedded package list, and writes the final zip under
docs\temp.

This script does not use requirements.txt and does not stage files into models\stt.

.NOTES
Qualcomm AI Hub account and API token required. Register at https://aihub.qualcomm.com
then set QAI_HUB_API_TOKEN or use a prior qai-hub configure call in this venv.

.PARAMETER jarvisRoot
Path to the JARVISv7 repository root.

.PARAMETER exportRoot
Path to the external developer workspace for the Qualcomm venv and export output.

.PARAMETER pythonExe
Python launcher used to create the external Qualcomm venv.

.PARAMETER transcriptPath
Path to the command transcript. Defaults under exportRoot.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Low')]
param(
    [string] $jarvisRoot = "E:\WORK\CODE\GitHub\bentman\Repositories\JARVISv7",
    [string] $exportRoot = "E:\WORK\jarvis-dev\whisper-qnn",
    [string] $pythonExe = "py",
    [string] $deviceName = "Snapdragon X Elite CRD",
    [string] $modelName = "whisper-base-en-qaihub-onnx-snapdragon-x",
    [string] $transcriptPath = ""
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$qualcommPackages = @(
    "onnxruntime>=1.24.4; platform_machine=='ARM64' and sys_platform=='win32'",
    "onnxruntime-qnn>=2.3.0; platform_machine=='ARM64' and sys_platform=='win32'",
    "onnx>=1.16; platform_machine=='ARM64' and sys_platform=='win32'",
    "transformers>=4.40; platform_machine=='ARM64' and sys_platform=='win32'",
    "qai_hub_models[whisper-base]"
)

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

if (-not (Test-Path $jarvisRoot)) {
    if ($WhatIfPreference) {
        Write-Host "WhatIf: JARVIS root does not exist on this host: $jarvisRoot"
    }
    else {
        throw "JARVIS root does not exist: $jarvisRoot"
    }
}

if (-not (Test-Path $exportRoot)) {
    Invoke-Step "Create export root" {
        New-Item -ItemType Directory -Force -Path $exportRoot | Out-Null
    }
}

if ([string]::IsNullOrWhiteSpace($transcriptPath)) {
    $transcriptPath = Join-Path $exportRoot "$(Get-Date -Format yyyyMMddHHmmss)_jarvis-arm-whisper-transcript.txt"
}

$venvDir = Join-Path $exportRoot ".venv-qualcomm"
$venvPy = Join-Path $venvDir "Scripts\python.exe"
$qaiHubExe = Join-Path $venvDir "Scripts\qai-hub.exe"
$timestamp = Get-Date -Format "yyyyMMddHHmmss"
$outputDir = Join-Path $exportRoot "output\$modelName-$timestamp"
$exportDir = Join-Path $outputDir "export"
$manifestPath = Join-Path $outputDir "manifest.json"
$pipFreezePath = Join-Path $outputDir "pip-freeze.txt"
$docsTemp = Join-Path $jarvisRoot "docs\temp"
$zipPath = Join-Path $docsTemp "jarvis-$modelName-$timestamp.zip"

$transcriptStarted = $false
if (-not $WhatIfPreference) {
    Start-Transcript -Path $transcriptPath -Force
    $transcriptStarted = $true
}
try {
    Write-Host "JARVIS root: $jarvisRoot"
    Write-Host "Export root: $exportRoot"
    Write-Host "Python exe: $pythonExe"
    Write-Host "Qualcomm venv: $venvDir"
    Write-Host "Output dir: $outputDir"
    Write-Host "Zip path: $zipPath"
    Write-Host "Transcript: $transcriptPath"

    Invoke-Step "Create Qualcomm export directories" {
        New-Item -ItemType Directory -Force -Path $exportDir | Out-Null
        New-Item -ItemType Directory -Force -Path $docsTemp | Out-Null
    }

    Invoke-Step "Create Qualcomm Python venv" {
        if (-not (Test-Path $venvPy)) {
            Invoke-Native $pythonExe @("-m", "venv", $venvDir)
        }
        else {
            Write-Host "Venv already exists: $venvDir"
        }
        Invoke-Native $venvPy @("-m", "pip", "install", "--upgrade", "pip")
    }

    Invoke-Step "Install embedded Qualcomm export dependencies" {
        $installArgs = @("-m", "pip", "install") + $qualcommPackages
        Invoke-Native $venvPy $installArgs
    }

    Invoke-Step "Configure Qualcomm AI Hub token" {
        if (-not [string]::IsNullOrWhiteSpace($env:QAI_HUB_API_TOKEN)) {
            Write-Host "Configuring Qualcomm AI Hub token from QAI_HUB_API_TOKEN."
            & $qaiHubExe @("configure", "--api_token", $env:QAI_HUB_API_TOKEN)
            if ($LASTEXITCODE -ne 0) {
                throw "qai-hub configure failed with exit code ${LASTEXITCODE}."
            }
        }
        else {
            Write-Host "No AI Hub token supplied; using existing qai-hub profile."
            Write-Host "If export fails with auth errors, set QAI_HUB_API_TOKEN and re-run."
        }
    }

    Invoke-Step "Export Whisper Base English ONNX artifacts" {
        Invoke-Native $venvPy @(
            "-m", "qai_hub_models.models.whisper_base.export",
            "--target-runtime", "precompiled_qnn_onnx",
            "--device", $deviceName,
            "--components", "encoder", "decoder",
            "--output-dir", $exportDir
        )
    }

    Invoke-Step "Record installed package versions" {
        & $venvPy -m pip freeze | Set-Content -Path $pipFreezePath -Encoding UTF8
        if ($LASTEXITCODE -ne 0) {
            throw "pip freeze failed with exit code ${LASTEXITCODE}"
        }
    }

    Invoke-Step "Write export manifest" {
        $manifest = [ordered]@{
            model_name     = $modelName
            created_utc    = (Get-Date).ToUniversalTime().ToString("o")
            jarvis_root    = $jarvisRoot
            export_root    = $exportRoot
            venv           = $venvDir
            device         = $deviceName
            target_runtime = "precompiled_qnn_onnx"
            export_module  = "qai_hub_models.models.whisper_base.export"
            packages       = $qualcommPackages
            output_dir     = $outputDir
            export_dir     = $exportDir
            zip_path       = $zipPath
            source_blog    = "https://www.qualcomm.com/developer/blog/2025/05/deploy-ai-models-on-snapdragon-x-elite-with-qualcomm-ai-hub"
        }

        $manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $manifestPath -Encoding UTF8
    }

    Invoke-Step "Create zip package in docs\temp" {
        Compress-Archive -Path (Join-Path $outputDir "*") -DestinationPath $zipPath -Force
        $zipItem = Get-Item $zipPath
        if ($zipItem.Length -le 0) {
            throw "Zip package was created with zero bytes: $zipPath"
        }
    }

    Write-Host ""
    if ($WhatIfPreference) {
        Write-Host "WhatIf completed. Package would be written to:"
        Write-Host "  $zipPath"
    }
    else {
        Write-Host "Export helper completed. Package written to:"
        Write-Host "  $zipPath"
    }
}
finally {
    if ($transcriptStarted) {
        Stop-Transcript
    }
}
