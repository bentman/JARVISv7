# JARVIS ARM llama.cpp Adreno OpenCL Helper

This document explains how to use `docs\jarvis-arm-llamacpp.ps1` to build and stage a local llama.cpp sidecar for Windows ARM64 Snapdragon systems with Qualcomm Adreno OpenCL.  

**WARNING:** This process is a "ram-hog" (~3.5+ GB on my 16GB laptop).

The normal workflow runs directly on the ARM64 Snapdragon host. The helper keeps third-party source/build trees outside the repo and stages only the runtime files JARVIS consumes.

This helper does not modify JARVIS runtime code.

## Output

The expected local runtime sidecar is:

```text
runtimes\llama.cpp\windows-arm64-adreno-opencl\llama-server.exe
runtimes\llama.cpp\windows-arm64-adreno-opencl\OpenCL.dll
```

The sidecar is consumed by the ARM64 Adreno OpenCL llama.cpp profile after the files exist locally and pass validation.

Do not commit generated runtime binaries.

## Requirements

Run this on the ARM64 target machine.

Required:

- Windows ARM64 Snapdragon system.
- Qualcomm Adreno GPU with current Windows display/GPU drivers.
- JARVISv7 cloned locally.
- Visual Studio Community or Build Tools with ARM64 C++ tooling.
- CMake, Ninja, Git, and LLVM/Clang tools.
- A local GGUF model already available to JARVIS.

Recommended:

- Import `docs\jarvis-arm.vsconfig` through Visual Studio Installer.
- Use Developer PowerShell for Visual Studio, or let the helper initialize the ARM64 Visual Studio environment.

## Install or verify build tools

The Visual Studio configuration file is the preferred setup path:

```text
docs\jarvis-arm.vsconfig
```

In Visual Studio Installer, use:

```text
More > Import configuration
```

Install or verify command-line tools:

```powershell
winget install --id Kitware.CMake --source winget
winget install --id Ninja-build.Ninja --source winget
winget install --id Git.Git --source winget
```

Check the tools are visible:

```powershell
cmake --version
ninja --version
git --version
```

If `clang-cl` is not visible, use a Visual Studio developer shell or ensure the ARM64 C++ tools are installed.

## Use the helper

Run from the JARVIS repo root.

Dry run:

```powershell
.\docs\jarvis-arm-llamacpp.ps1 -WhatIf
```

Build and stage:

```powershell
.\docs\jarvis-arm-llamacpp.ps1
```

The helper performs the build phases for you:

- Initializes the Visual Studio ARM64 build environment.
- Clones or updates OpenCL headers.
- Clones or updates the OpenCL ICD loader.
- Clones or updates llama.cpp.
- Builds llama.cpp with OpenCL enabled.
- Stages only the JARVIS runtime sidecar files.

Third-party work is kept outside the repo by default:

```text
<jarvisDevRoot>\OpenCL-Headers
<jarvisDevRoot>\OpenCL-ICD-Loader
<jarvisDevRoot>\llama.cpp
<jarvisDevRoot>\opencl
```

The repo receives only:

```text
runtimes\llama.cpp\windows-arm64-adreno-opencl\
```

## Smoke test before JARVIS validation

Before relying on the sidecar, confirm the built llama.cpp binary can see the expected accelerator.

From the staged or build output folder:

```powershell
.\llama-server.exe --list-devices
```

Expected evidence:

- OpenCL appears as an available backend.
- The device list includes a Qualcomm or Adreno GPU.

If only CPU devices appear, stop. Check the Windows GPU driver, OpenCL ICD registration, and the OpenCL loader build before treating the sidecar as valid.

## Validate JARVIS consumption

Run from the repo root with the repo virtual environment.

```powershell
backend\.venv\Scripts\python scripts\ensure_models.py --family llm --model assistant-small-q4 --verify-only
```

Then run a managed local-turn proof:

```powershell
cmd /c "set JARVISV7_LIVE_TESTS=1&& set USE_LOCAL_MODEL=true&& set LLAMA_CPP_MANAGED=true&& set LLM_MODEL_MODE=prod&& backend\.venv\Scripts\python -m pytest backend\tests\runtime\voice\test_llm_llama_cpp_live.py backend\tests\runtime\turn -q -m requires_llama_cpp"
```

Required evidence:

- JARVIS selects the Windows ARM64 Adreno OpenCL llama.cpp profile.
- The profile reports `gpu.opencl.adreno` or equivalent Adreno OpenCL evidence.
- llama.cpp logs mention OpenCL and the Qualcomm/Adreno device.
- The live llama.cpp tests prove the selected prod model/profile metadata and deterministic `ready` response contract.
- The process exits cleanly.

## Manual recovery path

Use the helper first. If it fails, inspect the transcript it writes under the developer workspace.

Manual recovery usually means re-running only one failed phase:

- Visual Studio ARM64 environment setup.
- OpenCL headers build.
- OpenCL ICD loader build.
- llama.cpp OpenCL build.
- Runtime staging.

Do not rewrite JARVIS runtime selection to work around a failed sidecar build. Fix or restage the sidecar first.

## Troubleshooting

`clang-cl` is missing:

- Install Visual Studio ARM64 C++ tools.
- Use Developer PowerShell for Visual Studio.
- Confirm `vcvarsall.bat arm64` initializes successfully.

CMake cannot find OpenCL:

- Confirm the helper built the OpenCL headers and ICD loader.
- Confirm the OpenCL install prefix contains headers and import libraries.
- Rerun the helper after clearing only the failed external build directory.

The ICD loader is the wrong architecture:

- Rebuild from an ARM64 Visual Studio environment.
- Do not reuse x64 or x86 build directories.

llama.cpp builds but does not list Adreno:

- Update Windows GPU drivers.
- Confirm the device exposes OpenCL.
- Confirm `OpenCL.dll` was staged beside `llama-server.exe`.

JARVIS does not select the Adreno profile:

- Verify the staged sidecar path.
- Verify model availability with `ensure_models.py`.
- Confirm preflight reports Adreno/OpenCL evidence.

## References

llama.cpp source and build documentation:

```text
https://github.com/ggml-org/llama.cpp
https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
```

Khronos OpenCL headers and ICD loader:

```text
https://github.com/KhronosGroup/OpenCL-Headers
https://github.com/KhronosGroup/OpenCL-ICD-Loader
https://www.khronos.org/opencl/
```

Visual Studio configuration import and C++ command-line build docs:

```text
https://learn.microsoft.com/en-us/visualstudio/install/import-export-installation-configurations
https://learn.microsoft.com/en-us/cpp/build/building-on-the-command-line
```
