# Build llama.cpp for Windows ARM64 Qualcomm Adreno OpenCL

This sheet is for end-user/manual build-out of the Qualcomm Adreno OpenCL llama.cpp sidecar on a Windows ARM64 Snapdragon system. It does not automate repo setup and does not modify JARVISv7 runtime code.

The expected output is a local runtime staged for this repo at:

```text
runtimes\llama.cpp\windows-arm64-adreno-opencl\llama-server.exe
runtimes\llama.cpp\windows-arm64-adreno-opencl\OpenCL.dll
```

The repo should consume that sidecar only after it exists locally with any required adjacent DLLs.

## Recommended Helper Script
Run from `docs` location [jarvis-arm-llamacpp.ps1](jarvis-arm-llamacpp.ps1)

## Target Machine

- Windows on ARM64.
- Qualcomm Snapdragon system with Adreno GPU.
- Current Windows display/GPU drivers installed.
- JARVISv7 cloned locally.
- Visual Studio Community installed with the ARM64 native C++ tooling listed below.

## Visual Studio Community Tools

This user builds with Visual Studio Community and the attached `jarvis-arm.vsconfig`. Import it through Visual Studio Installer or use it as a checklist.

Minimum relevant components from that config:

- `Microsoft.VisualStudio.Workload.NativeDesktop`
- `Microsoft.VisualStudio.ComponentGroup.NativeDesktop.Core`
- `Microsoft.VisualStudio.Component.CoreEditor`
- `Microsoft.VisualStudio.Component.VC.CoreIde`
- `Microsoft.VisualStudio.Component.VC.Tools.ARM64`
- `Microsoft.VisualStudio.Component.VC.Tools.ARM64EC`
- `Microsoft.VisualStudio.Component.VC.Tools.x86.x64`
- `Microsoft.VisualStudio.Component.VC.CMake.Project`
- `Microsoft.VisualStudio.Component.VC.Llvm.Clang`
- `Microsoft.VisualStudio.Component.VC.Llvm.ClangToolset`
- `Microsoft.VisualStudio.ComponentGroup.NativeDesktop.Llvm.Clang`
- `Microsoft.VisualStudio.ComponentGroup.WebToolsExtensions.CMake`
- `Microsoft.Component.MSBuild`
- `Microsoft.VisualStudio.Component.Windows11SDK.26100`
- `Microsoft.VisualStudio.Component.VC.Redist.14.Latest`
- `Microsoft.VisualStudio.Component.Vcpkg`

Optional but already present in the config:

- `Microsoft.VisualStudio.Component.VC.ATL`
- `Microsoft.VisualStudio.Component.VC.ATL.ARM64`
- `Microsoft.VisualStudio.Component.VC.ASAN`
- `Microsoft.VisualStudio.Component.VC.DiagnosticTools`
- `Microsoft.VisualStudio.Component.VC.CppBuildInsights`
- `Microsoft.VisualStudio.Component.VC.TestAdapterForBoostTest`
- `Microsoft.VisualStudio.Component.VC.TestAdapterForGoogleTest`

To import the config into an existing Community install, close Visual Studio, open Visual Studio Installer, choose the Community product card, then use `More > Import configuration`.

Programmatic import example:

```powershell
& "C:\Program Files (x86)\Microsoft Visual Studio\Installer\setup.exe" modify `
  --installPath "C:\Program Files\Microsoft Visual Studio\18\Community" `
  --config "\docs\jarvis-arm.vsconfig" `
  --passive
```

Adjust the `--installPath` if Visual Studio is installed elsewhere.

## Install Command-Line Tools

Install or verify CMake, Ninja, LLVM, and Git. These can be installed with `winget`:

```powershell
winget install --id Kitware.CMake --source winget
winget install --id Ninja-build.Ninja --source winget
winget install --id LLVM.LLVM --source winget
winget install --id Git.Git --source winget
```

Verify:

```powershell
where.exe cmake
cmake --version
where.exe ninja
ninja --version
where.exe git
git --version
```

Do not use `llvm-config --version` as a Windows check. The LLVM packages available to this user expose tools such as `clang.exe`, `llvm-ar.exe`, and `llvm-lib.exe`, but do not include `llvm-config.exe`.

Use **Developer PowerShell for VS** or **Developer Command Prompt for VS** for the build, then initialize the ARM64 environment with `vcvarsall.bat arm64`. The VS LLVM tools used by the working build resolved from the ARM64-specific bin directory:

```text
C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\Llvm\ARM64\bin
```

Verify the Visual Studio LLVM tools directly:

```powershell
$vsLlvmBin = "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\Llvm\ARM64\bin"
& "$vsLlvmBin\clang-cl.exe" --version
where.exe clang-cl
```

If the winget LLVM package is installed, it can be checked separately:

```powershell
$wingetLlvmBin = "C:\Program Files\LLVM\bin"
if (Test-Path "$wingetLlvmBin\clang.exe") { & "$wingetLlvmBin\clang.exe" --version }
if (Test-Path "$wingetLlvmBin\llvm-ar.exe") { & "$wingetLlvmBin\llvm-ar.exe" --version }
```

If `clang-cl` is not found in a plain shell, launch a VS developer shell or run:

```powershell
& "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat" arm64
```

The helper script below imports that environment into the current PowerShell process before configuring CMake.

## Using Helper Script

From the repo root, run the checked-in operator helper:

```powershell
.\docs\jarvis-arm-llamacpp.ps1
```

The helper keeps third-party clones under `D:\WORK\jarvis-dev\llm`, builds OpenCL-Headers, builds OpenCL-ICD-Loader, builds llama.cpp with `GGML_OPENCL=ON`, and stages only the runtime artifacts JARVIS consumes:

```text
runtimes\llama.cpp\windows-arm64-adreno-opencl\llama-server.exe
runtimes\llama.cpp\windows-arm64-adreno-opencl\OpenCL.dll
```

Use the manual sections below when you need to inspect or rerun individual build phases.

## Workspace Layout

Keep third-party build work outside the repo. This example uses:

```powershell
$jarvisRoot = "D:\WORK\CODE\GitHub\bentman\Repositories\JARVISv7"
$jarvisDevRoot = "D:\WORK\jarvis-dev\llm"
$gitOpenClPrefix = "$jarvisDevRoot\opencl"
$gitLlamaRoot = "$jarvisDevRoot\llama.cpp"
if (!(Test-Path $jarvisDevRoot)) {New-Item -ItemType Directory -Force $jarvisDevRoot}
```

## Build OpenCL Headers

```powershell
Set-Location $jarvisDevRoot
git clone https://github.com/KhronosGroup/OpenCL-Headers
Set-Location "$jarvisDevRoot\OpenCL-Headers"
New-Item -ItemType Directory -Force build
Set-Location build

cmake .. -G Ninja `
  -DBUILD_TESTING=OFF `
  -DOPENCL_HEADERS_BUILD_TESTING=OFF `
  -DOPENCL_HEADERS_BUILD_CXX_TESTS=OFF `
  -DCMAKE_INSTALL_PREFIX="$gitOpenClPrefix"

cmake --build . --target install
```

## Build OpenCL ICD Loader

```powershell
Set-Location $jarvisDevRoot
git clone https://github.com/KhronosGroup/OpenCL-ICD-Loader
Set-Location "$jarvisDevRoot\OpenCL-ICD-Loader"
New-Item -ItemType Directory -Force build
Set-Location build

cmake .. -G Ninja `
  -DCMAKE_BUILD_TYPE=Release `
  -DCMAKE_PREFIX_PATH="$gitOpenClPrefix" `
  -DCMAKE_INSTALL_PREFIX="$gitOpenClPrefix"

cmake --build . --target install
```

Expected result:

```text
$gitOpenClPrefix\include\CL\*.h
$gitOpenClPrefix\lib\OpenCL.lib
```

Verify the ICD loader import library is ARM64. If this reports `COFF-i386`, delete the OpenCL-ICD-Loader build directory and reconfigure from the VS ARM64 environment.

```powershell
llvm-readobj --file-headers "$gitOpenClPrefix\lib\OpenCL.lib"
```

Expected key lines:

```text
Format: COFF-ARM64
Arch: aarch64
Machine: IMAGE_FILE_MACHINE_ARM64
```

## Build llama.cpp With Adreno OpenCL

Use the upstream llama.cpp source. For repeatability, prefer a known commit or release tag instead of an unpinned moving branch once a build is proven.

```powershell
Set-Location $jarvisDevRoot
git clone https://github.com/ggml-org/llama.cpp
Set-Location $gitLlamaRoot
```

If rebuilding an existing clone:

```powershell
Set-Location $gitLlamaRoot
git pull
```

Configure:

```powershell
Set-Location $gitLlamaRoot
New-Item -ItemType Directory -Force build-arm64-adreno-opencl
Set-Location build-arm64-adreno-opencl

cmake .. -G Ninja `
  -DCMAKE_C_COMPILER=clang-cl `
  -DCMAKE_CXX_COMPILER=clang-cl `
  -DCMAKE_BUILD_TYPE=Release `
  -DCMAKE_PREFIX_PATH="$gitOpenClPrefix" `
  -DBUILD_SHARED_LIBS=OFF `
  -DGGML_OPENMP=OFF `
  -DGGML_OPENCL=ON
```

Build:

```powershell
ninja
```

Expected output directory:

```text
$gitLlamaRoot\build-arm64-adreno-opencl\bin
```

The files of interest are normally:

```text
llama-server.exe
llama-cli.exe
```

The staged JARVIS sidecar needs `llama-server.exe` from the llama.cpp build and `OpenCL.dll` from the OpenCL ICD loader install prefix.

## Smoke-Test Outside JARVISv7

First list devices:

```powershell
Set-Location "$gitLlamaRoot\build-arm64-adreno-opencl\bin"
.\llama-server.exe --list-devices
```

Look for an OpenCL device that identifies the Qualcomm/Adreno GPU. If only CPU devices appear, stop and check Windows GPU drivers, OpenCL ICD registration, and the OpenCL loader/header build.

Run a direct llama.cpp prompt test with a known local GGUF:

```powershell
.\llama-cli.exe `
  -m "$jarvisRoot\models\llm\assistant-small-q4\qwen2.5-0.5b-instruct-q4_k_m.gguf" `
  -ngl 99 `
  -b 128 `
  -c 2048 `
  -p "Say one short sentence about local inference."
```

Notes:

- `-ngl 99` requests GPU offload.
- `-b 128` matches Qualcomm's example batch size for Adreno OpenCL.
- Qualcomm notes the backend is currently optimized for `Q4_0`; JARVISv7's current small assistant model may use a different quantization. Treat performance as unproven until measured on this host.

If llama.cpp logs do not mention OpenCL/Adreno device use, do not stage the artifact as proven.

## Stage the Sidecar in JARVISv7

From the repo root:

```powershell
Set-Location "$jarvisRoot"
New-Item -ItemType Directory -Force "runtimes\llama.cpp\windows-arm64-adreno-opencl"
```

Copy the built server and OpenCL loader DLL:

```powershell
Copy-Item "$gitLlamaRoot\build-arm64-adreno-opencl\bin\llama-server.exe" `
  "runtimes\llama.cpp\windows-arm64-adreno-opencl\llama-server.exe" `
  -Force

Copy-Item "$gitOpenClPrefix\bin\OpenCL.dll" `
  "runtimes\llama.cpp\windows-arm64-adreno-opencl\OpenCL.dll" `
  -Force
```

Do not commit generated runtime binaries. They belong under ignored local runtime artifact storage.

## Verify Repo Consumption

Run from the repo root with the repo virtual environment:

```powershell
backend\.venv\Scripts\python scripts\ensure_models.py --family llm --model assistant-small-q4 --verify-only
```

Expected when the artifacts are staged on a Windows ARM64 Qualcomm Adreno host:

- The profile can become eligible only on Windows ARM64 with Qualcomm GPU evidence and Adreno OpenCL evidence.
- The selected profile should be `windows_arm64_gpu_qualcomm_adreno_opencl`.
- The preflight token set should include `opencl:adreno`.
- QNN/Hexagon profile state should remain independent.

Live proof command once the selector is expected to choose Adreno OpenCL:

```powershell
cmd /c "set USE_LOCAL_MODEL=true&& set LLAMA_CPP_MANAGED=true&& backend\.venv\Scripts\python scripts\run_jarvis.py --text-only --turns 1 --trace-to reports\validation\slice_s_adreno_opencl_live"
```

Required live evidence:

- selected profile: `windows_arm64_gpu_qualcomm_adreno_opencl`
- accelerator: `gpu.opencl.adreno`
- llama.cpp logs mention OpenCL and the Qualcomm/Adreno device
- response is non-empty
- process exits cleanly

## Troubleshooting

- `clang` not found: use Developer PowerShell for VS or add the VS LLVM bin directory to `PATH`.
- `cmake` cannot find OpenCL: confirm `$gitOpenClPrefix\include\CL` and `$gitOpenClPrefix\lib\OpenCL.lib` exist, then rerun CMake with `-DCMAKE_PREFIX_PATH="$gitOpenClPrefix"`.
- Device listing does not show Adreno: update Qualcomm/Windows GPU drivers and confirm the OpenCL ICD is registered.
- Build emits x86/x64 objects: confirm `vcvarsall.bat arm64` was imported and `where.exe clang-cl` resolves the VS `VC\Tools\Llvm\ARM64\bin` compiler before CMake configure.
- JARVISv7 still selects CPU: run `scripts\ensure_models.py --family llm --model assistant-small-q4 --verify-only` and confirm `opencl:adreno` appears in preflight and the staged runtime directory contains both `llama-server.exe` and `OpenCL.dll`.

## Citations

- Qualcomm Developer Blog, "Introducing the new OpenCL GPU backend in llama.cpp for Qualcomm Adreno GPUs", Feb. 17, 2025. Qualcomm states the Adreno OpenCL backend is upstreamed/integrated, based on OpenCL 3.0, tested on Windows 11 Snapdragon X Elite/X Plus laptops, and documents the Windows-on-Snapdragon build using Visual Studio, CMake, Ninja, LLVM, OpenCL-Headers, OpenCL-ICD-Loader, and `-DGGML_OPENCL=ON`.
- ggml-org llama.cpp `docs/build.md`, OpenCL / Windows Arm64 section. Upstream build docs show the OpenCL headers, OpenCL ICD loader, Windows ARM64 LLVM toolchain, and `-DGGML_OPENCL=ON` build flow.
- Microsoft Learn, "Import or export installation configurations". Microsoft documents using `.vsconfig` files to import Visual Studio workloads/components and the `setup.exe modify --config ...` command shape.
