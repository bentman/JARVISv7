<#
.SYNOPSIS
Build llama.cpp on Windows ARM64 with Qualcomm Adreno OpenCL support.

.DESCRIPTION
Manual helper for the JARVISv7 Windows ARM64 Adreno OpenCL sidecar build.
The script keeps build trees outside the repo, uses Visual Studio's official
ARM64 developer environment, and stages only the runtime directory in JARVISv7.

.NOTES
Run from PowerShell. The script imports the VS ARM64 environment with:
  vcvarsall.bat arm64

.PARAMETER JarvisRoot
Path to the JARVISv7 repository root.

.PARAMETER JarvisDevRoot
Path to the external developer workspace for OpenCL and llama.cpp build trees.

.PARAMETER TranscriptPath
Path to the command transcript. Defaults under JarvisDevRoot.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Low')]
param(
    [string] $jarvisRoot = "D:\WORK\CODE\GitHub\bentman\Repositories\JARVISv7",
    [string] $jarvisDevRoot = "D:\WORK\jarvis-dev\llm",
    [string] $transcriptPath = ""
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

function Import-VSArm64Environment {
    $vcvarsAll = "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat"
    if (-not (Test-Path $vcvarsAll)) {
        throw "vcvarsall.bat not found: $vcvarsAll"
    }

    $envDump = & cmd.exe /d /s /c "call `"$vcvarsAll`" arm64 >nul && set"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to initialize Visual Studio ARM64 environment with vcvarsall.bat arm64."
    }

    foreach ($line in $envDump) {
        $separator = $line.IndexOf("=")
        if ($separator -le 0) {
            continue
        }

        $name = $line.Substring(0, $separator)
        $value = $line.Substring($separator + 1)
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }

    if ($env:VSCMD_ARG_TGT_ARCH -ne "arm64") {
        throw "Visual Studio environment target architecture is '$env:VSCMD_ARG_TGT_ARCH', expected 'arm64'."
    }

    $clangCl = (Get-Command clang-cl.exe -ErrorAction Stop).Source
    if ($clangCl -notlike "*\VC\Tools\Llvm\ARM64\bin\clang-cl.exe") {
        throw "clang-cl.exe resolved to '$clangCl', expected Visual Studio ARM64 LLVM bin."
    }

    Write-Host "VS target architecture: $env:VSCMD_ARG_TGT_ARCH"
    Write-Host "clang-cl: $clangCl"
}

function Update-Or-Clone {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RepositoryUrl,

        [Parameter(Mandatory = $true)]
        [string] $Destination
    )

    if (Test-Path $Destination) {
        Push-Location $Destination
        try {
            Invoke-Native "git" @("pull", "--ff-only")
        }
        finally {
            Pop-Location
        }
    }
    else {
        Invoke-Native "git" @("clone", $RepositoryUrl, $Destination)
    }
}

if (-not (Test-Path $jarvisRoot)) {
    throw "JARVIS root does not exist: $jarvisRoot"
}

if (-not (Test-Path $jarvisDevRoot)) {
    New-Item -ItemType Directory -Force -Path $jarvisDevRoot | Out-Null
}

$jarvisRoot = (Resolve-Path $jarvisRoot).Path
$jarvisDevRoot = (Resolve-Path $jarvisDevRoot).Path

if ([string]::IsNullOrWhiteSpace($transcriptPath)) {
    $transcriptPath = Join-Path $jarvisDevRoot "$(Get-Date -Format yyyyMMddHHmmss)_jarvis-arm-llamacpp-transcript.txt"
}

$openCLHeadersRoot = Join-Path $jarvisDevRoot "OpenCL-Headers"
$openCLLoaderRoot = Join-Path $jarvisDevRoot "OpenCL-ICD-Loader"
$openCLPrefix = Join-Path $jarvisDevRoot "opencl"
$llamaRoot = Join-Path $jarvisDevRoot "llama.cpp"
$llamaBuildDir = Join-Path $llamaRoot "build-arm64-adreno-opencl"
$jarvisRuntimeDir = Join-Path $jarvisRoot "runtimes\llama.cpp\windows-arm64-adreno-opencl"

Start-Transcript -Path $transcriptPath -Force
try {
    Write-Host "JARVIS root: $jarvisRoot"
    Write-Host "Developer workspace root: $jarvisDevRoot"
    Write-Host "Transcript path: $transcriptPath"

    Invoke-Step "Import Visual Studio ARM64 developer environment" {
        Import-VSArm64Environment
    }

    Invoke-Step "Clone or update OpenCL-Headers" {
        Update-Or-Clone "https://github.com/KhronosGroup/OpenCL-Headers" $openCLHeadersRoot
    }

    Invoke-Step "Configure and install OpenCL headers" {
        $buildDir = Join-Path $openCLHeadersRoot "build"
        New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
        Invoke-Native "cmake" @(
            "-S", $openCLHeadersRoot,
            "-B", $buildDir,
            "-G", "Ninja",
            "-DBUILD_TESTING=OFF",
            "-DOPENCL_HEADERS_BUILD_TESTING=OFF",
            "-DOPENCL_HEADERS_BUILD_CXX_TESTS=OFF",
            "-DCMAKE_INSTALL_PREFIX=$openCLPrefix"
        )
        Invoke-Native "cmake" @("--build", $buildDir, "--target", "install")
    }

    Invoke-Step "Clone or update OpenCL-ICD-Loader" {
        Update-Or-Clone "https://github.com/KhronosGroup/OpenCL-ICD-Loader" $openCLLoaderRoot
    }

    Invoke-Step "Configure and install OpenCL ICD loader" {
        $buildDir = Join-Path $openCLLoaderRoot "build"
        New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
        Invoke-Native "cmake" @(
            "-S", $openCLLoaderRoot,
            "-B", $buildDir,
            "-G", "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_PREFIX_PATH=$openCLPrefix",
            "-DCMAKE_INSTALL_PREFIX=$openCLPrefix"
        )
        Invoke-Native "cmake" @("--build", $buildDir, "--target", "install")
    }

    Invoke-Step "Clone or update llama.cpp" {
        Update-Or-Clone "https://github.com/ggml-org/llama.cpp" $llamaRoot
    }

    Invoke-Step "Configure llama.cpp ARM64 Adreno OpenCL build" {
        if (Test-Path $llamaBuildDir) {
            $backupBuildDir = "$llamaBuildDir.failed-$(Get-Date -Format yyyyMMddHHmmss)"
            Rename-Item -Path $llamaBuildDir -NewName (Split-Path $backupBuildDir -Leaf)
            Write-Host "Renamed existing build directory to: $backupBuildDir"
        }

        Invoke-Native "cmake" @(
            "-S", $llamaRoot,
            "-B", $llamaBuildDir,
            "-G", "Ninja",
            "-DCMAKE_C_COMPILER=clang-cl",
            "-DCMAKE_CXX_COMPILER=clang-cl",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DGGML_OPENMP=OFF",
            "-DGGML_OPENCL=ON",
            "-DCMAKE_PREFIX_PATH=$openCLPrefix",
            "-DBUILD_SHARED_LIBS=OFF"
        )
    }

    Invoke-Step "Build llama.cpp ARM64 Adreno OpenCL" {
        Invoke-Native "cmake" @("--build", $llamaBuildDir)
    }

    Invoke-Step "Create JARVIS runtime staging directory" {
        New-Item -ItemType Directory -Force -Path $jarvisRuntimeDir | Out-Null
        Write-Host "Runtime staging directory: $jarvisRuntimeDir"
    }

    Invoke-Step "Copy llama.cpp runtime artifacts into JARVIS" {
        $llamaBinDir = Join-Path $llamaBuildDir "bin"
        $serverSource = Join-Path $llamaBinDir "llama-server.exe"
        $openCLDllSource = Join-Path $openCLPrefix "bin\OpenCL.dll"

        if (-not (Test-Path $serverSource)) {
            throw "Built llama-server.exe was not found: $serverSource"
        }

        if (-not (Test-Path $openCLDllSource)) {
            throw "Built OpenCL.dll was not found: $openCLDllSource"
        }

        Copy-Item -LiteralPath $serverSource -Destination (Join-Path $jarvisRuntimeDir "llama-server.exe") -Force
        Copy-Item -LiteralPath $openCLDllSource -Destination (Join-Path $jarvisRuntimeDir "OpenCL.dll") -Force

        Write-Host "Copied llama-server.exe"
        Write-Host "Copied OpenCL.dll"
    }

    Write-Host ""
    Write-Host "Build helper completed. Runtime artifacts staged in:"
    Write-Host "  $jarvisRuntimeDir"
}
finally {
    Stop-Transcript
}
