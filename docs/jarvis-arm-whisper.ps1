<#
.SYNOPSIS
Create a JARVISv7 Whisper/QNN export fixture package.

.DESCRIPTION
Manual helper for AMD64-host fixture generation. The script keeps Qualcomm
Workbench export work outside the repo and writes the only intended JARVIS artifact
as a zip under docs\temp. It never stages files into models\stt.

By default, this script does not call Qualcomm Workbench export. Use
-RunWorkbenchExport and confirm the warning prompt to create remote Qualcomm jobs/models.
Use -DownloadCompletedArtifacts to package completed Workbench models without creating
new remote jobs.

.PARAMETER jarvisRoot
Path to the JARVISv7 repository root.

.PARAMETER exportRoot
Path to the external developer workspace for the Qualcomm venv and export output.

.PARAMETER pythonExe
Python launcher used to create the external Qualcomm venv.

.PARAMETER InspectOnly
Write an inspection manifest/zip only. Do not create the venv, install packages,
configure AI Hub, or run Workbench export.

.PARAMETER RunWorkbenchExport
Allow the script to call qai_hub_models.models.whisper_base.export after explicit
typed confirmation. This creates remote Qualcomm Workbench jobs/models.

.PARAMETER DownloadCompletedArtifacts
Download completed Workbench encoder/decoder artifacts by IDs captured from the
current export output or supplied explicitly.

.PARAMETER workbenchIdsInputPath
Optional path to a workbench-ids.json file captured by an earlier export run.

.PARAMETER transcriptPath
Path to the command transcript. Defaults under exportRoot.
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Low')]
param(
    [string] $jarvisRoot = "E:\WORK\CODE\GitHub\bentman\Repositories\JARVISv7",
    [string] $exportRoot = "E:\WORK\jarvis-dev\whisper-qnn",
    [string] $pythonExe = "py",
    [string] $deviceName = "Snapdragon X Elite CRD",
    [string] $modelName = "whisper-base-en-qaihub-precompiled-qnn-onnx-snapdragon-x",
    [switch] $InspectOnly,
    [switch] $RunWorkbenchExport,
    [switch] $DownloadCompletedArtifacts,
    [string] $encoderJobId = "",
    [string] $decoderJobId = "",
    [string] $encoderModelId = "",
    [string] $decoderModelId = "",
    [string] $workbenchIdsInputPath = "",
    [string] $transcriptPath = ""
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"

# Keep Python child-process output UTF-8 so Workbench status glyphs do not fail on Windows.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# Runtime-aligned ARM64 QNN specs plus the Qualcomm export package.
$qualcommPackages = @(
    "onnxruntime>=1.24.4; platform_machine=='ARM64' and sys_platform=='win32'",
    "onnxruntime-qnn>=2.3.0; platform_machine=='ARM64' and sys_platform=='win32'",
    "onnx>=1.16; platform_machine=='ARM64' and sys_platform=='win32'",
    "transformers>=4.40; platform_machine=='ARM64' and sys_platform=='win32'",
    "qai_hub_models[whisper-base]"
)

# Derived package, export, transcript, and zip paths.
$timestamp = Get-Date -Format "yyyyMMddHHmmss"
$venvDir = Join-Path $exportRoot ".venv-qualcomm"
$venvPy = Join-Path $venvDir "Scripts\python.exe"
$outputDir = Join-Path $exportRoot "output\$modelName-$timestamp"
$exportDir = Join-Path $outputDir "export"
$manifestPath = Join-Path $outputDir "manifest.json"
$pipFreezePath = Join-Path $outputDir "pip-freeze.txt"
$exportStdoutPath = Join-Path $outputDir "workbench-export.stdout.txt"
$exportStderrPath = Join-Path $outputDir "workbench-export.stderr.txt"
$downloadStdoutPath = Join-Path $outputDir "workbench-download.stdout.txt"
$downloadStderrPath = Join-Path $outputDir "workbench-download.stderr.txt"
$downloadMonitorPath = Join-Path $outputDir "download-monitor.txt"
$workbenchIdsPath = Join-Path $outputDir "workbench-ids.json"
$docsTemp = Join-Path $jarvisRoot "docs\temp"
$zipPath = Join-Path $docsTemp "jarvis-$modelName-$timestamp.zip"
$exportCommand = @(
    $venvPy,
    "-m", "qai_hub_models.models.whisper_base.export",
    "--target-runtime", "precompiled_qnn_onnx",
    "--device", $deviceName,
    "--components", "encoder", "decoder",
    "--skip-profiling",
    "--skip-inferencing",
    "--output-dir", $exportDir
)
$jobIds = @()
$modelIds = @()

if ([string]::IsNullOrWhiteSpace($transcriptPath)) {
    $transcriptPath = Join-Path $exportRoot "$($timestamp)_jarvis-arm-whisper-transcript.txt"
}

# Run a native command and fail fast on non-zero exit.
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

# Run a named step through PowerShell ShouldProcess / -WhatIf.
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

# Write Qualcomm CLI config without BOM, matching Workbench client expectations.
function Write-QualcommConfig {
    if ([string]::IsNullOrWhiteSpace($env:QAI_HUB_API_TOKEN)) {
        Write-Host "No QAI_HUB_API_TOKEN supplied; using existing qai-hub profile if present."
        return
    }

    $configDir = Join-Path $env:USERPROFILE ".qai_hub"
    $configPath = Join-Path $configDir "client.ini"
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null
    if (Test-Path $configPath) {
        Copy-Item $configPath "$configPath.bak" -Force
    }

    $configText = @"
[api]
api_token = $($env:QAI_HUB_API_TOKEN)
api_url = https://workbench.aihub.qualcomm.com
web_url = https://workbench.aihub.qualcomm.com
verbose = False
client_mode = cli
"@

    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($configPath, $configText, $utf8NoBom)
    Write-Host "Wrote Qualcomm AI Hub config: $configPath"
}

# Return the recursive file byte total for download progress monitoring.
function Get-DirectoryBytes {
    param([string] $Path)

    if (-not (Test-Path $Path)) {
        return 0
    }

    $sum = Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue |
    Measure-Object -Property Length -Sum
    if ($null -eq $sum.Sum) {
        return 0
    }
    return [int64] $sum.Sum
}

# Run the gated Qualcomm Workbench export and monitor downloaded output size.
function Invoke-WorkbenchExport {
    $stdout = $exportStdoutPath
    $stderr = $exportStderrPath
    $args = $exportCommand[1..($exportCommand.Count - 1)]

    Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $venvPy
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($arg in $args) {
        [void] $startInfo.ArgumentList.Add($arg)
    }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $stdoutBuilder = [System.Text.StringBuilder]::new()
    $stderrBuilder = [System.Text.StringBuilder]::new()
    $outputHandler = [System.Diagnostics.DataReceivedEventHandler] {
        param($sender, $eventArgs)
        if ($null -ne $eventArgs.Data) {
            [void] $stdoutBuilder.AppendLine($eventArgs.Data)
            Write-Host $eventArgs.Data
        }
    }
    $errorHandler = [System.Diagnostics.DataReceivedEventHandler] {
        param($sender, $eventArgs)
        if ($null -ne $eventArgs.Data) {
            [void] $stderrBuilder.AppendLine($eventArgs.Data)
            Write-Host $eventArgs.Data
        }
    }
    $process.add_OutputDataReceived($outputHandler)
    $process.add_ErrorDataReceived($errorHandler)
    [void] $process.Start()
    $process.BeginOutputReadLine()
    $process.BeginErrorReadLine()

    while (-not $process.HasExited) {
        $bytes = Get-DirectoryBytes $exportDir
        $files = @(Get-ChildItem -LiteralPath $exportDir -Recurse -File -ErrorAction SilentlyContinue).Count
        $line = "[{0}] export_dir_files={1} export_dir_bytes={2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $files, $bytes
        Write-Host $line
        Add-Content -Path $downloadMonitorPath -Value $line
        Start-Sleep -Seconds 15
        $process.Refresh()
    }

    $process.WaitForExit()
    $stdoutText = $stdoutBuilder.ToString()
    $stderrText = $stderrBuilder.ToString()

    $stdoutText | Set-Content -Path $stdout -Encoding UTF8
    $stderrText | Set-Content -Path $stderr -Encoding UTF8

    if ($process.ExitCode -ne 0) {
        throw "Workbench export failed with exit code $($process.ExitCode). See $stdout and $stderr."
    }
}

# Download known completed Workbench artifacts without creating new jobs.
function Invoke-CompletedArtifactDownload {
    Import-WorkbenchIdsIfPresent
    if ([string]::IsNullOrWhiteSpace($encoderJobId) -and [string]::IsNullOrWhiteSpace($encoderModelId)) {
        throw "Encoder job/model ID is missing. Run -RunWorkbenchExport first or pass -encoderJobId/-encoderModelId."
    }
    if ([string]::IsNullOrWhiteSpace($decoderJobId) -and [string]::IsNullOrWhiteSpace($decoderModelId)) {
        throw "Decoder job/model ID is missing. Run -RunWorkbenchExport first or pass -decoderJobId/-decoderModelId."
    }

    $python = @"
import json
import os
import shutil
import zipfile
from pathlib import Path

import qai_hub as hub

out_root = Path(os.environ["JARVIS_WHISPER_OUT"])
zip_path = Path(os.environ["JARVIS_WHISPER_ZIP"])
encoder_job_id = os.environ.get("JARVIS_ENCODER_JOB_ID", "")
decoder_job_id = os.environ.get("JARVIS_DECODER_JOB_ID", "")
encoder_model_id = os.environ.get("JARVIS_ENCODER_MODEL_ID", "")
decoder_model_id = os.environ.get("JARVIS_DECODER_MODEL_ID", "")

manifest = {
    "purpose": "JARVISv7 Whisper QNN artifact handoff for ARM64 validation",
    "sources": {},
    "files": [],
}

def extract_if_zip(path, target_dir):
    path = Path(path)
    if path.suffix.lower() != ".zip":
        return None
    extracted = target_dir / "extracted"
    extracted.mkdir(exist_ok=True)
    with zipfile.ZipFile(path, "r") as zf:
        zf.extractall(extracted)
    print("extracted:", extracted)
    return extracted

def list_files(base):
    files = []
    for p in base.rglob("*"):
        if p.is_file():
            rel = str(p.relative_to(out_root))
            size = p.stat().st_size
            files.append({"path": rel, "bytes": size})
            print("file:", rel, size)
    return files

def download_by_job(label, job_id, out_dir):
    print(f"=== {label} job: {job_id} ===")
    job = hub.get_job(job_id)
    print("status:", job.get_status())
    print("url:", getattr(job, "url", None))
    target = job.get_target_model()
    if target is None:
        raise RuntimeError(f"{label} job {job_id} has no target model")
    print("target model:", getattr(target, "model_id", None), getattr(target, "name", None), getattr(target, "model_type", None))
    downloaded = Path(target.download(str(out_dir / f"{label}_target")))
    print("downloaded:", downloaded)
    return downloaded, {
        "kind": "job_target_model",
        "job_id": job_id,
        "job_url": getattr(job, "url", None),
        "target_model_id": getattr(target, "model_id", None),
        "target_name": getattr(target, "name", None),
        "target_type": str(getattr(target, "model_type", None)),
        "downloaded": str(downloaded),
    }

def download_by_model(label, model_id, out_dir):
    print(f"=== {label} model: {model_id} ===")
    model = hub.get_model(model_id)
    print("model:", getattr(model, "model_id", None), getattr(model, "name", None), getattr(model, "model_type", None))
    downloaded = Path(model.download(str(out_dir / f"{label}_target")))
    print("downloaded:", downloaded)
    return downloaded, {
        "kind": "model",
        "model_id": getattr(model, "model_id", model_id),
        "model_name": getattr(model, "name", None),
        "model_type": str(getattr(model, "model_type", None)),
        "downloaded": str(downloaded),
    }

def download_component(label, job_id, model_id):
    component_dir = out_root / label
    component_dir.mkdir(parents=True, exist_ok=True)
    try:
        if not job_id:
            raise RuntimeError(f"{label} job id not supplied")
        downloaded, meta = download_by_job(label, job_id, component_dir)
    except Exception as exc:
        print(f"{label} job download failed: {exc}")
        if not model_id:
            raise
        downloaded, meta = download_by_model(label, model_id, component_dir)
    extract_if_zip(downloaded, component_dir)
    manifest["sources"][label] = meta

download_component("encoder", encoder_job_id, encoder_model_id)
download_component("decoder", decoder_job_id, decoder_model_id)

manifest["files"] = list_files(out_root)
manifest_path = out_root / "download-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
print("download manifest:", manifest_path)
"@

    $downloadScriptPath = Join-Path $outputDir "download-completed-artifacts.py"
    $python | Set-Content -Path $downloadScriptPath -Encoding UTF8

    Write-Host "Downloading completed Workbench artifacts..."
    Write-Host "  encoder job/model: $encoderJobId / $encoderModelId"
    Write-Host "  decoder job/model: $decoderJobId / $decoderModelId"

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $venvPy
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    [void] $startInfo.ArgumentList.Add($downloadScriptPath)
    $startInfo.Environment["JARVIS_WHISPER_OUT"] = $exportDir
    $startInfo.Environment["JARVIS_WHISPER_ZIP"] = $zipPath
    $startInfo.Environment["JARVIS_ENCODER_JOB_ID"] = $encoderJobId
    $startInfo.Environment["JARVIS_DECODER_JOB_ID"] = $decoderJobId
    $startInfo.Environment["JARVIS_ENCODER_MODEL_ID"] = $encoderModelId
    $startInfo.Environment["JARVIS_DECODER_MODEL_ID"] = $decoderModelId

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $stdoutBuilder = [System.Text.StringBuilder]::new()
    $stderrBuilder = [System.Text.StringBuilder]::new()
    $outputHandler = [System.Diagnostics.DataReceivedEventHandler] {
        param($sender, $eventArgs)
        if ($null -ne $eventArgs.Data) {
            [void] $stdoutBuilder.AppendLine($eventArgs.Data)
            Write-Host $eventArgs.Data
        }
    }
    $errorHandler = [System.Diagnostics.DataReceivedEventHandler] {
        param($sender, $eventArgs)
        if ($null -ne $eventArgs.Data) {
            [void] $stderrBuilder.AppendLine($eventArgs.Data)
            Write-Host $eventArgs.Data
        }
    }
    $process.add_OutputDataReceived($outputHandler)
    $process.add_ErrorDataReceived($errorHandler)
    [void] $process.Start()
    $process.BeginOutputReadLine()
    $process.BeginErrorReadLine()

    while (-not $process.HasExited) {
        $bytes = Get-DirectoryBytes $exportDir
        $files = @(Get-ChildItem -LiteralPath $exportDir -Recurse -File -ErrorAction SilentlyContinue).Count
        $line = "[{0}] download_files={1} download_bytes={2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $files, $bytes
        Write-Host $line
        Add-Content -Path $downloadMonitorPath -Value $line
        Start-Sleep -Seconds 5
        $process.Refresh()
    }

    $process.WaitForExit()
    $stdoutBuilder.ToString() | Set-Content -Path $downloadStdoutPath -Encoding UTF8
    $stderrBuilder.ToString() | Set-Content -Path $downloadStderrPath -Encoding UTF8

    if ($process.ExitCode -ne 0) {
        throw "Completed artifact download failed with exit code $($process.ExitCode). See $downloadStdoutPath and $downloadStderrPath."
    }

    $script:jobIds = @($encoderJobId, $decoderJobId) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $script:modelIds = @($encoderModelId, $decoderModelId) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
}

# Best-effort extraction of job/model IDs from captured Workbench output.
function Get-WorkbenchIds {
    $text = @()
    foreach ($path in @($exportStdoutPath, $exportStderrPath)) {
        if (Test-Path $path) {
            $text += Get-Content -Path $path
        }
    }

    $joined = $text -join "`n"
    $script:jobIds = @([regex]::Matches($joined, "(?i)(?<=/jobs/)[a-z0-9_-]+|\bjob[_/-]?[a-z0-9]+\b") | ForEach-Object { $_.Value } | Sort-Object -Unique)
    $script:modelIds = @([regex]::Matches($joined, "(?i)(?<=/models/)[a-z0-9_-]+|\bmodel[_/-]?[a-z0-9]+\b|\bm[a-z0-9]{6,}\b") | ForEach-Object { $_.Value } | Sort-Object -Unique)

    foreach ($line in $text) {
        $lower = $line.ToLowerInvariant()
        $jobMatch = [regex]::Match($line, "(?i)(?<=/jobs/)[a-z0-9_-]+|\bjob[_/-]?[a-z0-9]+\b")
        $modelMatch = [regex]::Match($line, "(?i)(?<=/models/)[a-z0-9_-]+|\bmodel[_/-]?[a-z0-9]+\b|\bm[a-z0-9]{6,}\b")

        if ($lower.Contains("encoder")) {
            if ([string]::IsNullOrWhiteSpace($script:encoderJobId) -and $jobMatch.Success) {
                $script:encoderJobId = $jobMatch.Value
            }
            if ([string]::IsNullOrWhiteSpace($script:encoderModelId) -and $modelMatch.Success) {
                $script:encoderModelId = $modelMatch.Value
            }
        }

        if ($lower.Contains("decoder")) {
            if ([string]::IsNullOrWhiteSpace($script:decoderJobId) -and $jobMatch.Success) {
                $script:decoderJobId = $jobMatch.Value
            }
            if ([string]::IsNullOrWhiteSpace($script:decoderModelId) -and $modelMatch.Success) {
                $script:decoderModelId = $modelMatch.Value
            }
        }
    }

    $ids = [ordered]@{
        encoder_job_id = $script:encoderJobId
        decoder_job_id = $script:decoderJobId
        encoder_model_id = $script:encoderModelId
        decoder_model_id = $script:decoderModelId
        all_job_ids = $script:jobIds
        all_model_ids = $script:modelIds
    }
    $ids | ConvertTo-Json -Depth 4 | Set-Content -Path $workbenchIdsPath -Encoding UTF8
    Write-Host "Workbench IDs written to: $workbenchIdsPath"
}

# Load IDs captured by a prior export run in this output directory.
function Import-WorkbenchIdsIfPresent {
    $idsPath = $workbenchIdsPath
    if (-not [string]::IsNullOrWhiteSpace($workbenchIdsInputPath)) {
        $idsPath = $workbenchIdsInputPath
    }

    if (-not (Test-Path $idsPath)) {
        return
    }

    $ids = Get-Content -Raw $idsPath | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace($script:encoderJobId)) { $script:encoderJobId = [string] $ids.encoder_job_id }
    if ([string]::IsNullOrWhiteSpace($script:decoderJobId)) { $script:decoderJobId = [string] $ids.decoder_job_id }
    if ([string]::IsNullOrWhiteSpace($script:encoderModelId)) { $script:encoderModelId = [string] $ids.encoder_model_id }
    if ([string]::IsNullOrWhiteSpace($script:decoderModelId)) { $script:decoderModelId = [string] $ids.decoder_model_id }
    Write-Host "Loaded Workbench IDs from: $idsPath"
}

# Validate roots and mutually exclusive modes before starting transcript.
if (-not (Test-Path $jarvisRoot)) {
    throw "JARVIS root does not exist: $jarvisRoot"
}

if ($InspectOnly -and ($RunWorkbenchExport -or $DownloadCompletedArtifacts)) {
    throw "Use -InspectOnly by itself."
}

if ($RunWorkbenchExport -and $DownloadCompletedArtifacts) {
    throw "Use either -RunWorkbenchExport or -DownloadCompletedArtifacts, not both."
}

if (-not (Test-Path $exportRoot)) {
    Invoke-Step "Create export root" {
        New-Item -ItemType Directory -Force -Path $exportRoot | Out-Null
    }
}

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
    Write-Host "InspectOnly: $InspectOnly"
    Write-Host "RunWorkbenchExport: $RunWorkbenchExport"
    Write-Host "DownloadCompletedArtifacts: $DownloadCompletedArtifacts"

    # Phase 1: create local package directories.
    Invoke-Step "Create package directories" {
        New-Item -ItemType Directory -Force -Path $exportDir | Out-Null
        New-Item -ItemType Directory -Force -Path $docsTemp | Out-Null
    }

    if (-not $InspectOnly) {
        # Phase 2: create or refresh the external Qualcomm Python venv.
        Invoke-Step "Create Qualcomm Python venv" {
            if (-not (Test-Path $venvPy)) {
                Invoke-Native $pythonExe @("-m", "venv", $venvDir)
            }
            else {
                Write-Host "Venv already exists: $venvDir"
            }
            Invoke-Native $venvPy @("-m", "pip", "install", "--upgrade", "pip")
        }

        # Phase 3: install export dependencies into the external venv.
        Invoke-Step "Install embedded Qualcomm export dependencies" {
            $installArgs = @("-m", "pip", "install") + $qualcommPackages
            Invoke-Native $venvPy $installArgs
        }

        # Phase 4: configure Workbench credentials using the documented config file.
        Invoke-Step "Configure Qualcomm AI Hub profile from environment when present" {
            Write-QualcommConfig
        }
    }
    else {
        Write-Host "InspectOnly selected; skipping venv creation, package install, AI Hub configure, and Workbench export."
    }

    if ($RunWorkbenchExport) {
        Write-Host ""
        Write-Host "WARNING: Qualcomm Workbench export creates remote Qualcomm jobs/models."
        Write-Host "This can consume account resources and leave remote artifacts in Qualcomm Workbench."
        $confirmation = Read-Host "Type RUN-WORKBENCH-EXPORT to continue"
        if ($confirmation -ne "RUN-WORKBENCH-EXPORT") {
            throw "Workbench export confirmation was not provided."
        }

        # Phase 5: run the remote Workbench export only after explicit confirmation.
        Invoke-Step "Run Qualcomm Workbench export" {
            Invoke-WorkbenchExport
            Get-WorkbenchIds
        }
    }
    else {
        Write-Host "Workbench export skipped. Add -RunWorkbenchExport to create remote Qualcomm jobs/models."
    }

    if ($DownloadCompletedArtifacts) {
        # Phase 5b: download completed models without creating remote jobs.
        Invoke-Step "Download completed Qualcomm Workbench artifacts" {
            Invoke-CompletedArtifactDownload
        }
    }
    else {
        Write-Host "Completed artifact download skipped. Add -DownloadCompletedArtifacts to package known models."
    }

    # Phase 6: record resolved package versions when the external venv exists.
    Invoke-Step "Record installed package versions when venv exists" {
        if (Test-Path $venvPy) {
            & $venvPy -m pip freeze | Set-Content -Path $pipFreezePath -Encoding UTF8
            if ($LASTEXITCODE -ne 0) {
                throw "pip freeze failed with exit code ${LASTEXITCODE}"
            }
        }
        else {
            "Qualcomm venv not present; pip freeze skipped." | Set-Content -Path $pipFreezePath -Encoding UTF8
        }
    }

    # Phase 7: write package metadata for later ARM64 validation.
    Invoke-Step "Write export manifest" {
        $manifest = [ordered]@{
            model_name                            = $modelName
            timestamp                             = $timestamp
            created_utc                           = (Get-Date).ToUniversalTime().ToString("o")
            jarvis_root                           = $jarvisRoot
            export_root                           = $exportRoot
            venv                                  = $venvDir
            device                                = $deviceName
            target_runtime                        = "precompiled_qnn_onnx"
            export_module                         = "qai_hub_models.models.whisper_base.export"
            packages                              = $qualcommPackages
            output_dir                            = $outputDir
            export_dir                            = $exportDir
            zip_path                              = $zipPath
            command                               = ($exportCommand -join " ")
            inspect_only                          = [bool] $InspectOnly
            workbench_export_requested            = [bool] $RunWorkbenchExport
            completed_artifact_download_requested = [bool] $DownloadCompletedArtifacts
            encoder_job_id                        = $encoderJobId
            decoder_job_id                        = $decoderJobId
            encoder_model_id                      = $encoderModelId
            decoder_model_id                      = $decoderModelId
            workbench_ids_path                    = $workbenchIdsPath
            workbench_ids_input_path              = $workbenchIdsInputPath
            workbench_job_ids                     = $jobIds
            workbench_model_ids                   = $modelIds
            stdout_path                           = $exportStdoutPath
            stderr_path                           = $exportStderrPath
            download_stdout_path                  = $downloadStdoutPath
            download_stderr_path                  = $downloadStderrPath
            download_monitor_path                 = $downloadMonitorPath
            source_docs                           = @(
                "https://aihub.qualcomm.com/get-started",
                "https://workbench.aihub.qualcomm.com/docs/"
            )
        }

        $manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $manifestPath -Encoding UTF8
    }

    # Phase 8: create the only repo artifact for this helper.
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
    }
    else {
        Write-Host "Helper completed. Package written to:"
    }
    Write-Host "  $zipPath"
}
finally {
    if ($transcriptStarted) {
        # Ensure transcript is always closed, even on failure.
        Stop-Transcript
    }
}
