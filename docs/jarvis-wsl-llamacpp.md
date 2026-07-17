# JARVIS Linux AMD64/WSL2 llama.cpp CUDA Build

## Purpose

`docs/jarvis-wsl-llamacpp.sh` builds the pinned JARVIS llama.cpp CUDA sidecar on Linux AMD64/WSL2 and stages only the validated runtime into:

```text
runtimes/llama.cpp/linux-amd64-cuda
```

The source checkout, CMake tree, prior-runtime backup, lock, and transcript remain outside the repository under:

```text
~/WORK/CODE/jarvis-dev/llamacpp-cuda
```

This follows the adjacent ARM/QNN helper pattern: use an external developer workspace, validate the accelerator backend before deployment, and copy only runtime artifacts into JARVIS.

## Pinned build inputs

| Input | Value |
|---|---|
| llama.cpp tag | `b9704` |
| llama.cpp commit | `10786217e9d40c848ac0133cbe9c5f22a52421bb` |
| llama.cpp build number | `9704` |
| CUDA Toolkit | `/usr/local/cuda-13.3` |
| CUDA compiler | `/usr/local/cuda-13.3/bin/nvcc` |
| NVIDIA architecture | `86` (RTX 3060/Ampere) |
| Generator | Ninja |
| Build type | Release |
| Shared libraries | Enabled |

The helper uses a real Git checkout at the pinned commit. This preserves upstream build identity and prevents extracted-tarball metadata from producing `0`, `unknown`, or stale library versions.

## Safety and repeatability

The helper:

- changes CUDA environment variables only for itself and its child processes;
- never installs or changes NVIDIA drivers or CUDA packages;
- uses a provenance-specific build directory outside JARVIS;
- fingerprints the source, CUDA compiler, CUDA architecture, host compiler, CMake version, generator, and build configuration;
- discards the external CMake tree automatically when the fingerprint changes;
- removes abandoned `linux-amd64-cuda.stage.*` directories before creating a new stage;
- preserves shared-library symlinks while staging;
- validates build number and commit before replacing the current runtime;
- verifies `$ORIGIN`, adjacent llama.cpp library resolution, CUDA 13.3 runtime resolution, WSL `libcuda.so.1`, and CUDA device enumeration;
- replaces the runtime only after all staged checks pass.

A failed build does not replace the current runtime.

## Prerequisites

The host must already provide:

- WSL2 Linux AMD64;
- an NVIDIA GPU exposed to WSL;
- CUDA Toolkit 13.3 at `/usr/local/cuda-13.3`;
- the repository Python environment at `backend/.venv`;
- Git, CMake, Ninja, GCC/G++, binutils, libc-bin, coreutils, and util-linux.

Verify GPU and toolkit access:

```bash
nvidia-smi
/usr/local/cuda-13.3/bin/nvcc --version
test -r /usr/lib/wsl/lib/libcuda.so.1 && echo "PASS: WSL libcuda present"
```

CUDA 13.3 supports GCC major versions 6 through 15 on Linux x86_64. The helper records the actual host compiler in its build fingerprint.

## Run

From the JARVIS repository root:

```bash
bash docs/jarvis-wsl-llamacpp.sh
```

To let the helper install only missing generic Ubuntu build tools:

```bash
bash docs/jarvis-wsl-llamacpp.sh --install-build-prereqs
```

To use a different external workspace:

```bash
bash docs/jarvis-wsl-llamacpp.sh \
  --dev-root "$HOME/WORK/CODE/jarvis-dev/llamacpp-cuda"
```

The transcript defaults to a timestamped file under the external workspace. Override it with:

```bash
bash docs/jarvis-wsl-llamacpp.sh \
  --transcript "$HOME/WORK/CODE/jarvis-dev/llamacpp-cuda/build.log"
```

## Expected staged evidence

Before deployment, the helper requires:

```text
llama-server
libllama-server-impl.so
libllama-common.so.0
libggml.so
libggml-base.so
libggml-cpu.so
libggml-cuda.so
libllama.so
libmtmd.so
```

It also requires versioned libraries matching build `9704`, including:

```text
libllama.so.0.0.9704
libllama-common.so.0.0.9704
libmtmd.so.0.0.9704
```

`llama-server --version` must identify build `9704` and the pinned commit. `ldd` must resolve llama.cpp libraries from the staging directory, CUDA 13.3 libraries from `/usr/local/cuda-13.3`, and the NVIDIA driver library from `/usr/lib/wsl/lib/libcuda.so.1`.

`llama-server --list-devices` must enumerate the CUDA/NVIDIA device. CPU-only output is not sufficient for `linux_amd64_gpu_nvidia_cuda`.

## Production model acquisition

Production mode selects only the current host’s configured LLM when invoked explicitly:

```bash
backend/.venv/bin/python scripts/ensure_models.py --family llm
```

Verify without downloading:

```bash
backend/.venv/bin/python scripts/ensure_models.py --family llm --verify-only
```

Do not use `--all-llm` unless every configured LLM is intentionally required. Do not invoke model acquisition without a family when only the production LLM is needed.

## Runtime closeout

After the helper reports `PASS`:

```bash
backend/.venv/bin/python scripts/validate_backend.py profile
backend/.venv/bin/python scripts/ensure_models.py --family llm --verify-only
backend/.venv/bin/python scripts/validate_backend.py runtime --families llm --devices cuda
```

Completion requires observable runtime evidence, not artifact selection alone:

- production selects `assistant-qwen3-8b-q5-balanced`;
- `linux_amd64_gpu_nvidia_cuda` is selected and ready;
- the managed sidecar starts;
- health and model endpoints respond;
- a real completion succeeds;
- server output identifies CUDA device use or GPU layer offload.

## Cleanup boundaries

The helper may remove only:

- its provenance-specific external CMake build tree when the fingerprint changes;
- abandoned `runtimes/llama.cpp/linux-amd64-cuda.stage.*` directories;
- the previous CUDA runtime after successful replacement, unless `--keep-previous-runtime` is supplied.

It does not remove models, the Linux CPU runtime, CUDA installations, drivers, or unrelated build workspaces.

## References

- llama.cpp upstream build documentation: CUDA builds use CMake with `GGML_CUDA=ON`; architecture selection is available through `CMAKE_CUDA_ARCHITECTURES`.
- CMake `CMAKE_BUILD_RPATH_USE_ORIGIN`: converts build-tree RPATH entries to paths relative to `$ORIGIN` where supported.
- NVIDIA CUDA Installation Guide for Linux 13.3: documents `/usr/local/cuda-13.3`, PATH/`LD_LIBRARY_PATH` setup, and supported Linux host compiler ranges.
