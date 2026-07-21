<#
.SYNOPSIS
Build llama.cpp on Windows ARM64 with Qualcomm Hexagon QNN NPU support.

.DESCRIPTION
Manual helper for the JARVISv7 Windows ARM64 QNN NPU sidecar build.
The script keeps build trees outside the repo, uses Visual Studio's official
ARM64 developer environment, and stages only the runtime directory in JARVISv7.

.NOTES
Run from Visual Studio Developer PowerShell with ARM64 tools already loaded.

Requires Qualcomm AI Engine Direct SDK / QAIRT with Hexagon HTP libraries.
QNN support in llama.cpp is experimental and may require SDK-version-specific
build flag adjustments.

.PARAMETER JarvisRoot
Path to the JARVISv7 repository root.

.PARAMETER JarvisDevRoot
Path to the external developer workspace for QAIRT and llama.cpp build trees.

.PARAMETER QairtSdkPath
Path to the Qualcomm AI Engine Direct SDK / QAIRT root. If not provided, uses
the environment variable QAIRT_SDK_PATH.

.PARAMETER TranscriptPath
Path to the command transcript. Defaults under JarvisDevRoot.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Low')]
param(
    [string] $jarvisRoot = "$PSScriptRoot\..\..",
    [string] $jarvisDevRoot = "$jarvisRoot\..\jarvis-dev\llm-qnn",
    [string] $qairtSdkPath = "$jarvisRoot\..\jarvis-dev\Qualcomm\v2.46.0.260424\qairt\v2.46.0.260424",
    [string] $hexagonHtpCert = "",
    [string] $windowsSdkBin = "",
    [switch] $disableCertGen = $false,
    [string] $transcriptPath = "$jarvisDevRoot\$(Get-Date -Format yyyyMMddHHmmss)_jarvis-arm-llamacpp-qnn-transcript.txt"
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"

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

# Import Visual Studio's ARM64 compiler environment into this process.
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

# Auto-discover the Windows Kits 10 bin folder containing signtool and inf2cat
function Get-WindowsSdkBin {
    param(
        [string] $explicitBin
    )

    if (-not [string]::IsNullOrWhiteSpace($explicitBin) -and (Test-Path $explicitBin)) {
        return (Resolve-Path $explicitBin).Path
    }

    if (-not [string]::IsNullOrWhiteSpace($env:WINDOWS_SDK_BIN) -and (Test-Path $env:WINDOWS_SDK_BIN)) {
        return (Resolve-Path $env:WINDOWS_SDK_BIN).Path
    }

    $kitsPath = "C:\Program Files (x86)\Windows Kits\10\bin"
    if (Test-Path $kitsPath) {
        $latest = Get-ChildItem -Path $kitsPath -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "^10\." } |
            Sort-Object Name -Descending |
            Select-Object -First 1
        if ($null -ne $latest) {
            return $latest.FullName
        }
    }

    return ""
}

# Ensure a personal signing certificate exists. Generates one if enabled and missing.
function Ensure-HtpCertificate {
    param(
        [string] $explicitCert,
        [string] $devRoot,
        [bool] $disableGen
    )

    if (-not [string]::IsNullOrWhiteSpace($explicitCert) -and (Test-Path $explicitCert)) {
        return (Resolve-Path $explicitCert).Path
    }

    if (-not [string]::IsNullOrWhiteSpace($env:HEXAGON_HTP_CERT) -and (Test-Path $env:HEXAGON_HTP_CERT)) {
        return (Resolve-Path $env:HEXAGON_HTP_CERT).Path
    }

    $certPfx = Join-Path $devRoot "ggml-htp-v1.pfx"
    if (Test-Path $certPfx) {
        return $certPfx
    }

    if ($disableGen) {
        Write-Host "Certificate auto-generation is disabled."
        return ""
    }

    Write-Host "Generating self-signed Hexagon HTP certificate in developer workspace..."
    $certCer = Join-Path $devRoot "ggml-htp-v1.cer"

    try {
        if (Test-Path $certCer) { Remove-Item $certCer -Force }

        # Generate cert using native PowerShell cmdlets (non-interactive, no password popups)
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=GGML.HTP.v1" -KeyUsage DigitalSignature -KeyExportPolicy Exportable -CertStoreLocation Cert:\CurrentUser\My -ErrorAction Stop
        
        # Export PFX with a password (using TripleDES_SHA1 for SignTool compatibility)
        $password = ConvertTo-SecureString "ggml" -AsPlainText -Force
        $null = Export-PfxCertificate -Cert $cert -FilePath $certPfx -Password $password -CryptoAlgorithmOption TripleDES_SHA1 -ErrorAction Stop
        $null = Export-Certificate -Cert $cert -FilePath $certCer -ErrorAction Stop

        Write-Host "HTP Certificate generated successfully: $certPfx"
        Write-Host "Attempting to import certificate to Trusted Root and Trusted Publishers stores..."
        
        # Import to machine store (requires Admin for certutil)
        & certutil.exe -addstore Root $certCer | Out-Null
        & certutil.exe -addstore TrustedPublisher $certCer | Out-Null

        Write-Host "[IMPORTANT] Ensure 'bcdedit /set TESTSIGNING ON' has been run and the system rebooted."
        return $certPfx
    }
    catch {
        Write-Warning "Failed to generate or import HTP signing certificate: $_"
        return ""
    }
}

# Generate and sign catalog file (.cat) using MakeCat and SignTool
function Generate-CatalogFile {
    param(
        [string] $stagedDir,
        [string] $sdkBin,
        [string] $certPfx
    )

    $catFile = Join-Path $stagedDir "libggml-htp.cat"
    if (Test-Path $catFile) { Remove-Item $catFile -Force }

    $cdfPath = Join-Path $stagedDir "libggml-htp.cdf"
    $soFiles = Get-ChildItem -LiteralPath $stagedDir -File -Filter "libggml-htp-v*.so"

    if ($soFiles.Count -eq 0) {
        Write-Warning "No HTP skeleton files found to generate catalog."
        return
    }

    # Construct CDF content
    $cdfLines = @(
        "[CatalogHeader]",
        "Name=libggml-htp.cat",
        "PublicVersion=0x0000001",
        "EncodingType=0x00010001",
        "CATATTR1=0x10010001:OSAttr:2:6.0",
        "",
        "[CatalogFiles]"
    )
    foreach ($so in $soFiles) {
        $cdfLines += "<hash>$($so.Name)=$($so.Name)"
    }

    $cdfLines | Out-File -FilePath $cdfPath -Encoding ascii -Force

    $makecat = Get-ChildItem -Path $sdkBin -Recurse -Filter "makecat.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    $signtool = Get-ChildItem -Path $sdkBin -Recurse -Filter "signtool.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1

    if ($null -eq $makecat -or $null -eq $signtool) {
        Write-Warning "makecat.exe or signtool.exe not found; cannot sign catalog."
        if (Test-Path $cdfPath) { Remove-Item $cdfPath -Force }
        return
    }

    Write-Host "Creating catalog file using makecat..."
    Push-Location $stagedDir
    try {
        Invoke-Native $makecat.FullName @("-v", "libggml-htp.cdf")
        
        if (Test-Path "libggml-htp.cat") {
            Write-Host "Signing catalog file using signtool..."
            # Sign the catalog using the certificate and password
            Invoke-Native $signtool.FullName @("sign", "/fd", "sha256", "/f", $certPfx, "/p", "ggml", "libggml-htp.cat")
            Write-Host "Catalog file generated and signed: libggml-htp.cat"
        }
        else {
            Write-Warning "makecat failed to produce libggml-htp.cat."
        }
    }
    catch {
        Write-Warning "Catalog generation/signing failed: $_"
    }
    finally {
        if (Test-Path "libggml-htp.cdf") { Remove-Item "libggml-htp.cdf" -Force }
        Pop-Location
    }
}

# Clone a dependency repo once, then update by fast-forward only.
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

# Validate QAIRT SDK structure before using it in CMake.
function Test-QairtSdk {
    param(
        [Parameter(Mandatory = $true)]
        [string] $SdkPath
    )

    $requiredPaths = @(
        (Join-Path $SdkPath "include"),
        (Join-Path $SdkPath "lib"),
        (Join-Path $SdkPath "bin")
    )

    foreach ($path in $requiredPaths) {
        if (-not (Test-Path $path)) {
            throw "QAIRT SDK missing required path: $path"
        }
    }

    $htpDll = Get-ChildItem -LiteralPath $SdkPath -Recurse -Filter "QnnHtp.dll" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $htpDll) {
        throw "QAIRT SDK missing QnnHtp.dll under: $SdkPath"
    }

    $qnnInterfaceHeader = Get-ChildItem -LiteralPath $SdkPath -Recurse -Filter "QnnInterface.h" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $qnnInterfaceHeader) {
        throw "QAIRT SDK missing QnnInterface.h under: $SdkPath"
    }

    Write-Host "QAIRT SDK validated: $SdkPath"
    Write-Host "QnnHtp.dll: $($htpDll.FullName)"
    Write-Host "QnnInterface.h: $($qnnInterfaceHeader.FullName)"
}

# Resolve the Qualcomm package root from the QAIRT SDK path. For the repo's
# staged Qualcomm layout, a QAIRT path such as:
#   D:\WORK\Qualcomm\v2.46.0.260424\qairt\v2.46.0.260424
# resolves to:
#   D:\WORK\Qualcomm\v2.46.0.260424
function Get-QualcommPackageRootFromQairtPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $QairtRoot
    )

    $resolvedQairtRoot = (Resolve-Path $QairtRoot).Path
    $leaf = Split-Path $resolvedQairtRoot -Leaf
    $qairtContainer = Split-Path $resolvedQairtRoot -Parent
    $qairtContainerName = Split-Path $qairtContainer -Leaf

    if ($qairtContainerName -ieq "qairt") {
        return (Split-Path $qairtContainer -Parent)
    }

    if ($leaf -ieq "qairt") {
        return (Split-Path $resolvedQairtRoot -Parent)
    }

    return $resolvedQairtRoot
}

# llama.cpp's GGML_HEXAGON backend consumes the Hexagon SDK contract, even when
# the QNN/QAIRT runtime lives in the sibling qairt tree. Derive likely local SDK
# roots from the QAIRT package root instead of requiring C:\Qualcomm paths.
function Resolve-HexagonSdkRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string] $QairtRoot
    )

    if (-not [string]::IsNullOrWhiteSpace($env:HEXAGON_SDK_ROOT) -and (Test-Path $env:HEXAGON_SDK_ROOT)) {
        return (Resolve-Path $env:HEXAGON_SDK_ROOT).Path
    }

    $packageRoot = Get-QualcommPackageRootFromQairtPath -QairtRoot $QairtRoot
    $candidateRoots = @(
        (Join-Path $packageRoot "hexagon"),
        (Join-Path $packageRoot "hexagon-sdk"),
        (Join-Path $packageRoot "Hexagon_SDK"),
        (Join-Path $packageRoot "HexagonSDK"),
        $packageRoot,
        $QairtRoot
    )

    foreach ($candidate in $candidateRoots) {
        if (Test-HexagonSdkRoot -SdkPath $candidate -Quiet) {
            return (Resolve-Path $candidate).Path
        }

        if (Test-Path $candidate) {
            $versionedCandidate = Get-ChildItem -LiteralPath $candidate -Directory -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending |
                Where-Object { Test-HexagonSdkRoot -SdkPath $_.FullName -Quiet } |
                Select-Object -First 1

            if ($null -ne $versionedCandidate) {
                return $versionedCandidate.FullName
            }
        }
    }

    $childCandidate = Get-ChildItem -LiteralPath $packageRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "(?i)hexagon" } |
        Where-Object { Test-HexagonSdkRoot -SdkPath $_.FullName -Quiet } |
        Select-Object -First 1

    if ($null -ne $childCandidate) {
        return $childCandidate.FullName
    }

    throw "Hexagon SDK root could not be derived from QAIRT SDK path '$QairtRoot'. Expected a sibling Hexagon SDK under '$packageRoot' with build\cmake\hexagon_fun.cmake and incs."
}

function Test-HexagonSdkRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string] $SdkPath,

        [switch] $Quiet
    )

    $requiredPaths = @(
        (Join-Path $SdkPath "build\cmake\hexagon_fun.cmake"),
        (Join-Path $SdkPath "incs")
    )

    $missing = @($requiredPaths | Where-Object { -not (Test-Path $_) })
    if ($missing.Count -gt 0) {
        if ($Quiet) {
            return $false
        }

        throw "Hexagon SDK root is incomplete: $SdkPath. Missing: $($missing -join ', ')"
    }

    if (-not $Quiet) {
        Write-Host "Hexagon SDK validated: $SdkPath"
    }

    return $true
}

function Resolve-HexagonToolsRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string] $HexagonSdkRoot
    )

    if (-not [string]::IsNullOrWhiteSpace($env:HEXAGON_TOOLS_ROOT) -and (Test-Path $env:HEXAGON_TOOLS_ROOT)) {
        return (Resolve-Path $env:HEXAGON_TOOLS_ROOT).Path
    }

    $sdkConfigPath = Join-Path $HexagonSdkRoot "hexagon_sdk.json"
    if (Test-Path $sdkConfigPath) {
        $sdkConfig = Get-Content -LiteralPath $sdkConfigPath -Raw | ConvertFrom-Json
        $toolPath = $sdkConfig.root.tools.info[0].path
        if (-not [string]::IsNullOrWhiteSpace($toolPath)) {
            $candidate = Join-Path $HexagonSdkRoot $toolPath
            if (Test-Path $candidate) {
                return (Resolve-Path $candidate).Path
            }
        }
    }

    $toolsRoot = Join-Path $HexagonSdkRoot "tools\HEXAGON_Tools"
    if (Test-Path $toolsRoot) {
        $candidate = Get-ChildItem -LiteralPath $toolsRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            Select-Object -First 1
        if ($null -ne $candidate) {
            return $candidate.FullName
        }
    }

    throw "Hexagon tools root could not be derived from Hexagon SDK root '$HexagonSdkRoot'. Expected hexagon_sdk.json or tools\HEXAGON_Tools\<version>."
}

function Test-HexagonSdk {
    param(
        [Parameter(Mandatory = $true)]
        [string] $QairtRoot
    )

    $hexagonSdkRoot = Resolve-HexagonSdkRoot -QairtRoot $QairtRoot
    Test-HexagonSdkRoot -SdkPath $hexagonSdkRoot | Out-Null
    $hexagonToolsRoot = Resolve-HexagonToolsRoot -HexagonSdkRoot $hexagonSdkRoot

    $env:HEXAGON_SDK_ROOT = $hexagonSdkRoot
    $env:HEXAGON_TOOLS_ROOT = $hexagonToolsRoot

    Write-Host "Hexagon tools root: $hexagonToolsRoot"
}

# Resolve QAIRT runtime DLL directories that may need to be visible on PATH for
# native smoke tests. QAIRT_SDK_PATH is configuration metadata; Windows native
# DLL loading still needs the actual DLL directory on the loader search path.
function Get-QairtRuntimeDllDirectories {
    param(
        [Parameter(Mandatory = $true)]
        [string] $SdkPath
    )

    $runtimeDlls = Get-ChildItem -LiteralPath $SdkPath -Recurse -File -Include "QnnHtp.dll", "QnnSystem.dll", "QnnInterface.dll" -ErrorAction SilentlyContinue
    return $runtimeDlls |
        Select-Object -ExpandProperty DirectoryName -Unique |
        Sort-Object
}

# Resolve and print llama.cpp QNN CMake options before configure.
function Get-QnnCMakeArguments {
    param(
        [Parameter(Mandatory = $true)]
        [string] $QairtRoot
    )

    # Current upstream llama.cpp exposes the Windows Snapdragon accelerator as
    # the Hexagon backend, not as a QNN CMake option. Keep the SDK path options
    # here only as experimental compatibility inputs; the post-configure check
    # below rejects CPU-only builds.
    return @(
        "-DGGML_OPENMP=OFF",
        "-DGGML_HEXAGON=ON",
        "-DHEXAGON_SDK_ROOT=$env:HEXAGON_SDK_ROOT",
        "-DHEXAGON_TOOLS_ROOT=$env:HEXAGON_TOOLS_ROOT",
        "-DPREBUILT_LIB_DIR=toolv19_v81",
        "-DQAIRT_SDK_PATH=$QairtRoot",
        "-DGGML_QNN_SDK_PATH=$QairtRoot",
        "-DGGML_QNN_BUILD_STUB=OFF"
    )
}

# Fail fast if CMake accepted unknown QNN variables but did not enable an
# accelerator backend. A staged CPU-only binary is not valid evidence for the
# windows_arm64_npu_qualcomm_qnn profile.
function Assert-AcceleratorBackendConfigured {
    param(
        [Parameter(Mandatory = $true)]
        [string] $BuildDir
    )

    $cachePath = Join-Path $BuildDir "CMakeCache.txt"
    if (-not (Test-Path $cachePath)) {
        throw "CMakeCache.txt not found after configure: $cachePath"
    }

    $cacheText = Get-Content -LiteralPath $cachePath -Raw
    if ($cacheText -match "GGML_AVAILABLE_BACKENDS:INTERNAL=([^`r`n]+)") {
        $availableBackends = $Matches[1]
        Write-Host "Configured ggml backends: $availableBackends"
        if ($availableBackends -notmatch "hexagon|qnn") {
            throw "llama.cpp configure produced accelerator backends '$availableBackends', expected Hexagon/QNN. Check upstream Snapdragon build prerequisites and CMake options before staging."
        }
    }

    if ($cacheText -match "GGML_QNN:UNINITIALIZED=") {
        Write-Warning "GGML_QNN is not a recognized CMake cache option in this llama.cpp checkout. Upstream Snapdragon support currently uses GGML_HEXAGON."
    }
}

# Validate roots before deriving build paths.
if (-not (Test-Path $jarvisRoot)) {
    throw "JARVIS root does not exist: $jarvisRoot"
}

if (-not (Test-Path $jarvisDevRoot)) {
    New-Item -ItemType Directory -Force -Path $jarvisDevRoot | Out-Null
}

$jarvisRoot = (Resolve-Path $jarvisRoot).Path
$jarvisDevRoot = (Resolve-Path $jarvisDevRoot).Path

if ([string]::IsNullOrWhiteSpace($qairtSdkPath)) {
    $qairtSdkPath = $env:QAIRT_SDK_PATH
}
if ([string]::IsNullOrWhiteSpace($qairtSdkPath)) {
    throw "QAIRT SDK path not provided and QAIRT_SDK_PATH environment variable is not set."
}
if (-not (Test-Path $qairtSdkPath)) {
    throw "QAIRT SDK path does not exist: $qairtSdkPath"
}
$qairtSdkPath = (Resolve-Path $qairtSdkPath).Path

if ([string]::IsNullOrWhiteSpace($transcriptPath)) {
    $transcriptPath = Join-Path $jarvisDevRoot "$(Get-Date -Format yyyyMMddHHmmss)_jarvis-arm-llamacpp-qnn-transcript.txt"
}

$resolvedWindowsSdkBin = Get-WindowsSdkBin -explicitBin $windowsSdkBin
if (-not [string]::IsNullOrWhiteSpace($resolvedWindowsSdkBin)) {
    $env:WINDOWS_SDK_BIN = $resolvedWindowsSdkBin
}

$resolvedHexagonHtpCert = Ensure-HtpCertificate -explicitCert $hexagonHtpCert -devRoot $jarvisDevRoot -disableGen $disableCertGen
if (-not [string]::IsNullOrWhiteSpace($resolvedHexagonHtpCert)) {
    $env:HEXAGON_HTP_CERT = $resolvedHexagonHtpCert
}

# Derived build and staging paths.
$llamaRoot = Join-Path $jarvisDevRoot "llama.cpp"
$llamaBuildDir = Join-Path $llamaRoot "build-arm64-qnn"
$jarvisRuntimeDir = Join-Path $jarvisRoot "runtimes\llama.cpp\windows-arm64-qnn"

$transcriptStarted = $false
if (-not $WhatIfPreference) {
    Start-Transcript -Path $transcriptPath -Force
    $transcriptStarted = $true
}
try {
    Write-Host "JARVIS root: $jarvisRoot"
    Write-Host "Developer workspace root: $jarvisDevRoot"
    Write-Host "QAIRT SDK path: $qairtSdkPath"
    Write-Host "Windows SDK bin: $env:WINDOWS_SDK_BIN"
    Write-Host "Hexagon HTP cert: $env:HEXAGON_HTP_CERT"
    Write-Host "Transcript path: $transcriptPath"

    # Phase 1: cross-compilation toolchain.
    Invoke-Step "Initialize Visual Studio ARM64 build environment" {
        Import-VSArm64Environment
    }

    # Phase 2: QAIRT SDK validation.
    Invoke-Step "Validate QAIRT SDK" {
        Test-QairtSdk -SdkPath $qairtSdkPath
        Test-HexagonSdk -QairtRoot $qairtSdkPath
    }

    # Phase 3: llama.cpp source.
    Invoke-Step "Clone or update llama.cpp" {
        Update-Or-Clone "https://github.com/ggml-org/llama.cpp" $llamaRoot
    }

    # Phase 4: configure llama.cpp with QNN for ARM64.
    Invoke-Step "Configure llama.cpp ARM64 QNN build" {
        if (Test-Path $llamaBuildDir) {
            $backupBuildDir = "$llamaBuildDir.failed-$(Get-Date -Format yyyyMMddHHmmss)"
            Rename-Item -Path $llamaBuildDir -NewName (Split-Path $backupBuildDir -Leaf)
            Write-Host "Renamed existing build directory to: $backupBuildDir"
        }

        $env:QAIRT_SDK_PATH = $qairtSdkPath
        $qnnArgs = Get-QnnCMakeArguments -QairtRoot $qairtSdkPath

        $cmakeArgs = @(
            "-S", $llamaRoot,
            "-B", $llamaBuildDir,
            "-G", "Ninja",
            "-DCMAKE_C_COMPILER=clang-cl",
            "-DCMAKE_CXX_COMPILER=clang-cl",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DGGML_HEXAGON_HTP_CERT="
        ) + $qnnArgs

        Invoke-Native "cmake" $cmakeArgs
        Assert-AcceleratorBackendConfigured -BuildDir $llamaBuildDir
    }

    # Phase 5: compile.
    Invoke-Step "Build llama.cpp ARM64 QNN" {
        Invoke-Native "cmake" @("--build", $llamaBuildDir)
    }

    # Phase 6: create JARVIS runtime staging directory.
    Invoke-Step "Create JARVIS runtime staging directory" {
        New-Item -ItemType Directory -Force -Path $jarvisRuntimeDir | Out-Null
        Write-Host "Runtime staging directory: $jarvisRuntimeDir"
    }

    # Phase 7: deploy artifacts into the JARVIS runtime tree.
    Invoke-Step "Copy llama.cpp QNN runtime artifacts into JARVIS" {
        $llamaBinDir = Join-Path $llamaBuildDir "bin"
        $serverSource = Join-Path $llamaBinDir "llama-server.exe"

        if (-not (Test-Path $serverSource)) {
            throw "Built llama-server.exe was not found: $serverSource"
        }

        $runtimeArtifacts = Get-ChildItem -LiteralPath $llamaBinDir -File | Where-Object {
            $_.Name -eq "llama-server.exe" -or $_.Extension -eq ".dll"
        }

        $hexagonArtifactDir = Join-Path $llamaBuildDir "ggml\src\ggml-hexagon"
        if (Test-Path $hexagonArtifactDir) {
            $runtimeArtifacts += Get-ChildItem -LiteralPath $hexagonArtifactDir -File | Where-Object {
                $_.Name -like "libggml-htp-v*.so" -or $_.Name -eq "libggml-htp.cat"
            }
        }

        if ($runtimeArtifacts.Count -eq 0) {
            throw "No llama.cpp runtime artifacts were found in: $llamaBinDir"
        }

        foreach ($artifact in $runtimeArtifacts) {
            Copy-Item -LiteralPath $artifact.FullName -Destination (Join-Path $jarvisRuntimeDir $artifact.Name) -Force
        }

        # Deploy QNN runtime DLLs from QAIRT SDK (parallel to OpenCL DLL copy in Adreno script)
        $qairtLibDir = Join-Path $qairtSdkPath "lib\aarch64-windows-msvc"
        if (-not (Test-Path $qairtLibDir)) {
            $qairtLibDir = Join-Path $qairtSdkPath "lib\arm64x-windows-msvc"
        }
        if (Test-Path $qairtLibDir) {
            $qairtDlls = Get-ChildItem -LiteralPath $qairtLibDir -File -Filter "*.dll" | Where-Object {
                $_.Name -match "^Qnn(Htp|System)"
            }
            foreach ($dll in $qairtDlls) {
                Copy-Item -LiteralPath $dll.FullName -Destination (Join-Path $jarvisRuntimeDir $dll.Name) -Force
            }
            Write-Host "Copied QNN runtime DLLs: $($qairtDlls.Name -join ', ')"
        }

        $stagedHtpSkels = Get-ChildItem -LiteralPath $jarvisRuntimeDir -File -Filter "libggml-htp-v*.so" -ErrorAction SilentlyContinue
        if ($stagedHtpSkels.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace($resolvedHexagonHtpCert)) {
            Generate-CatalogFile -stagedDir $jarvisRuntimeDir -sdkBin $resolvedWindowsSdkBin -certPfx $resolvedHexagonHtpCert
        }

        $stagedHtpCatalog = Join-Path $jarvisRuntimeDir "libggml-htp.cat"
        if ($stagedHtpSkels.Count -gt 0 -and -not (Test-Path $stagedHtpCatalog)) {
            Write-Warning "Staged HTP skel libraries but libggml-htp.cat is missing. Windows Hexagon session creation may fail until HTP skel signing/test-signing is configured."
        }

        Write-Host "Copied llama-server.exe and $($runtimeArtifacts.Count - 1) runtime sidecar artifact(s)."
        Write-Host "Staged standalone QNN runtime sidecar files successfully."
    }

    Write-Host ""
    Write-Host "Build helper completed. Runtime artifacts staged in:"
    Write-Host "  $jarvisRuntimeDir"
    Write-Host ""
    Write-Host "Smoke test before JARVIS validation:"
    Write-Host "  cd $jarvisRuntimeDir"
    Write-Host "  `$env:QAIRT_SDK_PATH = `"$qairtSdkPath`""
    Write-Host "  `$env:Path = `"<QAIRT_RUNTIME_DLL_DIR>;`" + `$env:Path"
    Write-Host "  .\llama-server.exe --list-devices"
    Write-Host ""
    Write-Host "Expected evidence:"
    Write-Host "  - QNN, Hexagon, HTP, or Qualcomm NPU appears as an available backend/device."
    Write-Host "  - CPU-only output is not sufficient for the windows_arm64_npu_qualcomm_qnn profile."
}
finally {
    # Ensure transcript is always closed, even on failure.
    if ($transcriptStarted) {
        Stop-Transcript
    }
}