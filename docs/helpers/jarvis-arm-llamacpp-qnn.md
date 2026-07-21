# JARVIS ARM llama.cpp QNN Helper

This document explains how to use `docs\helpers\jarvis-arm-llamacpp-qnn.ps1` to build and stage a local llama.cpp sidecar for Windows ARM64 Snapdragon systems with Qualcomm Hexagon/QNN NPU support.

**WARNING:** This path is experimental. The current repository declares `windows_arm64_npu_qualcomm_qnn` as a degraded/pending-viability profile until a real sidecar binary is built, staged, and validated on the target host. Current upstream llama.cpp Snapdragon support is exposed as the Hexagon backend (`GGML_HEXAGON`), not a stable QNN backend named `GGML_QNN`.

The normal workflow runs directly on the ARM64 Snapdragon host. The helper keeps third-party source/build trees outside the repo and stages only the runtime file JARVIS consumes.

This helper does not modify JARVIS runtime code.

## Output

The expected local runtime sidecar directory is:

```text
runtimes\llama.cpp\windows-arm64-qnn\
```

The sidecar is consumed by the ARM64 QNN llama.cpp profile after `llama-server.exe` and its adjacent llama.cpp runtime DLLs exist locally and pass validation.

Do not commit generated runtime binaries.

## Requirements

Run this on the ARM64 target machine.

Required:

- Windows ARM64 Snapdragon system.
- Qualcomm NPU / Hexagon HTP-capable platform.
- JARVISv7 cloned locally.
- Visual Studio Community or Build Tools with ARM64 C++ tooling.
- CMake, Ninja, and Git.
- Qualcomm AI Engine Direct SDK / QAIRT zip extracted locally.
- Hexagon SDK extracted under the same local Qualcomm package root as QAIRT, or already exposed through `HEXAGON_SDK_ROOT` / `HEXAGON_TOOLS_ROOT`.
- A local GGUF model already available to JARVIS.

Recommended:

- Import `docs\helpers\jarvis-arm.vsconfig` through Visual Studio Installer.
- Use Visual Studio Developer PowerShell with ARM64 tools already loaded.
- Set `QAIRT_SDK_PATH` to the extracted Qualcomm AI Engine Direct SDK / QAIRT root before running the helper.

## Qualcomm AI Engine Direct SDK / QAIRT

JARVIS uses `QAIRT_SDK_PATH` elsewhere for QNN discovery, and this helper follows the same operator-owned SDK path convention.

Prefer the current Qualcomm AI Engine Direct SDK / QAIRT zip download over the older Windows installer when the zip version is newer. Extract the zip to a stable local path and point `QAIRT_SDK_PATH` or the helper's `-QairtSdkPath` argument at the extracted SDK root.

The helper derives the related Hexagon SDK paths from the QAIRT package root. For example, this QAIRT root:

```text
D:\WORK\Qualcomm\v2.46.0.260424\qairt\v2.46.0.260424
```

has package root:

```text
D:\WORK\Qualcomm\v2.46.0.260424
```

The helper then looks for a sibling Hexagon SDK below that package root, such as:

```text
D:\WORK\Qualcomm\v2.46.0.260424\hexagon\
D:\WORK\Qualcomm\v2.46.0.260424\hexagon-sdk\
D:\WORK\Qualcomm\v2.46.0.260424\Hexagon_SDK\
```

The derived Hexagon SDK root must expose `build\cmake\hexagon_fun.cmake` and `incs\`. The helper derives `HEXAGON_TOOLS_ROOT` from `hexagon_sdk.json` when available, or from `tools\HEXAGON_Tools\<version>`.

Use the Qualcomm AI Engine Direct SDK / QAIRT package appropriate for Windows on Snapdragon ARM64 development. The extracted SDK root should expose the QNN headers, import libraries, and runtime DLLs used by QNN/HTP execution.

The helper validates that the QAIRT SDK root contains at least:

```text
<QAIRT_SDK_PATH>\include\
<QAIRT_SDK_PATH>\lib\
<QAIRT_SDK_PATH>\bin\
QnnInterface.h under the SDK tree
QnnHtp.dll under the SDK tree
```

Depending on the SDK version, QNN libraries may live below versioned or architecture-specific subdirectories. The helper searches recursively for `QnnInterface.h` and `QnnHtp.dll` to avoid assuming one exact layout. It also validates the derived Hexagon SDK root before configuring llama.cpp because `GGML_HEXAGON=ON` requires Hexagon SDK build files in addition to QAIRT runtime files.

## Hexagon SDK

QAIRT does not necessarily include the Hexagon SDK files required by llama.cpp's `GGML_HEXAGON=ON` backend. The transcript failure below means the Hexagon SDK is missing or not discoverable:

```text
CMake Error at ggml/src/ggml-hexagon/CMakeLists.txt:5 (message):
  Make sure HEXAGON_SDK_ROOT point to the correct Hexagon SDK installation.
```

Use one of the upstream llama.cpp-documented sources:

- Qualcomm Software Center, Hexagon SDK Community Edition:

  ```text
  https://softwarecenter.qualcomm.com/catalog/item/Hexagon_SDK?version=6.6.0.0
  ```

- Trimmed Snapdragon toolchain package referenced by upstream llama.cpp docs/CI:

  ```text
  https://github.com/snapdragon-toolchain/hexagon-sdk/releases/download/v6.6.0.0/hexagon-sdk-v6.6.0.0-arm64-wos.tar.xz
  ```

Extract the Hexagon SDK under the same local Qualcomm package root as QAIRT. For the default helper path:

```text
D:\WORK\Qualcomm\v2.46.0.260424\qairt\v2.46.0.260424
```

use a sibling directory such as:

```text
D:\WORK\Qualcomm\v2.46.0.260424\hexagon-sdk\
```

Some packages extract with the SDK version as the actual SDK root under that directory:

```text
D:\WORK\Qualcomm\v2.46.0.260424\hexagon-sdk\6.6.0.0\
```

The helper accepts this versioned layout and uses the versioned child directory as `HEXAGON_SDK_ROOT`.

After extraction, the helper expects these files/directories to exist:

```text
D:\WORK\Qualcomm\v2.46.0.260424\hexagon-sdk\6.6.0.0\build\cmake\hexagon_fun.cmake
D:\WORK\Qualcomm\v2.46.0.260424\hexagon-sdk\6.6.0.0\incs\
```

The helper derives `HEXAGON_TOOLS_ROOT` from either:

```text
D:\WORK\Qualcomm\v2.46.0.260424\hexagon-sdk\6.6.0.0\hexagon_sdk.json
```

or:

```text
D:\WORK\Qualcomm\v2.46.0.260424\hexagon-sdk\6.6.0.0\tools\HEXAGON_Tools\<version>\
```

If the Hexagon SDK is extracted somewhere else, set the paths explicitly before running the helper:

```powershell
$env:HEXAGON_SDK_ROOT = "D:\path\to\hexagon-sdk"
$env:HEXAGON_TOOLS_ROOT = "D:\path\to\hexagon-sdk\tools\HEXAGON_Tools\<version>"
```

Windows Snapdragon Hexagon/HTP builds can also require signed HTP ops libraries. If configure succeeds and the build later fails during HTP skel or catalog signing, follow upstream signing setup and provide:

```powershell
$env:HEXAGON_HTP_CERT = "<path-to-your-ggml-htp-v1.pfx>"
$env:WINDOWS_SDK_BIN = "C:\Program Files (x86)\Windows Kits\10\bin\<sdk-version>"
```

Example environment setup for an extracted zip:

```powershell
$env:QAIRT_SDK_PATH = "D:\Qualcomm\QAIRT\v2.46.0.260424"
```

Use the actual extracted SDK root on the target host.

## Install or verify build tools

The Visual Studio configuration file is the preferred setup path:

```text
docs\helpers\jarvis-arm.vsconfig
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

Confirm the current Visual Studio Developer PowerShell is targeting ARM64:

```powershell
Enter-VsDevShell -VsInstallPath $env:VSINSTALLDIR -DevCmdArguments '-arch=arm64 -host_arch=arm64'
$env:VSCMD_ARG_TGT_ARCH
```

Expected output is `arm64`. Then confirm `clang-cl` resolves to the ARM64 LLVM tools path:

```powershell
Get-Command clang-cl.exe
```

If `clang-cl` is not visible, use Visual Studio Developer PowerShell with ARM64 tools loaded or ensure the ARM64 C++ tools are installed.

## Use the helper

Run from the JARVIS repo root.

The helper automatically:
- Initializes the Visual Studio ARM64 build environment using `vcvarsall.bat arm64`.
- Auto-discovers the Windows SDK Kits path to find signature tools (`makecert.exe`, `pvk2pfx.exe`, `signtool.exe`, `inf2cat.exe`).
- Generates a local self-signed test certificate (`ggml-htp-v1.pfx`) in the developer workspace by default (unless `-DisableCertGen` is specified) and attempts to import it into the local machine's Trusted Root/Trusted Publishers store.
- Exports `HEXAGON_HTP_CERT` and `WINDOWS_SDK_BIN` so CMake builds and signs the catalog file (`libggml-htp.cat`) alongside the compiled skeleton files.
- Stages the complete, standalone QNN runtime sidecar files including `llama-server.exe`, `libggml-htp-v*.so`, `libggml-htp.cat`, and matching QNN SDK execution provider libraries (`QnnHtp.dll`, `QnnSystem.dll`, `QnnHtpV*Stub.dll`).

Dry run:

```powershell
.\docs\helpers\jarvis-arm-llamacpp-qnn.ps1 -WhatIf
```

Build and stage:

```powershell
# Standard invocation (automatic certificate generation & registration)
.\docs\helpers\jarvis-arm-llamacpp-qnn.ps1

# Invocation disabling certificate auto-generation
.\docs\helpers\jarvis-arm-llamacpp-qnn.ps1 -DisableCertGen

# Invocation passing custom QAIRT SDK path and Windows SDK bin path
.\docs\helpers\jarvis-arm-llamacpp-qnn.ps1 -QairtSdkPath "D:\Qualcomm\QAIRT\v2.46.0.260424" -WindowsSdkBin "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0"
```

### Windows Host Code-Signing Setup

> [!WARNING]
> **Windows Test-Signing is a hard requirement for Hexagon HTP NPU execution.**
> Because Microsoft and Qualcomm strictly enforce kernel/driver-level digital signatures for custom DSP/NPU code on Windows Snapdragon hosts, self-signed catalog files (`libggml-htp.cat`) will only load when `TESTSIGNING` is active.
>
> If enabling `TESTSIGNING ON` is a blocker for your device (e.g. retail Copilot+ PCs or Surface laptops where secure boot or game anti-cheat compliance must be maintained), you should use the Adreno GPU OpenCL backend ([jarvis-arm-llamacpp.md](jarvis-arm-llamacpp.md)) instead, which runs at native retail security levels without requiring test-signing.

Because the Hexagon NPU driver checks Windows digital signatures when loading HTP skeleton libraries (`.so`), the host system must be configured to trust the certificate used to sign the catalog file (`libggml-htp.cat`).

Run the following commands from an **elevated Administrator PowerShell or Command Prompt**:

1. **Enable Windows Test-Signing Mode:**
   ```powershell
   bcdedit /set TESTSIGNING ON
   ```
   > [!IMPORTANT]
   > You must reboot your computer after running this command for testsigning to take effect.

2. **Trust the Developer Certificate:**
   Import the auto-generated certificate (`ggml-htp-v1.cer`) into the Local Machine's Trusted Root Certification Authorities and Trusted Publishers stores:
   ```powershell
   certutil -addstore Root "D:\WORK\jarvis-dev\llm-qnn\ggml-htp-v1.cer"
   certutil -addstore TrustedPublisher "D:\WORK\jarvis-dev\llm-qnn\ggml-htp-v1.cer"
   ```

Third-party build logs and checkouts are kept outside the repo:

```text
<jarvisDevRoot>\llama.cpp
```

The repo receives the self-contained sidecar directory:

```text
runtimes\llama.cpp\windows-arm64-qnn\llama-server.exe
runtimes\llama.cpp\windows-arm64-qnn\*.dll
runtimes\llama.cpp\windows-arm64-qnn\libggml-htp-v*.so
runtimes\llama.cpp\windows-arm64-qnn\libggml-htp.cat
```

## QNN / Hexagon build options

The helper currently passes these accelerator-related CMake definitions:

```text
-DGGML_OPENMP=OFF
-DGGML_HEXAGON=ON
-DHEXAGON_SDK_ROOT=<derived Hexagon SDK root>
-DHEXAGON_TOOLS_ROOT=<derived Hexagon tools root>
-DPREBUILT_LIB_DIR=toolv19_v81
-DQAIRT_SDK_PATH=<QAIRT_SDK_PATH>
-DGGML_QNN_SDK_PATH=<QAIRT_SDK_PATH>
-DGGML_QNN_BUILD_STUB=OFF
```

These are intentionally isolated in the helper because llama.cpp Snapdragon acceleration support is narrower and more version-sensitive than the existing Adreno OpenCL path. In the inspected upstream checkout, `GGML_QNN` is not a recognized CMake option; it is recorded as `UNINITIALIZED` and the resulting build can remain CPU-only. A valid configure must report a Hexagon/QNN backend in `GGML_AVAILABLE_BACKENDS`, not only `ggml-cpu`.

## Smoke test before JARVIS validation

Before relying on the sidecar, confirm the built llama.cpp binary can see the expected accelerator.

From the staged or build output folder:

```powershell
$env:QAIRT_SDK_PATH = "D:\Qualcomm\QAIRT\v2.46.0.260424"
$env:Path = "<QAIRT_RUNTIME_DLL_DIR>;" + $env:Path
.\llama-server.exe --list-devices
```

Use the actual QAIRT runtime DLL directory for `<QAIRT_RUNTIME_DLL_DIR>`. It is usually the directory that contains `QnnHtp.dll`, `QnnSystem.dll`, or `QnnInterface.dll` under the extracted SDK. `QAIRT_SDK_PATH` tells tools where the SDK is, but native Windows DLL loading still requires dependent DLLs to be beside the EXE or reachable through the loader search path.

Expected evidence:

- QNN, Hexagon, HTP, or Qualcomm NPU appears as an available backend/device.
- CPU-only output is not sufficient for the `windows_arm64_npu_qualcomm_qnn` profile.

If only CPU devices appear, stop. Check the QAIRT SDK path, Windows Snapdragon drivers, QNN/HTP runtime DLL discovery, and llama.cpp QNN build configuration before treating the sidecar as valid.

## Validate JARVIS consumption

Run from the repo root with the repo virtual environment.

```powershell
backend\.venv\Scripts\python scripts\ensure_models.py --family llm --model assistant-qwen3-4b-q4-portable --verify-only
```

Then run profile validation:

```powershell
backend\.venv\Scripts\python scripts\validate_backend.py profile
```

Then run a managed local-turn proof:

```powershell
cmd /c "set JARVISV7_LIVE_TESTS=1&& set USE_LOCAL_MODEL=true&& set LLAMA_CPP_MANAGED=true&& set LLM_MODEL_MODE=prod&& set QAIRT_SDK_PATH=D:\Qualcomm\QAIRT\v2.46.0.260424&& backend\.venv\Scripts\python -m pytest backend\tests\runtime\voice\test_llm_llama_cpp_live.py backend\tests\runtime\turn -q -m requires_llama_cpp"
```

Required evidence:

- JARVIS selects the Windows ARM64 QNN llama.cpp profile.
- The profile reports `npu.qnn` or equivalent QNN/HTP evidence.
- llama.cpp logs mention QNN, Hexagon, HTP, or Qualcomm NPU device use.
- The live llama.cpp tests prove the selected prod model/profile metadata and deterministic ready response contract.
- The process exits cleanly.

## Current repository boundary

The repository already declares the QNN LLM profile in `config\models\llm.yaml` as:

```text
windows_arm64_npu_qualcomm_qnn
accelerator: npu.qnn
binary_path: runtimes/llama.cpp/windows-arm64-qnn/llama-server.exe
validation_status: declared-degraded
```

That declaration is not runtime proof. It becomes a real capability only after the sidecar exists locally and live validation shows the selected profile using QNN/HTP rather than CPU fallback.

## Manual recovery path

Use the helper first. If it fails, inspect the transcript it writes under the developer workspace.

Manual recovery usually means re-running only one failed phase:

- Visual Studio ARM64 environment setup.
- QAIRT SDK path validation.
- llama.cpp QNN configure.
- llama.cpp QNN build.
- Runtime staging.

Do not rewrite JARVIS runtime selection to work around a failed sidecar build. Fix or restage the sidecar first.

## Troubleshooting

`QAIRT_SDK_PATH` is missing:

- Download and extract the current Qualcomm AI Engine Direct SDK / QAIRT zip.
- Set `QAIRT_SDK_PATH` to the extracted SDK root.
- Re-run the helper with `-QairtSdkPath` if the environment variable is not desirable.

`QnnHtp.dll` is missing:

- Confirm the SDK package includes Hexagon HTP runtime components.
- Confirm the SDK root points at the full SDK, not a nested include/lib directory.

`QnnInterface.h` is missing:

- Confirm the SDK package includes QNN development headers.
- Confirm the helper points at the SDK root.

`llama-server-impl.dll` is missing:

- Re-run the helper after confirming the llama.cpp build output contains DLLs under `build-arm64-qnn\bin`.
- The staged runtime directory must include `llama-server.exe` plus adjacent llama.cpp DLLs such as `llama-server-impl.dll`, `llama.dll`, `llama-common.dll`, and `ggml*.dll`.
- A tiny `llama-server.exe` by itself is not a complete modern llama.cpp runtime on Windows.

`ggml-hex: failed to open session 0 : error 0x80000406`:

- Confirm the staged runtime directory includes the generated HTP skel libraries: `libggml-htp-v73.so`, `libggml-htp-v75.so`, `libggml-htp-v79.so`, and `libggml-htp-v81.so`.
- If those `.so` files are present but `libggml-htp.cat` is missing, the remaining blocker is likely Windows Snapdragon HTP skel signing/test-signing or driver trust. Configure `HEXAGON_HTP_CERT` and `WINDOWS_SDK_BIN`, enable Windows test-signing as required by upstream Snapdragon Hexagon instructions, rebuild, and confirm `libggml-htp.cat` is staged beside the `.so` files.
- Re-run the smoke test from the staged runtime directory after prepending the QAIRT runtime DLL directory to `PATH`.

QAIRT DLL load errors after llama.cpp DLLs are staged:

- Keep `QAIRT_SDK_PATH` set in the same shell used to run `llama-server.exe`.
- Prepend the QAIRT runtime DLL directory containing `QnnHtp.dll`, `QnnSystem.dll`, or `QnnInterface.dll` to `PATH` before running the native EXE.
- If the server starts but lists CPU only, check Qualcomm NPU / HTP drivers and the llama.cpp QNN CMake configuration before treating the sidecar as valid.

`clang-cl` is missing or the Visual Studio architecture is not ARM64:

- Install Visual Studio ARM64 C++ tools.
- Open Visual Studio Developer PowerShell, then run `Enter-VsDevShell -VsInstallPath $env:VSINSTALLDIR -DevCmdArguments '-arch=arm64 -host_arch=arm64'` before running the helper.
- Confirm `$env:VSCMD_ARG_TGT_ARCH` is `arm64` and `clang-cl.exe` resolves under the Visual Studio ARM64 LLVM tools path.

CMake does not recognize QNN options:

- Confirm the llama.cpp checkout contains QNN backend support.
- Check upstream llama.cpp CMake option names for the installed revision. Current Snapdragon docs use `GGML_HEXAGON=ON` plus `HEXAGON_SDK_ROOT` / `HEXAGON_TOOLS_ROOT`, not a stable `GGML_QNN` backend option.
- Update the helper's `Get-QnnCMakeArguments` function only after confirming the upstream contract.

`hexagon_fun.cmake` reports `string sub-command FIND requires 3 or 4 parameters`:

- Qualcomm's Hexagon CMake helper expects `PREBUILT_LIB_DIR` to be set when it is included from the top-level Windows configure.
- The helper passes `-DPREBUILT_LIB_DIR=toolv19_v81` for the top-level configure. The per-DSP HTP skel builds still pass their own `PREBUILT_LIB_DIR` values from llama.cpp.

`HEXAGON_SDK_ROOT` cannot be derived:

- Confirm the Hexagon SDK is extracted beside QAIRT under the same Qualcomm package root. For `D:\WORK\Qualcomm\v2.46.0.260424\qairt\v2.46.0.260424`, the helper searches under `D:\WORK\Qualcomm\v2.46.0.260424`.
- Confirm the derived SDK root contains `build\cmake\hexagon_fun.cmake` and `incs\`. For the trimmed Snapdragon package, the actual SDK root is commonly the versioned child, such as `hexagon-sdk\6.6.0.0`.
- If the SDK is intentionally elsewhere, set `HEXAGON_SDK_ROOT` and `HEXAGON_TOOLS_ROOT` before running the helper.

Configure succeeds but `--list-devices` is empty:

- Inspect `build-arm64-qnn\CMakeCache.txt`.
- If `GGML_AVAILABLE_BACKENDS:INTERNAL=ggml-cpu`, the build is CPU-only even if `GGML_QNN:UNINITIALIZED=ON` appears.
- Follow upstream `docs\backend\snapdragon\windows.md`: set `HEXAGON_SDK_ROOT`, `HEXAGON_TOOLS_ROOT`, and signing prerequisites for HTP ops libraries, then configure with `GGML_HEXAGON=ON`.
- Do not stage or claim the sidecar as QNN-valid until `--list-devices` or runtime logs show Hexagon/QNN/HTP.

llama.cpp builds but does not list QNN/HTP:

- Confirm `QAIRT_SDK_PATH` is set in the same shell used to run `llama-server.exe`.
- Confirm Qualcomm NPU / HTP drivers are installed on the target host.
- Confirm the build did not silently produce a CPU-only binary.

JARVIS does not select the QNN profile:

- Verify the staged sidecar path.
- Verify model availability with `ensure_models.py`.
- Confirm preflight reports QNN provider and HTP evidence.
- Confirm the selected LLM policy can map the current host to `windows_arm64_npu_qualcomm_qnn`.

## References

llama.cpp source and build documentation:

```text
https://github.com/ggml-org/llama.cpp
https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
```

Qualcomm AI Engine Direct / QAIRT documentation and downloads:

```text
https://developer.qualcomm.com/software/qualcomm-ai-engine-direct-sdk
https://docs.qualcomm.com/bundle/publicresource/topics/80-63442-2/introduction.html
```

Visual Studio configuration import and C++ command-line build docs:

```text
https://learn.microsoft.com/en-us/visualstudio/install/import-export-installation-configurations
https://learn.microsoft.com/en-us/cpp/build/building-on-the-command-line
```
